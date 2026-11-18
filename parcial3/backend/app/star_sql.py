"""SQL (Athena / Trino) que construye el modelo estrella desde la landing zone.

Proceso de cada refresco (reconstruccion completa, idempotente):
  1. DDL (gratis en Athena): base, tabla externa sobre los eventos crudos (JSON por lineas,
     gzip) y tablas externas sobre los CSV de referencia.
  2. Por cada tabla de la estrella: DROP TABLE + CTAS en Parquet hacia un prefijo nuevo
     star/<tabla>/<run_id>/. Re-ejecutar el mismo lote produce exactamente las mismas filas:
     nunca hay INSERT sobre lo anterior, asi que no puede duplicar.

Las reglas de limpieza estan en el SQL de los hechos:
  * Duplicados: ROW_NUMBER() OVER (PARTITION BY event_id) = 1.
  * Tardios y desordenados: la fecha sale de event_ts, nunca de la hora de llegada ni de la
    carpeta de S3; como se reconstruye todo, un evento que llega tarde cae en su fecha.
  * Version de la ruta (SCD tipo 2): join "as-of" valid_from <= fecha < valid_to.
  * Rutas o clases desconocidas apuntan al miembro 0 de la dimension (sin huerfanos, R6).
"""

FAR_FUTURE = "DATE '9999-12-31'"
TS_REGEX = r"'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'"


def ddl(db: str, bucket: str, raw_prefix: str, ref_prefix: str) -> list[tuple[str, str]]:
    raw = f"s3://{bucket}/{raw_prefix}"
    ref = f"s3://{bucket}/{ref_prefix}"
    csv = "ROW FORMAT DELIMITED FIELDS TERMINATED BY ',' STORED AS TEXTFILE"
    skip = "TBLPROPERTIES ('skip.header.line.count'='1')"
    return [
        ("database", f"CREATE DATABASE IF NOT EXISTS {db}"),
        ("raw_events", f"""
CREATE EXTERNAL TABLE IF NOT EXISTS {db}.raw_events (
  event_id string, event_type string, event_ts string, schema_version int,
  session_id string, origin string, destination string, travel_date string, results_count int,
  reservation_id string, flight_id string, route string, flight_date string,
  fare_class string, price_cents bigint)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
LOCATION '{raw}'"""),
        ("ref_routes", f"""
CREATE EXTERNAL TABLE IF NOT EXISTS {db}.ref_routes (
  route string, origin string, destination string, region string)
{csv} LOCATION '{ref}routes/' {skip}"""),
        ("ref_route_category_history", f"""
CREATE EXTERNAL TABLE IF NOT EXISTS {db}.ref_route_category_history (
  route string, route_category string, effective_date string)
{csv} LOCATION '{ref}route_category_history/' {skip}"""),
        ("ref_holidays", f"""
CREATE EXTERNAL TABLE IF NOT EXISTS {db}.ref_holidays (
  holiday_date string, holiday_name string)
{csv} LOCATION '{ref}holidays/' {skip}"""),
    ]


# ------------------------------------------------------------------------- SELECTs
# Se separan del CTAS para poder verificarlos en local (DuckDB) con el mismo texto.

def select_dim_date(db: str) -> str:
    return f"""
WITH h AS (
  SELECT CAST(trim(holiday_date) AS date) AS hday,
         array_join(array_agg(trim(holiday_name)), ' / ') AS holiday_name
  FROM {db}.ref_holidays
  GROUP BY 1
),
days AS (
  -- CAST: en Athena sequence() sobre fechas devuelve timestamp(0), que el CTAS a Parquet rechaza.
  SELECT CAST(d AS date) AS day FROM UNNEST(sequence(DATE '2023-01-01', DATE '2027-12-31', INTERVAL '1' DAY)) AS t(d)
),
x AS (
  SELECT d.day,
         h0.holiday_name,
         h0.hday IS NOT NULL AS is_holiday,
         hm1.hday IS NOT NULL AS hol_minus1,
         hm2.hday IS NOT NULL AS hol_minus2,
         hp1.hday IS NOT NULL AS hol_plus1,
         hp2.hday IS NOT NULL AS hol_plus2
  FROM days d
  LEFT JOIN h h0  ON h0.hday  = d.day
  LEFT JOIN h hm1 ON hm1.hday = date_add('day', -1, d.day)
  LEFT JOIN h hm2 ON hm2.hday = date_add('day', -2, d.day)
  LEFT JOIN h hp1 ON hp1.hday = date_add('day', 1, d.day)
  LEFT JOIN h hp2 ON hp2.hday = date_add('day', 2, d.day)
)
SELECT
  CAST(year(day) * 10000 + month(day) * 100 + day_of_month(day) AS integer) AS date_key,
  day AS full_date,
  CAST(year(day) AS integer) AS year,
  CAST(quarter(day) AS integer) AS quarter,
  CAST(month(day) AS integer) AS month,
  date_format(day, '%M') AS month_name,
  date_format(day, '%Y-%m') AS year_month,
  CAST(day_of_month(day) AS integer) AS day_of_month,
  CAST(day_of_week(day) AS integer) AS weekday,
  date_format(day, '%W') AS weekday_name,
  day_of_week(day) >= 6 AS is_weekend,
  is_holiday,
  COALESCE(holiday_name, '') AS holiday_name,
  -- Puente: festivo en viernes o lunes, mas el sabado y domingo de ese fin de semana.
  CASE day_of_week(day)
    WHEN 1 THEN is_holiday
    WHEN 5 THEN is_holiday
    WHEN 6 THEN hol_minus1 OR hol_plus2
    WHEN 7 THEN hol_minus2 OR hol_plus1
    ELSE false
  END AS is_long_weekend,
  NOT (day_of_week(day) >= 6 OR is_holiday) AS is_business_day
FROM x"""


