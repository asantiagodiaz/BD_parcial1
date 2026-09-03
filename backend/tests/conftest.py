"""Fixtures de test.

Requiere la BD PostgreSQL OLTP local accesible (ver backend/setup-postgres-local.sh).
Los tests NO usan SQLite: la prueba de concurrencia necesita el comportamiento
real de SELECT ... FOR UPDATE de PostgreSQL.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import (
    Aeronave,
    Aeropuerto,
    ConfigCabina,
    InstanciaVuelo,
    InventarioAsientos,
    Ruta,
    Tarifa,
    VueloProgramado,
)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _reset_reservas_e_inventario() -> None:
    from sqlalchemy import text

    s = SessionLocal()
    for tabla in (
        "billete",
        "asignacion_asiento",
        "pago",
        "evento_reserva",
        "segmento_itinerario",
        "itinerario",
        "reserva_pasajero",
        "reserva",
    ):
        s.execute(text(f"DELETE FROM {tabla}"))
    # Restaura el inventario del vuelo de prueba a "1 asiento disponible".
    s.execute(
        text(
            "UPDATE inventario_asientos "
            "SET asientos_vendidos = asientos_totales - 1, asientos_retenidos = 0 "
            "WHERE cabina = 'ECONOMICA'"
        )
    )
    s.commit()
    s.close()


@pytest.fixture
def limpiar_reservas():
    """Estado limpio antes y despues del test: sin reservas, 1 asiento libre."""
    _reset_reservas_e_inventario()
    yield
    _reset_reservas_e_inventario()


@pytest.fixture(scope="session")
def datos_base(_schema):
    """Un vuelo BOG->MDE manana con 1 asiento en ECONOMICA."""
    s = SessionLocal()
    if not s.scalar(select(Aeropuerto).limit(1)):
        s.add_all(
            [
                Aeropuerto(codigo_iata="BOG", nombre="El Dorado", ciudad="Bogota",
                           pais="CO", zona_horaria="America/Bogota"),
                Aeropuerto(codigo_iata="MDE", nombre="JMC", ciudad="Rionegro",
                           pais="CO", zona_horaria="America/Bogota"),
            ]
        )
        s.flush()
        ruta = Ruta(iata_origen="BOG", iata_destino="MDE", distancia_km=240)
        s.add(ruta)
        s.flush()
        av = Aeronave(matricula="HK-TEST", modelo="ATR 72")
        s.add(av)
        s.flush()
        s.add(ConfigCabina(id_aeronave=av.id_aeronave, cabina="ECONOMICA", num_asientos=60))
        s.add(
            Tarifa(id_ruta=ruta.id_ruta, cabina="ECONOMICA", clase_tarifa="FLEX",
                   dias_anticipacion_min=0, dias_anticipacion_max=365,
                   monto_precio=250000, moneda="COP", es_reembolsable=True, penalidad_cambio=0)
        )
        s.flush()
        manana = dt.date.today() + dt.timedelta(days=1)
        vp = VueloProgramado(
            numero_vuelo="RA999", id_ruta=ruta.id_ruta, id_aeronave=av.id_aeronave,
            hora_salida_local=dt.time(6, 0), duracion_min=45,
            dias_semana=[1, 2, 3, 4, 5, 6, 7],
            vigente_desde=dt.date.today(), vigente_hasta=manana + dt.timedelta(days=5),
        )
        s.add(vp)
        s.flush()
        inst = InstanciaVuelo(
            id_vuelo_programado=vp.id_vuelo_programado,
            fecha_salida=manana,
            salida_utc=dt.datetime.combine(manana, dt.time(11, 0), tzinfo=dt.timezone.utc),
            llegada_utc=dt.datetime.combine(manana, dt.time(11, 45), tzinfo=dt.timezone.utc),
            estado="PROGRAMADO",
        )
        s.add(inst)
        s.flush()
        s.add(
            InventarioAsientos(
                id_instancia_vuelo=inst.id_instancia_vuelo, cabina="ECONOMICA",
                asientos_totales=60, asientos_vendidos=59, asientos_retenidos=0,  # 1 disponible
            )
        )
        s.commit()

    inst = s.scalar(
        select(InstanciaVuelo).join(VueloProgramado).where(VueloProgramado.numero_vuelo == "RA999")
    )
    tarifa = s.scalar(select(Tarifa).where(Tarifa.clase_tarifa == "FLEX"))
    data = {
        "id_instancia_vuelo": inst.id_instancia_vuelo,
        "id_tarifa": tarifa.id_tarifa,
        "fecha": inst.fecha_salida,
    }
    s.close()
    return data
