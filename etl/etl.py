"""ETL  OLTP -> OLAP  (seccion 5.7).

Copia y TRANSFORMA (agrega/desnormaliza) datos del sistema transaccional al
almacen analitico en esquema estrella (analytics/schema_olap.sql).

  python etl/etl.py --init      # crea el esquema OLAP (una vez)
  python etl/etl.py             # ejecuta la carga (idempotente: upsert por segmento)
  python etl/etl.py --full      # recarga completa (TRUNCATE + insert)

Decisiones (justificadas en docs/07 5.7.2):
  - Que se copia: reservas a nivel de SEGMENTO + sus dimensiones (ruta, vuelo,
    tarifa, tiempo, canal). NO se copia tal cual: se desnormaliza y se derivan
    columnas (par_ruta, ventana_compra, temporada, banderas de estado).
  - Frecuencia: on-demand / diaria (cron). El analisis comercial no necesita
    datos al segundo; una carga diaria es suficiente y barata (5.7.5).
  - Motor del ETL: script Python con SQLAlchemy. Un AWS Glue Job PySpark seria
    la alternativa 'canonica' de Big Data; se descarta para el MVP por la
    complejidad de configurarlo en el Learner Lab (IAM, JDBC, VPC). Documentado
    como evolucion en 5.7.4.

Conexiones: OLTP_DATABASE_URL y OLAP_DATABASE_URL del entorno (.env).
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import sys

from sqlalchemy import create_engine, text

# permite ejecutar como  python etl/etl.py  sin instalar el paquete backend
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

try:
    from app.config import settings  # type: ignore

    OLTP_URL = settings.oltp_database_url
    OLAP_URL = settings.olap_database_url
except Exception:  # pragma: no cover - fallback si no esta el paquete backend
    OLTP_URL = os.environ["OLTP_DATABASE_URL"]
    OLAP_URL = os.environ["OLAP_DATABASE_URL"]

SCHEMA_SQL = pathlib.Path(__file__).resolve().parent.parent / "analytics" / "schema_olap.sql"

MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
# temporada alta en Colombia: dic, ene, jun, jul (vacaciones) + Semana Santa (aprox)
TEMPORADA_ALTA = {1, 6, 7, 12}


def _id_tiempo(fecha: dt.date) -> int:
    return fecha.year * 10000 + fecha.month * 100 + fecha.day


# --------------------------------------------------------------------------- #
# EXTRACT + TRANSFORM  (una consulta que une el OLTP a nivel de segmento)
# --------------------------------------------------------------------------- #

EXTRACT_SQL = text(
    """
    SELECT
        s.id_segmento_itinerario,
        r.codigo_reserva,
        r.estado                       AS estado_reserva,
        r.canal,
        r.creada_en::date              AS fecha_reserva,
        r.monto_total,
        r.monto_comision,

        ru.id_ruta,
        ru.iata_origen,
        ru.iata_destino,
        ao.ciudad                      AS ciudad_origen,
        ad.ciudad                      AS ciudad_destino,
        ru.distancia_km,

        iv.id_instancia_vuelo,
        iv.fecha_salida,
        iv.estado                      AS estado_vuelo,
        vp.numero_vuelo,
        av.modelo                      AS modelo_aeronave,

        ta.id_tarifa,
        ta.clase_tarifa,
        ta.cabina,
        ta.es_reembolsable,
        ta.dias_anticipacion_min,

        s.monto_segmento,
        cc.num_asientos                AS asientos_cabina,
        cap.asientos_totales_aeronave,
        (SELECT count(*) FROM reserva_pasajero rp WHERE rp.id_reserva = r.id_reserva) AS num_pasajeros
    FROM segmento_itinerario s
    JOIN itinerario  it ON it.id_itinerario = s.id_itinerario
    JOIN reserva     r  ON r.id_reserva = it.id_reserva
    JOIN instancia_vuelo iv ON iv.id_instancia_vuelo = s.id_instancia_vuelo
    JOIN vuelo_programado vp ON vp.id_vuelo_programado = iv.id_vuelo_programado
    JOIN ruta        ru ON ru.id_ruta = vp.id_ruta
    JOIN aeropuerto  ao ON ao.codigo_iata = ru.iata_origen
    JOIN aeropuerto  ad ON ad.codigo_iata = ru.iata_destino
    JOIN aeronave    av ON av.id_aeronave = vp.id_aeronave
    JOIN tarifa      ta ON ta.id_tarifa = s.id_tarifa
    JOIN config_cabina cc ON cc.id_aeronave = vp.id_aeronave AND cc.cabina = s.cabina
    JOIN LATERAL (
        SELECT COALESCE(SUM(num_asientos),0) AS asientos_totales_aeronave
        FROM config_cabina WHERE id_aeronave = vp.id_aeronave
    ) cap ON true
    """
)


def _ventana_compra(dias_min: int) -> str:
    return "anticipada" if dias_min >= 15 else "ultima hora"


def _transform(row) -> dict:
    d = row._mapping
    fecha_reserva = d["fecha_reserva"]
    fecha_vuelo = d["fecha_salida"]
    estado = d["estado_reserva"]
    return {
        # dims tiempo
        "tiempo_reserva": _fila_tiempo(fecha_reserva),
        "tiempo_vuelo": _fila_tiempo(fecha_vuelo),
        # dim ruta
        "ruta": {
            "id_ruta": d["id_ruta"],
            "iata_origen": d["iata_origen"],
            "iata_destino": d["iata_destino"],
            "ciudad_origen": d["ciudad_origen"],
            "ciudad_destino": d["ciudad_destino"],
            "par_ruta": f"{d['iata_origen']}-{d['iata_destino']}",
            "distancia_km": d["distancia_km"],
        },
        # dim vuelo
        "vuelo": {
            "id_instancia_vuelo": d["id_instancia_vuelo"],
            "numero_vuelo": d["numero_vuelo"],
            "fecha_salida": fecha_vuelo,
            "modelo_aeronave": d["modelo_aeronave"],
            "asientos_totales": d["asientos_totales_aeronave"],
            "estado": d["estado_vuelo"],
        },
        # dim tarifa
        "tarifa": {
            "id_tarifa": d["id_tarifa"],
            "clase_tarifa": d["clase_tarifa"],
            "cabina": d["cabina"],
            "es_reembolsable": d["es_reembolsable"],
            "ventana_compra": _ventana_compra(d["dias_anticipacion_min"]),
        },
        # hecho
        "fact": {
            "id_tiempo_reserva": _id_tiempo(fecha_reserva),
            "id_tiempo_vuelo": _id_tiempo(fecha_vuelo),
            "id_ruta": d["id_ruta"],
            "id_instancia_vuelo": d["id_instancia_vuelo"],
            "id_tarifa": d["id_tarifa"],
            "id_canal": 2 if d["canal"] == "AGENCIA" else 1,
            "codigo_reserva": d["codigo_reserva"],
            "id_segmento_itinerario": d["id_segmento_itinerario"],
            "num_pasajeros": d["num_pasajeros"],
            "ingreso_segmento": float(d["monto_segmento"]),
            "comision_agencia": round(
                float(d["monto_comision"])
                * (float(d["monto_segmento"]) / float(d["monto_total"]))
                if d["monto_total"]
                else 0.0,
                2,
            ),
            "asientos_cabina": d["asientos_cabina"],
            "estado_reserva": estado,
            "es_confirmada": estado == "CONFIRMADA",
            "es_cancelada": estado == "CANCELADA",
            "es_expirada": estado == "EXPIRADA",
        },
    }


def _fila_tiempo(fecha: dt.date) -> dict:
    return {
        "id_tiempo": _id_tiempo(fecha),
        "fecha": fecha,
        "anio": fecha.year,
        "mes": fecha.month,
        "dia": fecha.day,
        "dia_semana": fecha.isoweekday(),
        "nombre_mes": MESES_ES[fecha.month],
        "es_fin_semana": fecha.isoweekday() >= 6,
        "temporada": "ALTA" if fecha.month in TEMPORADA_ALTA else "BAJA",
    }


# --------------------------------------------------------------------------- #
# LOAD  (upsert en el OLAP)
# --------------------------------------------------------------------------- #

UPSERT_TIEMPO = text("""
    INSERT INTO dim_tiempo (id_tiempo, fecha, anio, mes, dia, dia_semana, nombre_mes, es_fin_semana, temporada)
    VALUES (:id_tiempo, :fecha, :anio, :mes, :dia, :dia_semana, :nombre_mes, :es_fin_semana, :temporada)
    ON CONFLICT (id_tiempo) DO NOTHING
