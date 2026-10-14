"""Job PySpark (EMR): limpia el historial crudo y genera las dos tablas del contrato.

Entrada  (CSV crudo, sucio):  <input>/flights.csv, <input>/reservations.csv
Salida 1 (Parquet, particionado por month):  <curated>   -> reservations_curated
Salida 2 (Parquet, sin particionar):         <metrics>   -> route_month_metrics

Reglas de limpieza (enunciado 4.1):
  C1 route:  quitar TODO espacio en blanco y pasar a mayusculas
  C2 status: strip + mayusculas
  C3 conservar solo status in {CONFIRMED, CANCELLED}
  C4 descartar price_cents nulo o <= 0
  C5 descartar reservation_id duplicados (se conserva el primero)

Uso (EMR step):
  spark-submit job.py --input s3://bucket/raw/ --curated s3://bucket/curated/reservations_curated/ \
                      --metrics s3://bucket/curated/route_month_metrics/
"""

import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


def limpiar_vuelos(vuelos):
    return (
        vuelos.withColumn("flight_id", F.col("flight_id").cast("string"))
        # C1: \s+ elimina espacios internos y de los extremos (' bog - mde ' -> 'BOG-MDE')
        .withColumn("route", F.upper(F.regexp_replace("route", r"\s+", "")))
        .withColumn("capacity", F.col("capacity").cast("long"))
        .withColumn("month", F.substring("flight_date", 1, 7))
        .select("flight_id", "route", "month", "capacity")
    )


def limpiar_reservas(reservas):
    r = (
        reservas.withColumn("reservation_id", F.col("reservation_id").cast("string"))
        .withColumn("flight_id", F.col("flight_id").cast("string"))
        .withColumn("price_cents", F.col("price_cents").cast("long"))
        # C2
        .withColumn("status", F.upper(F.trim("status")))
    )
    # C3
    r = r.filter(F.col("status").isin("CONFIRMED", "CANCELLED"))
    # C4: price_cents nulo (isNotNull) o <= 0 se descartan
    r = r.filter(F.col("price_cents").isNotNull() & (F.col("price_cents") > 0))
    # C5: conservar la primera aparicion. Se ordena por una columna de orden de lectura
    # para que "primero" sea determinista y no dependa del shuffle.
    r = r.withColumn("_orden", F.monotonically_increasing_id())
    w = Window.partitionBy("reservation_id").orderBy("_orden")
    r = r.withColumn("_n", F.row_number().over(w)).filter(F.col("_n") == 1)
    return r.select("reservation_id", "flight_id", "fare_class", "price_cents", "status")


def construir(vuelos_limpios, reservas_limpias):
    """Devuelve (detalle, metricas) segun el contrato de datos."""
    # Detalle: una fila por reserva valida, con la ruta y el mes del VUELO (month = mes de flight_date)
    detalle = (
        reservas_limpias.join(vuelos_limpios.select("flight_id", "route", "month"), "flight_id", "inner")
        .select("reservation_id", "flight_id", "route", "fare_class", "price_cents", "status", "month")
    )

    # Capacidad: suma de la capacidad de TODOS los vuelos de la ruta en el mes
    # (aunque un vuelo no tenga reservas, sus asientos cuentan como capacidad).
    capacidad = vuelos_limpios.groupBy("route", "month").agg(F.sum("capacity").alias("seats_capacity"))

    ventas = detalle.groupBy("route", "month").agg(
        F.sum(F.when(F.col("status") == "CONFIRMED", 1).otherwise(0)).alias("seats_sold"),
        F.sum(F.when(F.col("status") == "CONFIRMED", F.col("price_cents")).otherwise(0)).alias("revenue_cents"),
        F.sum(F.when(F.col("status") == "CANCELLED", 1).otherwise(0)).alias("cancellations"),
    )

    metricas = (
        capacidad.join(ventas, ["route", "month"], "left")
        .na.fill(0, ["seats_sold", "revenue_cents", "cancellations"])
        .withColumn("seats_capacity", F.col("seats_capacity").cast("long"))
        .withColumn("seats_sold", F.col("seats_sold").cast("long"))
        .withColumn("revenue_cents", F.col("revenue_cents").cast("long"))
        .withColumn("cancellations", F.col("cancellations").cast("long"))
        .withColumn("bookings", F.col("seats_sold"))  # bookings = reservas CONFIRMED
        .withColumn("occupancy", F.col("seats_sold") / F.col("seats_capacity"))
        .select(
            "route", "month", "seats_capacity", "seats_sold", "occupancy",
            "revenue_cents", "bookings", "cancellations",
        )
    )
    return detalle, metricas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="carpeta con flights.csv y reservations.csv")
    ap.add_argument("--curated", required=True, help="destino de reservations_curated (Parquet)")
    ap.add_argument("--metrics", required=True, help="destino de route_month_metrics (Parquet)")
    a = ap.parse_args()
    base = a.input.rstrip("/")

    spark = SparkSession.builder.appName("airline-curate").getOrCreate()
    # Solo se reescribe la particion que cambia; no se borra el resto.
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

    vuelos = spark.read.option("header", True).csv(f"{base}/flights.csv")
    reservas = spark.read.option("header", True).csv(f"{base}/reservations.csv")

    detalle, metricas = construir(limpiar_vuelos(vuelos), limpiar_reservas(reservas))

    # Un archivo por mes (24 particiones): evita miles de archivos pequenos y mantiene
    # barato cada escaneo de Athena.
    (
        detalle.repartition("month")
        .write.mode("overwrite")
        .partitionBy("month")
        .parquet(a.curated)
    )
    # Son ~216 filas (9 rutas x 24 meses): un solo archivo.
    metricas.coalesce(1).write.mode("overwrite").parquet(a.metrics)

    spark.stop()


if __name__ == "__main__":
    main()
