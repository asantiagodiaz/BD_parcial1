"""Verifica la logica del job PySpark contra el oraculo del harness, sin AWS.

Genera datos crudos con la semilla del equipo, aplica limpiar_vuelos / limpiar_reservas /
construir (las mismas funciones que usa emr/job.py en EMR) en Spark local y compara con
la verdad (airline_data.oracle). Trabaja en memoria: la lectura/escritura de S3 y Parquet
se prueba en EMR real.

Uso:
  python emr/verificar_local.py --seed 963 --rows 200000 --harness <ruta a parcial2-harness>
Requiere Java 17 (JAVA_HOME) y pyspark. En Windows ademas HADOOP_HOME apuntando a una
carpeta cualquiera (solo para que Hadoop no se queje; no se hace E/S).
"""

import argparse
import os
import sys

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=963)
    ap.add_argument("--rows", type=int, default=200_000)
    ap.add_argument("--harness", required=True, help="carpeta parcial2-harness (con airline_data/)")
    a = ap.parse_args()
    sys.path.insert(0, a.harness)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from airline_data.oracle import Truth
    from job import construir, limpiar_reservas, limpiar_vuelos
    from pyspark.sql import SparkSession

    truth = Truth(a.seed, a.rows)
    print(f"crudo: {len(truth.flights_raw)} vuelos, {len(truth.res_raw)} reservas")

    spark = (
        SparkSession.builder.master("local[2]").appName("verificar")
        .config("spark.sql.shuffle.partitions", "4").config("spark.ui.enabled", "false").getOrCreate()
    )
    # Se escribe el CSV crudo y se lee con spark.read.csv, igual que en EMR (todo llega como texto).
    import tempfile
    tmp = tempfile.mkdtemp(prefix="emr_local_")
    truth.flights_raw.to_csv(os.path.join(tmp, "flights.csv"), index=False)
    truth.res_raw.to_csv(os.path.join(tmp, "reservations.csv"), index=False)
    vuelos = spark.read.option("header", True).csv(os.path.join(tmp, "flights.csv"))
    reservas = spark.read.option("header", True).csv(os.path.join(tmp, "reservations.csv"))

    detalle_df, metricas_df = construir(limpiar_vuelos(vuelos), limpiar_reservas(reservas))
    # collect() en vez de toPandas(): no depende de la conversion Arrow/pandas de PySpark
    detalle = pd.DataFrame([r.asDict() for r in detalle_df.collect()])
    metricas = (
        pd.DataFrame([r.asDict() for r in metricas_df.collect()])
        .sort_values(["route", "month"]).reset_index(drop=True)
    )
    spark.stop()

    esperado = truth.metrics
    ok = True

    def check(nombre, cond, extra=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'OK' if cond else 'FALLA'}] {nombre} {extra}")

    check("filas curadas", len(detalle) == truth.row_count, f"({len(detalle)} vs {truth.row_count})")
    check("meses distintos", detalle["month"].nunique() == 24, f"({detalle['month'].nunique()})")
    check(
        "ingreso CONFIRMED por mes",
        all(
            int(detalle[(detalle["month"] == m) & (detalle["status"] == "CONFIRMED")]["price_cents"].sum())
            == truth.confirmed_revenue(m)
            for m in truth.params["months"]
        ),
    )
    check("filas de metricas", len(metricas) == len(esperado), f"({len(metricas)} vs {len(esperado)})")
    for col in ["seats_capacity", "seats_sold", "revenue_cents", "cancellations"]:
        check(f"metricas.{col}", (metricas[col].values == esperado[col].values).all())
    # DATA.md / enunciado A.2: "bookings = CONFIRMED count". El oraculo del harness
    # (oracle.route_month_metrics) cuenta TODAS las reservas validas en esa columna, pero
    # ningun test la compara; seguimos el contrato escrito: bookings == seats_sold.
    check("metricas.bookings (== CONFIRMED, segun contrato)",
          (metricas["bookings"].values == esperado["seats_sold"].values).all())
    check("metricas.occupancy", ((metricas["occupancy"] - esperado["occupancy"]).abs() < 1e-9).all())
    print("\nRESULTADO:", "TODO OK" if ok else "HAY DIFERENCIAS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