""")

UPSERT_RUTA = text("""
    INSERT INTO dim_ruta (id_ruta, iata_origen, iata_destino, ciudad_origen, ciudad_destino, par_ruta, distancia_km)
    VALUES (:id_ruta, :iata_origen, :iata_destino, :ciudad_origen, :ciudad_destino, :par_ruta, :distancia_km)
    ON CONFLICT (id_ruta) DO UPDATE SET distancia_km = EXCLUDED.distancia_km
""")

UPSERT_VUELO = text("""
    INSERT INTO dim_vuelo (id_instancia_vuelo, numero_vuelo, fecha_salida, modelo_aeronave, asientos_totales, estado)
    VALUES (:id_instancia_vuelo, :numero_vuelo, :fecha_salida, :modelo_aeronave, :asientos_totales, :estado)
    ON CONFLICT (id_instancia_vuelo) DO UPDATE SET estado = EXCLUDED.estado
""")

UPSERT_TARIFA = text("""
    INSERT INTO dim_tarifa (id_tarifa, clase_tarifa, cabina, es_reembolsable, ventana_compra)
    VALUES (:id_tarifa, :clase_tarifa, :cabina, :es_reembolsable, :ventana_compra)
    ON CONFLICT (id_tarifa) DO NOTHING
""")

UPSERT_FACT = text("""
    INSERT INTO fact_reserva_segmento (
        id_tiempo_reserva, id_tiempo_vuelo, id_ruta, id_instancia_vuelo, id_tarifa, id_canal,
        codigo_reserva, id_segmento_itinerario, num_pasajeros, ingreso_segmento, comision_agencia,
        asientos_cabina, estado_reserva, es_confirmada, es_cancelada, es_expirada)
    VALUES (
        :id_tiempo_reserva, :id_tiempo_vuelo, :id_ruta, :id_instancia_vuelo, :id_tarifa, :id_canal,
        :codigo_reserva, :id_segmento_itinerario, :num_pasajeros, :ingreso_segmento, :comision_agencia,
        :asientos_cabina, :estado_reserva, :es_confirmada, :es_cancelada, :es_expirada)
    ON CONFLICT (id_segmento_itinerario) DO UPDATE SET
        estado_reserva = EXCLUDED.estado_reserva,
        es_confirmada  = EXCLUDED.es_confirmada,
        es_cancelada   = EXCLUDED.es_cancelada,
        es_expirada    = EXCLUDED.es_expirada,
        ingreso_segmento = EXCLUDED.ingreso_segmento,
        comision_agencia = EXCLUDED.comision_agencia,
        fecha_carga_etl  = now()
