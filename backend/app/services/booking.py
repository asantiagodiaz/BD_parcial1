"""Modulo booking - dueno del control de concurrencia contra la sobreventa.

Mecanismo: BLOQUEO PESIMISTA en PostgreSQL (decision de docs/04 seccion 5.4.2).
Dentro de la transaccion de reserva se hace SELECT ... FOR UPDATE sobre las filas
de inventario_asientos de cada segmento, se valida disponibilidad y se actualizan
los contadores antes del COMMIT.

Garantiza NFR-03 (no sobreventa) y NFR-04 (atomicidad del itinerario multi-tramo).
"""

from __future__ import annotations

import datetime as dt
import random
import string

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    Agencia,
    Billete,
    EventoReserva,
    InstanciaVuelo,
    InventarioAsientos,
    Itinerario,
    Pasajero,
    Reserva,
    ReservaPasajero,
    SegmentoItinerario,
    Tarifa,
)
from app.schemas import ReservaIn

_CODIGO_ALFABETO = string.ascii_uppercase + string.digits


def _nuevo_codigo_reserva(db: Session) -> str:
    """Localizador de 6 caracteres, unico (reintenta ante colision)."""
    for _ in range(10):
        codigo = "".join(random.choices(_CODIGO_ALFABETO, k=6))
        existe = db.scalar(select(Reserva.id_reserva).where(Reserva.codigo_reserva == codigo))
        if not existe:
            return codigo
    raise RuntimeError("no se pudo generar un codigo de reserva unico")


def _obtener_o_crear_pasajero(db: Session, datos) -> Pasajero:
    pax = db.scalar(
        select(Pasajero).where(
            Pasajero.tipo_documento == datos.tipo_documento,
            Pasajero.numero_documento == datos.numero_documento,
        )
    )
    if pax is None:
        pax = Pasajero(
            tipo_documento=datos.tipo_documento,
            numero_documento=datos.numero_documento,
            nombre_completo=datos.nombre_completo,
            fecha_nacimiento=datos.fecha_nacimiento,
            correo=datos.correo,
            telefono=datos.telefono,
        )
        db.add(pax)
        db.flush()
    return pax


