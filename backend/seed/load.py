"""Carga datos de ejemplo en la BD transaccional.

  python -m seed.load           # datos base + 30 dias de instancias
  python -m seed.load --reset   # borra y recarga

Genera:
  - 5 aeropuertos, rutas entre ellos, 3 aeronaves con cabinas
  - vuelos programados (diarios) + instancias para un rango de fechas
  - inventario por instancia y cabina
  - tarifas por ruta/cabina/ventana de anticipacion
  - 2 agencias, cuentas de usuario de ejemplo
  - 1 vuelo "casi lleno" (1 asiento en ECONOMICA) para la prueba de concurrencia
"""

from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import (
    Aeronave,
    Aeropuerto,
    Agencia,
    ConfigCabina,
    CuentaUsuario,
    InstanciaVuelo,
    InventarioAsientos,
    Ruta,
    Tarifa,
    VueloProgramado,
)

AEROPUERTOS = [
    ("BOG", "El Dorado", "Bogota", "CO", "America/Bogota"),
    ("MDE", "Jose Maria Cordova", "Rionegro", "CO", "America/Bogota"),
    ("CTG", "Rafael Nunez", "Cartagena", "CO", "America/Bogota"),
    ("CLO", "Alfonso Bonilla Aragon", "Cali", "CO", "America/Bogota"),
    ("BAQ", "Ernesto Cortissoz", "Barranquilla", "CO", "America/Bogota"),
]

# rutas (origen, destino, distancia_km) - ida y vuelta
RUTAS = [
    ("BOG", "MDE", 240),
    ("MDE", "BOG", 240),
    ("BOG", "CTG", 660),
    ("CTG", "BOG", 660),
    ("BOG", "CLO", 300),
    ("CLO", "BOG", 300),
    ("MDE", "CTG", 460),
    ("CTG", "MDE", 460),
    ("CLO", "BAQ", 700),
    ("BAQ", "CLO", 700),
]

# vuelos programados: (numero, origen, destino, hora_local, duracion_min, aeronave_idx)
VUELOS = [
    ("RA101", "BOG", "MDE", dt.time(6, 0), 45, 0),
    ("RA102", "MDE", "BOG", dt.time(8, 0), 45, 0),
    ("RA111", "BOG", "MDE", dt.time(18, 0), 45, 0),
    ("RA201", "BOG", "CTG", dt.time(7, 0), 80, 1),
    ("RA202", "CTG", "BOG", dt.time(10, 0), 80, 1),
    ("RA301", "BOG", "CLO", dt.time(9, 0), 55, 2),
    ("RA302", "CLO", "BOG", dt.time(12, 0), 55, 2),
    ("RA401", "MDE", "CTG", dt.time(11, 0), 60, 0),
    ("RA402", "CTG", "MDE", dt.time(14, 0), 60, 0),
    ("RA501", "CLO", "BAQ", dt.time(13, 0), 90, 2),
]

AERONAVES = [
    ("HK-1001", "ATR 72", {"ECONOMICA": 60, "EJECUTIVA": 8}),
    ("HK-1002", "Airbus A320", {"ECONOMICA": 150, "EJECUTIVA": 12}),
    ("HK-1003", "Embraer 190", {"ECONOMICA": 96, "EJECUTIVA": 10}),
]

DIAS = 30  # instancias a generar desde hoy


