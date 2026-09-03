"""Crea reservas de ejemplo con varios estados, para tener datos analiticos que
el ETL (etl/etl.py) pueda cargar al OLAP y las vistas de negocio muestren algo.

  python -m seed.demo_reservas          # ~12 reservas: confirmadas, canceladas, retenidas

Usa la ruta de codigo real (booking.crear_reserva -> hold) y luego ajusta el
estado de forma consistente con el inventario.
"""

from __future__ import annotations

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import InstanciaVuelo, Reserva, Tarifa, VueloProgramado
from app.schemas import PasajeroIn, ReservaIn, SegmentoIn
from app.services import booking

VUELOS_DEMO = ["RA101", "RA201", "RA301", "RA111", "RA401"]


def _confirmar(db, reserva: Reserva) -> None:
    """RETENIDA -> CONFIRMADA: mueve retenidos->vendidos SOLO en la cabina del segmento."""
    for seg in reserva.itinerario.segmentos:
        db.execute(
            text(
                "UPDATE inventario_asientos "
                "SET asientos_vendidos = asientos_vendidos + :n, "
                "    asientos_retenidos = asientos_retenidos - :n "
                "WHERE id_instancia_vuelo = :iv AND cabina = :cab"
            ),
            {"n": len(reserva.pasajeros), "iv": seg.id_instancia_vuelo, "cab": seg.cabina},
        )
    reserva.estado = "CONFIRMADA"
    db.add(
        __import__("app.models", fromlist=["EventoReserva"]).EventoReserva(
            id_reserva=reserva.id_reserva, tipo_evento="CONFIRMADA", tipo_actor="SISTEMA"
        )
    )


def _cancelar(db, reserva: Reserva) -> None:
    """RETENIDA -> CANCELADA: libera los retenidos."""
    for seg in reserva.itinerario.segmentos:
        db.execute(
            text(
                "UPDATE inventario_asientos "
                "SET asientos_retenidos = asientos_retenidos - :n "
                "WHERE id_instancia_vuelo = :iv AND cabina = :cab"
            ),
            {"n": len(reserva.pasajeros), "iv": seg.id_instancia_vuelo, "cab": seg.cabina},
        )
    reserva.estado = "CANCELADA"
    db.add(
        __import__("app.models", fromlist=["EventoReserva"]).EventoReserva(
            id_reserva=reserva.id_reserva, tipo_evento="CANCELADA", tipo_actor="PASAJERO"
        )
    )


def main() -> None:
    db = SessionLocal()

    instancias = db.execute(
        select(InstanciaVuelo, VueloProgramado)
        .join(VueloProgramado)
        .where(VueloProgramado.numero_vuelo.in_(VUELOS_DEMO))
        .order_by(InstanciaVuelo.fecha_salida)
        .limit(14)
    ).all()

    codigos: list[str] = []
    for i, (iv, vp) in enumerate(instancias):
        tarifa = db.scalar(
            select(Tarifa)
            .where(Tarifa.id_ruta == vp.id_ruta, Tarifa.cabina == "ECONOMICA")
            .order_by(Tarifa.monto_precio)
        )
        canal = "AGENCIA" if i % 4 == 0 else "DIRECTO"
        payload = ReservaIn(
            segmentos=[
                SegmentoIn(id_instancia_vuelo=iv.id_instancia_vuelo, cabina="ECONOMICA",
                           id_tarifa=tarifa.id_tarifa)
            ],
            pasajeros=[
                PasajeroIn(tipo_documento="CC", numero_documento=f"D{i:05d}",
                           nombre_completo=f"Demo Pax {i}", es_contacto_principal=True)
            ],
            canal=canal,
            id_agencia=1 if canal == "AGENCIA" else None,
        )
        r = booking.crear_reserva(db, payload)
        db.commit()
        codigos.append(r.codigo_reserva)

    # estados: ~65% confirmadas, ~20% canceladas, resto retenidas
    for j, cod in enumerate(codigos):
        r = booking.obtener_reserva(db, cod)
        if j % 5 in (0, 1, 2):
            _confirmar(db, r)
        elif j % 5 == 3:
            _cancelar(db, r)
        # j % 5 == 4  -> queda RETENIDA
        db.commit()

    conf = db.scalar(select(text("count(*)")).select_from(Reserva).where(Reserva.estado == "CONFIRMADA"))
    canc = db.scalar(select(text("count(*)")).select_from(Reserva).where(Reserva.estado == "CANCELADA"))
    ret = db.scalar(select(text("count(*)")).select_from(Reserva).where(Reserva.estado == "RETENIDA"))
    print(f"reservas demo: {len(codigos)}  ->  CONFIRMADA={conf}  CANCELADA={canc}  RETENIDA={ret}")


if __name__ == "__main__":
    main()