def crear_reserva(db: Session, payload: ReservaIn, actor: str = "PASAJERO") -> Reserva:
    """Crea una reserva en estado RETENIDA (hold temporal).

    Toda la operacion ocurre en UNA transaccion (la sesion de FastAPI).
    El commit lo hace el router al terminar sin excepcion.
    """
    num_pax = len(payload.pasajeros)

    # --- 1. Resolver instancias de vuelo y ordenarlas de forma DETERMINISTA ---
    #        (por id_instancia_vuelo asc) para evitar deadlocks entre reservas
    #        multi-tramo que compartan vuelos en distinto orden.
    ids_solicitados = [s.id_instancia_vuelo for s in payload.segmentos]
    segmentos_ordenados = sorted(
        enumerate(payload.segmentos), key=lambda t: t[1].id_instancia_vuelo
    )

    # --- 2. BLOQUEO PESIMISTA: lock de las filas de inventario ---------------
    #        Cualquier otra reserva por estas mismas filas espera aqui.
    ids_ordenados = sorted(ids_solicitados)
    inventarios = (
        db.execute(
            select(InventarioAsientos)
            .where(
                InventarioAsientos.id_instancia_vuelo.in_(ids_ordenados),
            )
            .order_by(InventarioAsientos.id_instancia_vuelo)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    inv_por_vuelo = {
        (inv.id_instancia_vuelo, inv.cabina): inv for inv in inventarios
    }

    # --- 3. Validar disponibilidad de CADA segmento -------------------------
    for seg in payload.segmentos:
        inv = inv_por_vuelo.get((seg.id_instancia_vuelo, seg.cabina))
        if inv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no hay inventario para el vuelo {seg.id_instancia_vuelo} cabina {seg.cabina}",
            )
        if inv.disponibles < num_pax:
            # NFR-03: exactamente una reserva se lleva el ultimo asiento; el resto -> 409
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"vuelo {seg.id_instancia_vuelo} agotado en cabina {seg.cabina}: "
                    f"disponibles={inv.disponibles}, solicitados={num_pax}"
                ),
            )

    # --- 4. Aplicar el hold en cada fila de inventario ----------------------
    for seg in payload.segmentos:
        inv = inv_por_vuelo[(seg.id_instancia_vuelo, seg.cabina)]
        inv.asientos_retenidos += num_pax  # el CHECK del motor es la ultima barrera

    # --- 5. Calcular precio y (si aplica) descuento/comision de agencia -----
    tarifas = {
        t.id_tarifa: t
        for t in db.execute(
            select(Tarifa).where(Tarifa.id_tarifa.in_([s.id_tarifa for s in payload.segmentos]))
        ).scalars()
    }
    monto_base = 0.0
    montos_segmento: list[float] = []
    for seg in payload.segmentos:
        tarifa = tarifas.get(seg.id_tarifa)
        if tarifa is None or tarifa.cabina != seg.cabina:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tarifa {seg.id_tarifa} invalida para la cabina {seg.cabina}",
            )
        monto_seg = float(tarifa.monto_precio) * num_pax
        montos_segmento.append(monto_seg)
        monto_base += monto_seg

    tasa_descuento = 0.0
    tasa_comision = 0.0
    id_agencia = None
    if payload.canal == "AGENCIA":
        if payload.id_agencia is None:
            raise HTTPException(400, "canal AGENCIA requiere id_agencia")
        agencia = db.get(Agencia, payload.id_agencia)
        if agencia is None or not agencia.esta_activa:
            raise HTTPException(400, "agencia inexistente o inactiva")
        id_agencia = agencia.id_agencia
        tasa_descuento = float(agencia.tasa_descuento)
        tasa_comision = float(agencia.tasa_comision)

    monto_total = round(monto_base * (1 - tasa_descuento), 2)
    monto_comision = round(monto_total * tasa_comision, 2)

    # --- 6. Crear RESERVA, ITINERARIO, SEGMENTOS, RESERVA_PASAJERO ---------
    instancias = {
        i.id_instancia_vuelo: i
        for i in db.execute(
            select(InstanciaVuelo)
            .options(selectinload(InstanciaVuelo.vuelo_programado))
            .where(InstanciaVuelo.id_instancia_vuelo.in_(ids_solicitados))
        ).scalars()
    }
    primera = instancias[payload.segmentos[0].id_instancia_vuelo]
    ultima = instancias[payload.segmentos[-1].id_instancia_vuelo]

    reserva = Reserva(
        codigo_reserva=_nuevo_codigo_reserva(db),
        canal=payload.canal,
        id_agencia=id_agencia,
        estado="RETENIDA",
        retenida_hasta=dt.datetime.now(dt.timezone.utc)
        + dt.timedelta(minutes=settings.hold_minutes),
        monto_total=monto_total,
        moneda="COP",
        monto_comision=monto_comision,
    )
    db.add(reserva)
    db.flush()

    itinerario = Itinerario(
        id_reserva=reserva.id_reserva,
        iata_origen=_iata_origen(db, primera),
        iata_destino=_iata_destino(db, ultima),
    )
    db.add(itinerario)
    db.flush()

    for orden, seg in enumerate(payload.segmentos, start=1):
        db.add(
            SegmentoItinerario(
                id_itinerario=itinerario.id_itinerario,
                secuencia=orden,
                id_instancia_vuelo=seg.id_instancia_vuelo,
                cabina=seg.cabina,
                id_tarifa=seg.id_tarifa,
                monto_segmento=montos_segmento[orden - 1],
            )
        )

    for datos_pax in payload.pasajeros:
        pax = _obtener_o_crear_pasajero(db, datos_pax)
        db.add(
            ReservaPasajero(
                id_reserva=reserva.id_reserva,
                id_pasajero=pax.id_pasajero,
                es_contacto_principal=datos_pax.es_contacto_principal,
            )
        )

    # --- 7. EVENTO_RESERVA (auditoria append-only, NFR-09) ----------------
    db.add(
        EventoReserva(
            id_reserva=reserva.id_reserva,
            tipo_evento="CREADA",
            contenido={
                "num_pasajeros": num_pax,
                "segmentos": ids_solicitados,
                "monto_total": monto_total,
            },
            tipo_actor=actor,
        )
    )

    db.flush()
    return reserva


def _iata_origen(db: Session, instancia: InstanciaVuelo) -> str:
    return instancia.vuelo_programado.ruta.iata_origen


def _iata_destino(db: Session, instancia: InstanciaVuelo) -> str:
    return instancia.vuelo_programado.ruta.iata_destino


def obtener_reserva(db: Session, codigo: str) -> Reserva:
    reserva = db.scalar(
        select(Reserva)
        .where(Reserva.codigo_reserva == codigo.upper())
        .options(
            selectinload(Reserva.itinerario)
            .selectinload(Itinerario.segmentos)
            .selectinload(SegmentoItinerario.instancia_vuelo)
            .selectinload(InstanciaVuelo.vuelo_programado),
            selectinload(Reserva.pasajeros).selectinload(ReservaPasajero.pasajero),
            selectinload(Reserva.pagos),
            selectinload(Reserva.eventos),
        )
    )
    if reserva is None:
        raise HTTPException(status_code=404, detail=f"reserva {codigo} no encontrada")
    return reserva