""")


def init_olap() -> None:
    """Ejecuta analytics/schema_olap.sql completo (psycopg admite multi-sentencia)."""
    import psycopg

    raw_url = OLAP_URL.replace("postgresql+psycopg://", "postgresql://")
    sql = SCHEMA_SQL.read_text()
    with psycopg.connect(raw_url, autocommit=True) as conn:
        conn.execute(sql)
    print(f"esquema OLAP creado desde {SCHEMA_SQL.name}")


def run(full: bool = False) -> dict:
    src = create_engine(OLTP_URL, future=True)
    dst = create_engine(OLAP_URL, future=True)

    with src.connect() as s:
        filas = list(s.execute(EXTRACT_SQL))

    transformadas = [_transform(f) for f in filas]

    with dst.begin() as d:
        if full:
            d.execute(text("TRUNCATE fact_reserva_segmento RESTART IDENTITY"))
        for t in transformadas:
            d.execute(UPSERT_TIEMPO, t["tiempo_reserva"])
            d.execute(UPSERT_TIEMPO, t["tiempo_vuelo"])
            d.execute(UPSERT_RUTA, t["ruta"])
            d.execute(UPSERT_VUELO, t["vuelo"])
            d.execute(UPSERT_TARIFA, t["tarifa"])
            d.execute(UPSERT_FACT, t["fact"])

    resumen = {
        "segmentos_procesados": len(transformadas),
        "confirmados": sum(1 for t in transformadas if t["fact"]["es_confirmada"]),
        "cancelados": sum(1 for t in transformadas if t["fact"]["es_cancelada"]),
        "modo": "full" if full else "incremental (upsert)",
        "ejecutado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    return resumen


def main() -> None:
    ap = argparse.ArgumentParser(description="ETL OLTP -> OLAP (estrella)")
    ap.add_argument("--init", action="store_true", help="crea el esquema OLAP")
    ap.add_argument("--full", action="store_true", help="recarga completa del hecho")
    args = ap.parse_args()

    if args.init:
        init_olap()
        if not args.full:
            return

    resumen = run(full=args.full)
    print("ETL OK:")
    for k, v in resumen.items():
        print(f"  {k:22s}: {v}")


if __name__ == "__main__":
    main()
