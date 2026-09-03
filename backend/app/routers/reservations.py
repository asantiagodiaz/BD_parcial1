from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import InstanciaVuelo, SegmentoItinerario
from app.schemas import (
    EventoOut,
    PagoOut,
    PasajeroOut,
    ReservaCreada,
    ReservaIn,
    ReservaOut,
    SegmentoOut,
)
from app.services import booking

router = APIRouter(prefix="/reservations", tags=["reservas"])


@router.post("", response_model=ReservaCreada, status_code=status.HTTP_201_CREATED)
def crear_reserva(payload: ReservaIn, db: Session = Depends(get_db)):
    """FR-04 / FR-05 / FR-06: crea la reserva multi-tramo en estado RETENIDA.

    Refleja la decision de concurrencia de docs/04 (bloqueo pesimista):
    si algun segmento no tiene cupo ante peticiones simultaneas -> HTTP 409.
    """
    reserva = booking.crear_reserva(db, payload)
    db.commit()  # libera los locks tomados con FOR UPDATE
    db.refresh(reserva)
    return ReservaCreada(
        codigo_reserva=reserva.codigo_reserva,
        estado=reserva.estado,
        retenida_hasta=reserva.retenida_hasta,
        monto_total=float(reserva.monto_total),
        moneda=reserva.moneda,
    )


@router.get("/{codigo}", response_model=ReservaOut)
def consultar_reserva(codigo: str, db: Session = Depends(get_db)):
    """FR-12: consulta una reserva por su codigo, con historial (NFR-09)."""
    r = booking.obtener_reserva(db, codigo)
    it = r.itinerario
    segmentos = []
    for seg in it.segmentos:
        inst: InstanciaVuelo = seg.instancia_vuelo
        vp = inst.vuelo_programado
        segmentos.append(
            SegmentoOut(
                secuencia=seg.secuencia,
                id_instancia_vuelo=seg.id_instancia_vuelo,
                numero_vuelo=vp.numero_vuelo,
                iata_origen=vp.ruta.iata_origen,
                iata_destino=vp.ruta.iata_destino,
                salida_utc=inst.salida_utc,
                llegada_utc=inst.llegada_utc,
                cabina=seg.cabina,
                monto_segmento=float(seg.monto_segmento),
            )
        )
    return ReservaOut(
        codigo_reserva=r.codigo_reserva,
        canal=r.canal,
        estado=r.estado,
        retenida_hasta=r.retenida_hasta,
        monto_total=float(r.monto_total),
        moneda=r.moneda,
        monto_comision=float(r.monto_comision),
        creada_en=r.creada_en,
        iata_origen=it.iata_origen,
        iata_destino=it.iata_destino,
        segmentos=segmentos,
        pasajeros=[
            PasajeroOut(
                nombre_completo=rp.pasajero.nombre_completo,
                tipo_documento=rp.pasajero.tipo_documento,
                numero_documento=rp.pasajero.numero_documento,
                es_contacto_principal=rp.es_contacto_principal,
            )
            for rp in r.pasajeros
        ],
        pagos=[
            PagoOut(
                proveedor=p.proveedor,
                estado=p.estado,
                monto=float(p.monto),
                moneda=p.moneda,
                creado_en=p.creado_en,
            )
            for p in r.pagos
        ],
        historial=[
            EventoOut(
                tipo_evento=e.tipo_evento,
                tipo_actor=e.tipo_actor,
                ocurrido_en=e.ocurrido_en,
                contenido=e.contenido,
            )
            for e in sorted(r.eventos, key=lambda e: e.ocurrido_en)
        ],
    )
