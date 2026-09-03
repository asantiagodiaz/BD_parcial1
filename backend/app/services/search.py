"""Modulo search - busqueda de vuelos directos y con 1 escala (FR-01, FR-02, FR-03).

La disponibilidad mostrada es ORIENTATIVA: la busqueda no toma locks (NFR-01/02).
El control real de sobreventa ocurre al reservar (app/services/booking.py, NFR-03).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    InstanciaVuelo,
    InventarioAsientos,
    Ruta,
    Tarifa,
    VueloProgramado,
)
from app.schemas import BusquedaResultado, OpcionVueloOut, TarifaOut, TramoOut


def _tarifa_aplicable(
    db: Session, id_ruta: int, cabina: str, dias_anticipacion: int
) -> Tarifa | None:
    return db.scalar(
        select(Tarifa)
        .where(
            Tarifa.id_ruta == id_ruta,
            Tarifa.cabina == cabina,
            Tarifa.dias_anticipacion_min <= dias_anticipacion,
            Tarifa.dias_anticipacion_max >= dias_anticipacion,
        )
        .order_by(Tarifa.monto_precio.asc())
    )


def _tramos_de(
    db: Session, origen: str, destino: str, fecha: dt.date, cabina: str
) -> list[TramoOut]:
    """Todos los tramos directos origen->destino que salen en 'fecha'."""
    filas = db.execute(
        select(InstanciaVuelo, VueloProgramado, Ruta, InventarioAsientos)
        .join(VueloProgramado, InstanciaVuelo.id_vuelo_programado == VueloProgramado.id_vuelo_programado)
        .join(Ruta, VueloProgramado.id_ruta == Ruta.id_ruta)
        .join(
            InventarioAsientos,
            (InventarioAsientos.id_instancia_vuelo == InstanciaVuelo.id_instancia_vuelo)
            & (InventarioAsientos.cabina == cabina),
        )
        .where(
            Ruta.iata_origen == origen,
            Ruta.iata_destino == destino,
            InstanciaVuelo.fecha_salida == fecha,
            InstanciaVuelo.estado == "PROGRAMADO",
        )
    ).all()

    hoy = dt.date.today()
    tramos: list[TramoOut] = []
    for inst, vp, ruta, inv in filas:
        dias_ant = (fecha - hoy).days
        tarifa = _tarifa_aplicable(db, ruta.id_ruta, cabina, dias_ant)
        if tarifa is None:
            continue
        tramos.append(
            TramoOut(
                id_instancia_vuelo=inst.id_instancia_vuelo,
                numero_vuelo=vp.numero_vuelo,
                iata_origen=ruta.iata_origen,
                iata_destino=ruta.iata_destino,
                salida_utc=inst.salida_utc,
                llegada_utc=inst.llegada_utc,
                cabina=cabina,
                asientos_disponibles=inv.asientos_totales
                - inv.asientos_vendidos
                - inv.asientos_retenidos,
                tarifa=TarifaOut(
                    id_tarifa=tarifa.id_tarifa,
                    clase_tarifa=tarifa.clase_tarifa,
                    cabina=tarifa.cabina,
                    monto_precio=float(tarifa.monto_precio),
                    moneda=tarifa.moneda,
                    es_reembolsable=tarifa.es_reembolsable,
                ),
            )
        )
    return tramos


def buscar(
    db: Session,
    origen: str,
    destino: str,
    fecha: dt.date,
    pasajeros: int,
    cabina: str = "ECONOMICA",
    con_escalas: bool = True,
) -> BusquedaResultado:
    origen, destino, cabina = origen.upper(), destino.upper(), cabina.upper()
    opciones: list[OpcionVueloOut] = []

    # --- Directos (FR-01) ---
    for tramo in _tramos_de(db, origen, destino, fecha, cabina):
        if tramo.asientos_disponibles >= pasajeros:
            opciones.append(
                OpcionVueloOut(
                    tramos=[tramo],
                    escalas=0,
                    precio_total=round(tramo.tarifa.monto_precio * pasajeros, 2),
                    moneda=tramo.tarifa.moneda,
                )
            )

    # --- Con 1 escala (FR-02) ---
    if con_escalas:
        # aeropuertos de conexion posibles: destinos de rutas que salen del origen
        conexiones = db.execute(
            select(Ruta.iata_destino).where(Ruta.iata_origen == origen).distinct()
        ).scalars()
        for hub in conexiones:
            if hub in (origen, destino):
                continue
            primeros = _tramos_de(db, origen, hub, fecha, cabina)
            if not primeros:
                continue
            # el segundo tramo puede salir el mismo dia o el siguiente
            segundos = _tramos_de(db, hub, destino, fecha, cabina) + _tramos_de(
                db, hub, destino, fecha + dt.timedelta(days=1), cabina
            )
            for t1 in primeros:
                if t1.asientos_disponibles < pasajeros:
                    continue
                for t2 in segundos:
                    if t2.asientos_disponibles < pasajeros:
                        continue
                    espera = (t2.salida_utc - t1.llegada_utc).total_seconds() / 60
                    if not (
                        settings.min_connection_minutes
                        <= espera
                        <= settings.max_connection_minutes
                    ):
                        continue
                    precio = round(
                        (t1.tarifa.monto_precio + t2.tarifa.monto_precio) * pasajeros, 2
                    )
                    opciones.append(
                        OpcionVueloOut(
                            tramos=[t1, t2],
                            escalas=1,
                            precio_total=precio,
                            moneda=t1.tarifa.moneda,
                        )
                    )

    opciones.sort(key=lambda o: o.precio_total)
    return BusquedaResultado(opciones=opciones)