def _reset() -> None:
    """Vacia las tablas SIN borrar el esquema (conserva el trigger append-only)."""
    from sqlalchemy import text

    from app.db import Base

    s = SessionLocal()
    tablas = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    s.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
    s.commit()
    s.close()
    print("  tablas vaciadas (TRUNCATE)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="borra y recrea todo")
    args = ap.parse_args()

    if args.reset:
        _reset()

    from app.db import Base

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    if db.scalar(select(Aeropuerto).limit(1)):
        print("ya hay datos; usa --reset para recargar")
        return

    # --- aeropuertos ---
    for iata, nombre, ciudad, pais, tz in AEROPUERTOS:
        db.add(Aeropuerto(codigo_iata=iata, nombre=nombre, ciudad=ciudad, pais=pais, zona_horaria=tz))
    db.flush()

    # --- rutas ---
    rutas: dict[tuple[str, str], Ruta] = {}
    for o, d, km in RUTAS:
        r = Ruta(iata_origen=o, iata_destino=d, distancia_km=km)
        db.add(r)
        rutas[(o, d)] = r
    db.flush()

    # --- aeronaves + cabinas ---
    aeronaves: list[Aeronave] = []
    for matricula, modelo, cabinas in AERONAVES:
        av = Aeronave(matricula=matricula, modelo=modelo)
        db.add(av)
        db.flush()
        for cab, n in cabinas.items():
            db.add(ConfigCabina(id_aeronave=av.id_aeronave, cabina=cab, num_asientos=n))
        aeronaves.append(av)
    db.flush()

    # --- tarifas: 2 ventanas de anticipacion x 2 cabinas por ruta ---
    for (o, d), r in rutas.items():
        base = 180000 + (r.distancia_km or 300) * 250
        db.add_all(
            [
                Tarifa(id_ruta=r.id_ruta, cabina="ECONOMICA", clase_tarifa="PROMO",
                       dias_anticipacion_min=15, dias_anticipacion_max=365,
                       monto_precio=round(base * 0.8, 2), moneda="COP", es_reembolsable=False,
                       penalidad_cambio=80000),
                Tarifa(id_ruta=r.id_ruta, cabina="ECONOMICA", clase_tarifa="FLEX",
                       dias_anticipacion_min=0, dias_anticipacion_max=14,
                       monto_precio=round(base * 1.3, 2), moneda="COP", es_reembolsable=True,
                       penalidad_cambio=0),
                Tarifa(id_ruta=r.id_ruta, cabina="EJECUTIVA", clase_tarifa="BUSINESS",
                       dias_anticipacion_min=0, dias_anticipacion_max=365,
                       monto_precio=round(base * 2.2, 2), moneda="COP", es_reembolsable=True,
                       penalidad_cambio=0),
            ]
        )
    db.flush()

    # --- vuelos programados ---
    hoy = dt.date.today()
    vp_por_numero: dict[str, VueloProgramado] = {}
    for numero, o, d, hora, dur, av_idx in VUELOS:
        vp = VueloProgramado(
            numero_vuelo=numero,
            id_ruta=rutas[(o, d)].id_ruta,
            id_aeronave=aeronaves[av_idx].id_aeronave,
            hora_salida_local=hora,
            duracion_min=dur,
            dias_semana=[1, 2, 3, 4, 5, 6, 7],
            vigente_desde=hoy,
            vigente_hasta=hoy + dt.timedelta(days=DIAS + 5),
        )
        db.add(vp)
        vp_por_numero[numero] = vp
    db.flush()

    # --- instancias + inventario para DIAS dias ---
    cabinas_por_aeronave = {
        av.id_aeronave: {c.cabina: c.num_asientos for c in av.cabinas} for av in aeronaves
    }
    for numero, vp in vp_por_numero.items():
        for offset in range(DIAS):
            fecha = hoy + dt.timedelta(days=offset)
            # salida/llegada en UTC (Colombia = UTC-5, sin DST)
            salida_local = dt.datetime.combine(fecha, vp.hora_salida_local)
            salida_utc = salida_local + dt.timedelta(hours=5)
            llegada_utc = salida_utc + dt.timedelta(minutes=vp.duracion_min)
            inst = InstanciaVuelo(
                id_vuelo_programado=vp.id_vuelo_programado,
                fecha_salida=fecha,
                salida_utc=salida_utc,
                llegada_utc=llegada_utc,
                estado="PROGRAMADO",
            )
            db.add(inst)
            db.flush()
            for cabina, n in cabinas_por_aeronave[vp.id_aeronave].items():
                db.add(
                    InventarioAsientos(
                        id_instancia_vuelo=inst.id_instancia_vuelo,
                        cabina=cabina,
                        asientos_totales=n,
                        asientos_vendidos=0,
                        asientos_retenidos=0,
                    )
                )
    db.flush()

    # --- agencias + cuentas ---
    ag1 = Agencia(nombre="Viajes Andina", nit="900111222", tasa_comision=0.07, tasa_descuento=0.03)
    ag2 = Agencia(nombre="TurisCaribe", nit="900333444", tasa_comision=0.05, tasa_descuento=0.00)
    db.add_all([ag1, ag2])
    db.flush()
    db.add_all(
        [
            CuentaUsuario(correo="admin@aerolinea.co", hash_contrasena="x", rol="ADMIN"),
            CuentaUsuario(correo="agente@andina.co", hash_contrasena="x",
                          rol="AGENTE_AGENCIA", id_agencia=ag1.id_agencia),
        ]
    )

    # --- vuelo "casi lleno" para la prueba de concurrencia: 1 asiento ECONOMICA ---
    inst_test = db.scalars(
        select(InstanciaVuelo)
        .join(VueloProgramado)
        .where(VueloProgramado.numero_vuelo == "RA101")
        .order_by(InstanciaVuelo.fecha_salida)
    ).all()[7]  # 7 dias -> cae en la ventana PROMO (>=15? no) usamos FLEX; ver test
    inv_econ = db.scalar(
        select(InventarioAsientos).where(
            InventarioAsientos.id_instancia_vuelo == inst_test.id_instancia_vuelo,
            InventarioAsientos.cabina == "ECONOMICA",
        )
    )
    inv_econ.asientos_vendidos = inv_econ.asientos_totales - 1  # deja 1 disponible
    print(f"  vuelo de prueba: instancia={inst_test.id_instancia_vuelo} "
          f"fecha={inst_test.fecha_salida} ECONOMICA disponibles=1")

    db.commit()
    print("seed OK")


if __name__ == "__main__":
    main()