def select_dim_route(db: str) -> str:
    return f"""
WITH h AS (
  SELECT trim(route) AS route, trim(route_category) AS route_category,
         CAST(trim(effective_date) AS date) AS vf
  FROM {db}.ref_route_category_history
),
v AS (
  SELECT route, route_category, vf,
         lead(vf) OVER (PARTITION BY route ORDER BY vf) AS nxt,
         row_number() OVER (PARTITION BY route ORDER BY vf) AS version
  FROM h
)
SELECT CAST(row_number() OVER (ORDER BY v.route, v.vf) AS integer) AS route_key,
       v.route, trim(r.origin) AS origin, trim(r.destination) AS destination, trim(r.region) AS region,
       v.route_category,
       v.vf AS valid_from,
       COALESCE(v.nxt, {FAR_FUTURE}) AS valid_to,
       v.nxt IS NULL AS is_current,
       CAST(v.version AS integer) AS version
FROM v
JOIN {db}.ref_routes r ON trim(r.route) = v.route
UNION ALL
SELECT CAST(0 AS integer), 'UNKNOWN', 'UNK', 'UNK', 'UNKNOWN', 'UNKNOWN',
       DATE '1900-01-01', {FAR_FUTURE}, true, CAST(1 AS integer)"""


def select_dim_fare_class(db: str) -> str:
    return """
SELECT CAST(fare_class_key AS integer) AS fare_class_key, fare_class, fare_class_name,
       CAST(cabin_rank AS integer) AS cabin_rank
FROM (VALUES (0, 'UNKNOWN', 'Unknown', 0),
             (1, 'ECONOMY', 'Economy', 1),
             (2, 'BUSINESS', 'Business', 2)) AS t(fare_class_key, fare_class, fare_class_name, cabin_rank)"""


def select_fact_search(db: str) -> str:
    return f"""
WITH e AS (
  SELECT event_id, session_id, upper(trim(origin)) AS origin, upper(trim(destination)) AS destination,
         travel_date, results_count, event_ts,
         CAST(substr(event_ts, 1, 10) AS date) AS event_date,
         row_number() OVER (PARTITION BY event_id ORDER BY event_ts) AS rn
  FROM {db}.raw_events
  WHERE event_type = 'search_performed' AND event_id IS NOT NULL
    AND regexp_like(event_ts, {TS_REGEX})
)
SELECT e.event_id,
       d.date_key,
       COALESCE(r.route_key, 0) AS route_key,
       CAST(COALESCE(e.results_count, 0) AS integer) AS results_count,
       CAST(1 AS integer) AS searches,
       e.session_id,
       try_cast(e.travel_date AS date) AS travel_date,
       CAST(date_diff('day', e.event_date, try_cast(e.travel_date AS date)) AS integer) AS days_to_travel,
       e.event_ts,
       substr(e.event_ts, 1, 7) AS month
FROM e
JOIN {db}.dim_date d ON d.full_date = e.event_date
LEFT JOIN {db}.dim_route r
       ON r.route = concat(e.origin, '-', e.destination)
      AND e.event_date >= r.valid_from AND e.event_date < r.valid_to
WHERE e.rn = 1"""


def select_fact_booking_event(db: str) -> str:
    return f"""
WITH e AS (
  SELECT event_id, event_type, reservation_id, flight_id, upper(trim(route)) AS route,
         flight_date, upper(trim(fare_class)) AS fare_class, price_cents, event_ts,
         CAST(substr(event_ts, 1, 10) AS date) AS event_date,
         row_number() OVER (PARTITION BY event_id ORDER BY event_ts) AS rn
  FROM {db}.raw_events
  WHERE event_type IN ('reservation_created', 'reservation_cancelled') AND event_id IS NOT NULL
    AND regexp_like(event_ts, {TS_REGEX})
)
SELECT e.event_id,
       d.date_key,
       COALESCE(r.route_key, 0) AS route_key,
       COALESCE(c.fare_class_key, 0) AS fare_class_key,
       e.reservation_id,
       e.event_type,
       CAST(CASE WHEN e.event_type = 'reservation_created' THEN 1 ELSE 0 END AS integer) AS bookings,
       CAST(CASE WHEN e.event_type = 'reservation_cancelled' THEN 1 ELSE 0 END AS integer) AS cancellations,
       CAST(CASE WHEN e.event_type = 'reservation_created' THEN e.price_cents ELSE -e.price_cents END AS bigint)
         AS revenue_cents,
       e.flight_id,
       try_cast(e.flight_date AS date) AS flight_date,
       e.event_ts,
       substr(e.event_ts, 1, 7) AS month
FROM e
JOIN {db}.dim_date d ON d.full_date = e.event_date
LEFT JOIN {db}.dim_route r
       ON r.route = e.route
      AND e.event_date >= r.valid_from AND e.event_date < r.valid_to
LEFT JOIN {db}.dim_fare_class c ON c.fare_class = e.fare_class
WHERE e.rn = 1"""


# Orden de construccion: primero dimensiones (los hechos hacen join con ellas).
TABLES = [
    ("dim_date", select_dim_date, None),
    ("dim_route", select_dim_route, None),
    ("dim_fare_class", select_dim_fare_class, None),
    ("fact_search", select_fact_search, "month"),
    ("fact_booking_event", select_fact_booking_event, "month"),
]


def ctas(db: str, table: str, select_sql: str, location: str, partition: str | None) -> str:
    props = [f"format = 'PARQUET'", "write_compression = 'SNAPPY'", f"external_location = '{location}'"]
    if partition:
        props.append(f"partitioned_by = ARRAY['{partition}']")
    return f"CREATE TABLE {db}.{table} WITH ({', '.join(props)}) AS {select_sql}"
