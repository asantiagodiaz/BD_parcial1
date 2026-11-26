# Sustentación del Parcial 3: pregunta, respuesta y cómo verificarlo

Cada punto tiene tres partes: lo que pide el parcial, cómo lo resolvimos y cómo mostrarlo. Los comandos se pueden copiar y pegar sin cambiar nada.
🖥️ **AWS** = se muestra en la consola de AWS (región us-east-1).

---

## 0. Preparación (10 min antes, en una sola terminal)

```bash
cd ~/Universidad/Big\ Data/BD_parcial1
source parcial3/aws-env.sh
aws kinesis describe-stream-summary --stream-name airline-events >/dev/null 2>&1 || parcial3/infra/crear_stream.sh
IP=$(aws ec2 describe-instances --filters Name=tag:aws:cloudformation:stack-name,Values=AirlineP3 \
  Name=instance-state-name,Values=running --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
API=http://$IP:8000
B=s3://p3-airline-891376990124
source parcial3/tools/athena_q.sh
echo "$API" ; curl -s $API/health
```
- Antes de correr el bloque, entra a AWS Academy, dale *Start Lab* y pega las credenciales en `parcial3/aws-credentials`. La primera línea debe quedar como `[learnerlab]`.
- En la salida de `/health`, `last_error` debe ser `null`.
- Deja abiertos: el navegador en `$API/` y `$API/manager`, la consola de AWS, VS Code y el PDF `PARCIAL3-ENTREGA.pdf`.

> Cada bloque es **eliminatorio**: si el equipo no sabe defender una parte, se pierden también sus puntos del harness. Todos deben poder explicar los tres bloques.

---

# BLOQUE A: eventos y vista en vivo (R1–R4)

## R1 (7 pts)
**Pide el parcial:** que cada búsqueda, reserva y cancelación publique exactamente un evento válido. El evento debe cumplir el contrato, `event_ts` debe ser el momento en que ocurrió, la clave de partición debe ser la especificada y no puede llevar datos personales.

**Respuesta:**
- `events.py` arma el evento según el contrato A.1: `event_id` UUID, `event_ts` en UTC del momento real y `schema_version` 1.
- La clave de partición es `session_id` en las búsquedas (sale del header `X-Session-Id`) y `flight_id` en reservas y cancelaciones. Así, los eventos de un mismo vuelo van al mismo shard y conservan su orden.
- El nombre del pasajero se guarda en PostgreSQL, pero nunca va en el evento.
- Para la cancelación agregamos `POST /reservations/{id}/cancel`: 200 si cancela, 409 si ya estaba cancelada y 404 si no existe.

**Verificar:**
```bash
parcial3/tools/demo_evento.sh
```
- El paso 1 hace búsqueda, reserva, cancelación y una segunda cancelación (debe dar 409).
- El paso 2 imprime los 3 eventos tal como llegaron a Kinesis. Señala `event_ts`, la clave de partición y que no aparece `passenger_name`.

## R2 (6 pts)
**Pide el parcial:** que ningún evento se pierda en una ráfaga y que publicar no vuelva lenta la API. El harness manda 200 búsquedas, 50 a la vez, y exige p95 ≤ 1 s y exactamente 200 eventos.

**Respuesta:**
- **Búsquedas:** van a una cola en memoria y un hilo las envía con `PutRecords` en lotes de hasta 500. La petición nunca espera a Kinesis. Solo se reintentan los registros que fallaron, así que no hay duplicados.
- **Reservas:** `PutRecord` síncrono **después del commit**, con reintentos. Así nunca se publica una reserva que no quedó guardada.

**Verificar:**
```bash
curl -s $API/health            # publisher.dropped = 0
grep -A3 "^## R2" parcial3/report.md
```
- El reporte muestra p95 = 0,257 s y 200 eventos para 200 peticiones.
- En VS Code, muestra la clase `Publisher` de `backend/app/events.py`.

## R3 (7 pts)
**Pide el parcial:** que `GET /analytics/live` refleje eventos nuevos en menos de 10 s y cuente por hora del evento. Los eventos viejos repetidos no deben aparecer.

**Respuesta:**
- Un hilo dentro de la misma API (`live.py`, `StreamConsumer`) lee el shard cada 1 s.
- Guarda una hora de eventos indexados por `event_id`, así que deduplica.
- Cuenta por `event_ts`: el replay del harness trae fechas de 2025 y queda fuera de la ventana.
- Al arrancar lee desde hace una hora, para no empezar en cero después de un reinicio.

**Verificar:**
```bash
curl -s "$API/analytics/live?window=5"; echo
curl -s -o /dev/null -H 'X-Session-Id: defensa' "$API/flights/search?origin=CTG&destination=BOG&date=2026-12-20"
sleep 3; curl -s "$API/analytics/live?window=5"; echo      # searches subió en 1
```
O en el navegador: abre `$API/manager`, haz búsquedas y reservas desde `$API/` en otra pestaña y mira subir los contadores.

## R4 (4 pts)
**Pide el parcial:** que todo evento llegue a la landing zone en S3 en máximo 5 minutos.

**Respuesta:**
- Firehose lee el stream y escribe en `raw/events/AAAA/MM/DD/HH/` con búfer de 60 s y GZIP.
- Tiene activado el procesador `AppendDelimiterToRecord`, que deja un JSON por línea. Sin él los JSON quedan pegados (`}{`) y Athena no puede leerlos.
- Elegimos Firehose porque es gestionado, cuesta unos US$0,05 al mes y no es enhanced fan-out (R11).

**Verificar:** el paso 4 de `demo_evento.sh` encuentra los 3 eventos en S3 en unos 70 s. A mano:
```bash
aws s3 ls $B/raw/events/ --recursive | tail -3
```
🖥️ **AWS:**
1. **Kinesis → Data streams → airline-events.** En *Configuration* se ve Provisioned, 1 shard y 24 h. En *Monitoring* se ven los picos de la corrida del harness.
2. **Amazon Data Firehose → airline-events-to-s3 → Configuration.** Fuente Kinesis, búfer de 60 s, GZIP y *Append delimiter to record*.
3. **S3 → p3-airline-891376990124 → raw/events/2026/11/…**: descargar y abrir un `.gz`.

---

# BLOQUE B: modelo estrella (R5–R10)

Primero refresca la estrella (tarda unos 30 s):
```bash
curl -s -XPOST $API/admin/refresh-star; echo; sleep 35; curl -s $API/admin/refresh-status; echo
```

## R5 (7 pts)
**Pide el parcial:** que las tablas de la estrella existan en el catálogo de Glue con las columnas y tipos del contrato, en Parquet. `fact_search` debe estar particionada por mes, con las particiones registradas. `dim_date` debe estar enriquecida (nombre del día, trimestre, festivos y puentes) para cada día de 2023 a 2027.

**Respuesta:**
- El ETL usa Athena CTAS (`star_sql.py`) con `format = PARQUET` y `partitioned_by = ['month']`. El mismo CTAS registra las particiones en Glue.
- `dim_date` se genera con `sequence()`: 1826 días. Lleva trimestre, `weekday` (1 = lunes), `weekday_name`, festivo con su nombre (sacado de `holidays_ref.csv`) y puente.
- Un día es puente cuando un festivo cae viernes o lunes: ese día más el sábado y el domingo.

**Verificar:**
```bash
q "SELECT count(*), min(full_date), max(full_date) FROM dim_date"
q "SELECT full_date, weekday_name, quarter, is_holiday, holiday_name, is_long_weekend
   FROM dim_date WHERE full_date BETWEEN DATE '2025-01-03' AND DATE '2025-01-07' ORDER BY 1"
aws glue get-partitions --database-name airline_star --table-name fact_search --query 'Partitions[].Values' --output text
```
- La primera consulta da 1826 días. En la segunda, el lunes 6 de enero es Reyes, así que el sábado 4, el domingo 5 y el lunes 6 son puente.
- Muestra también el diagrama `docs/diagrams/08-modelo-estrella-parcial3.png`.

🖥️ **AWS:**
1. **Glue → Data Catalog → Databases → airline_star → fact_search.** En *Schema* están las columnas y `month` como partición. En *Partitions* aparecen 2025-01, 2025-02, 2025-03 y 2026-11.
2. **S3 → star/fact_search/<carpeta>/**: hay una carpeta `month=…` por mes con archivos Parquet.

## R6 (5 pts)
**Pide el parcial:** integridad. Claves de dimensión únicas, ningún hecho apuntando a una dimensión que no existe y una fila de hecho por `event_id`.

**Respuesta:**
- Las claves sustitutas se generan en el CTAS.
- `dim_route` y `dim_fare_class` tienen un miembro UNKNOWN con clave 0: un evento con ruta o clase desconocida apunta ahí y nunca queda huérfano.
- `ROW_NUMBER() OVER (PARTITION BY event_id)` deja una sola fila por evento.
- `dim_date` no lleva miembro desconocido porque R5 exige exactamente los días de 2023 a 2027.

**Verificar** (las tres columnas deben dar 0):
```bash
q "SELECT (SELECT count(*) - count(DISTINCT route_key) FROM dim_route) AS claves_repetidas,
          (SELECT count(*) FROM fact_booking_event f LEFT JOIN dim_route r ON f.route_key = r.route_key
           WHERE r.route_key IS NULL) AS huerfanos,
          (SELECT count(*) - count(DISTINCT event_id) FROM fact_search) AS eventos_repetidos"
```

## R7 (11 pts, el que más vale)
**Pide el parcial:** que las preguntas de negocio Q1, Q2, Q3, Q4, Q6, Q7 y Q8 den los números correctos.

**Respuesta:**
- Diseñamos el modelo a partir de las preguntas (matriz bus en el PDF, §5.3).
- Hay dos hechos: `fact_search`, con una fila por búsqueda, y `fact_booking_event`, con una fila por reserva o por cancelación. La cancelación lleva ingreso negativo, así que el ingreso neto sale de un `SUM`.
- `dim_date` y `dim_route` son **conformadas**: las comparten los dos hechos, y por eso Q6 y Q7 pueden cruzar búsquedas con reservas.

**Verificar:** en Athena (🖥️ **AWS → Athena → Query editor**, workgroup **airline-p3**, base `airline_star`) o en la terminal:
```bash
# Q1 ingreso neto por mes y clase
q "SELECT d.year_month, c.fare_class, sum(f.revenue_cents)/100.0 AS ingreso_neto
   FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
   JOIN dim_fare_class c ON f.fare_class_key = c.fare_class_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1, 2 ORDER BY 1, 2"
# Q2 tasa de cancelación por ruta
q "SELECT r.route, sum(f.bookings) AS reservas, sum(f.cancellations) AS cancelaciones,
          round(1.0*sum(f.cancellations)/sum(f.bookings), 4) AS tasa
   FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1 ORDER BY 1"
# Q3 reservas por día de la semana
q "SELECT d.weekday, d.weekday_name, sum(f.bookings) AS reservas
   FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1, 2 ORDER BY 1"
# Q4 top 10 rutas por ingreso
q "SELECT r.route, sum(f.revenue_cents)/100.0 AS ingreso
   FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
# Q6 conversión por ruta (dos hechos, una dimensión compartida)
q "WITH s AS (SELECT r.route, sum(f.searches) b FROM fact_search f JOIN dim_route r ON f.route_key = r.route_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1),
        k AS (SELECT r.route, sum(f.bookings) v FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1)
   SELECT s.route, s.b AS busquedas, k.v AS reservas, round(1.0*k.v/s.b, 4) AS conversion
   FROM s JOIN k ON s.route = k.route ORDER BY 1"
# Q7 festivos frente a otros días
q "WITH s AS (SELECT d.is_holiday h, sum(f.searches) b FROM fact_search f JOIN dim_date d ON f.date_key = d.date_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1),
        k AS (SELECT d.is_holiday h, sum(f.bookings) v FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1)
   SELECT s.h AS festivo, s.b AS busquedas, k.v AS reservas FROM s JOIN k ON s.h = k.h"
# Q8 reservas en puentes
q "SELECT d.is_long_weekend, sum(f.bookings) AS reservas
   FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1"
```
- Para comprobar que cuadran: en Q3 y en Q8 las reservas suman 2.600, y en Q7 las búsquedas suman 17.000.
- El filtro `rp-%` deja solo los eventos del replay del harness.

## R8 (6 pts)
**Pide el parcial:** que se eliminen los duplicados, que los eventos tardíos usen su propia fecha y que `POST /admin/refresh-star` termine en menos de 15 minutos.

**Respuesta:**
- Se deduplica por `event_id`. La fecha sale de `event_ts`, no de la hora de llegada ni de la carpeta de S3.
- Cada refresco reconstruye todo: DROP + CTAS a una carpeta nueva y luego borra la anterior. Por eso es **idempotente**: correrlo dos veces da lo mismo.
- Un evento tardío cae en su fecha real.
- Un evento fuera de orden no cambia nada, porque el orden de llegada no se usa.
- En `star.py`, si llega otro POST durante una corrida, se agenda otra corrida al terminar.

**Verificar:**
```bash
curl -s $API/admin/refresh-status; echo                                    # SUCCEEDED, ~30 s
q "SELECT event_type, count(*) FROM fact_booking_event WHERE event_id LIKE 'rp-%' GROUP BY 1"   # 2600 y 312
q "SELECT month, count(*) FROM fact_search WHERE event_id LIKE 'rp-%' GROUP BY 1 ORDER BY 1"    # 5824 / 5146 / 6030
```
El harness envió 20.509 registros con un 3 % de duplicados. Quedan exactamente 17.000 búsquedas, 2.600 reservas y 312 cancelaciones.

## R9 (8 pts)
**Pide el parcial:** que `dim_route` sea una dimensión de cambio lento tipo 2 y que los hechos usen la versión vigente en la fecha del evento (pregunta Q5).

**Respuesta:**
- Cada versión de una ruta es una fila.
- `valid_to` es la fecha de la versión siguiente, calculada con `LEAD(effective_date)`, o `9999-12-31` si no hay siguiente.
- `is_current` es verdadero solo en la última versión.
- El hecho elige la versión con un join as-of: `valid_from <= fecha_evento < valid_to`.
- Con tipo 1, todo enero de 2025 de CTG-BOG saldría como REGIONAL aunque era TRUNK, y los reportes de meses cerrados cambiarían cada vez que se recategoriza una ruta.

**Verificar:**
```bash
q "SELECT route, route_category, valid_from, valid_to, is_current FROM dim_route
   WHERE route IN ('CTG-BOG','CUC-SMR','ADZ-BAQ') ORDER BY route, valid_from"
# Q5 ingreso por categoría vigente el día del evento
q "SELECT f.month, r.route_category, sum(f.revenue_cents)/100.0 AS ingreso
   FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1, 2 ORDER BY 1, 2"
```
Las tres rutas tienen dos versiones, con el cambio el 2025-02-01.

## R10 (4 pts)
**Pide el parcial:** que una consulta filtrada por mes no escanee todo (máximo el 60 % de lo que escanea sin filtro) y que el workgroup de Athena tenga un límite de 1 GB por consulta.

**Respuesta:** los hechos están particionados por `month`, así que Athena solo lee la carpeta de ese mes. El workgroup `airline-p3` tiene `BytesScannedCutoffPerQuery` = 1 GB, lo que protege el presupuesto.

**Verificar:**
```bash
q "SELECT sum(results_count) FROM fact_search WHERE month = '2025-02'"     # ~3.400 bytes
q "SELECT sum(results_count) FROM fact_search"                             # ~11.200 bytes → razón ≈ 0,3
aws athena get-work-group --work-group airline-p3 --query 'WorkGroup.Configuration.BytesScannedCutoffPerQuery'
```
🖥️ **AWS:**
1. En **Athena**, corre las dos consultas y compara *Data scanned* debajo del resultado.
2. En **Athena → Workgroups → airline-p3**, el *Per query data usage control* está en 1 GB.

> No uses `count(*)` para esta comparación: Athena lo responde con metadatos y marca 0 bytes.

---

# BLOQUE C: costo y arquitectura (R11–R12)

## R11 (3 pts)
**Pide el parcial:** un stream mínimo: modo provisionado, un shard, retención por defecto (máximo 24 h) y sin consumidores enhanced fan-out.

**Respuesta:**
- `infra/crear_stream.sh` lo crea así.
- Leen el shard tres consumidores estándar: Firehose, nuestro hilo y el harness. Comparten 5 lecturas por segundo; por eso nuestro hilo lee cada 1 s.
- El stream no está en el stack de CloudFormation porque cobra por hora: se crea al empezar a probar y se borra al terminar.

**Verificar:**
```bash
aws kinesis describe-stream-summary --stream-name airline-events \
  --query 'StreamDescriptionSummary.[StreamModeDetails.StreamMode,OpenShardCount,RetentionPeriodHours,ConsumerCount]' --output text
# → PROVISIONED  1  24  0
```
🖥️ **AWS:** en **Kinesis → airline-events**, la pestaña *Enhanced fan-out* está vacía.

## R12 (2 pts)
**Pide el parcial:** una proyección de costo mensual (`cost_projection.yaml`) de máximo 1,5 veces la solución de referencia del profesor, nunca por encima de US$50, que incluya Kinesis, S3 y Athena.

**Respuesta:**
- El total es **US$18,15 al mes**. La EC2 sola es el 84 %.
- PostgreSQL corre en la misma EC2 y no en RDS, lo que ahorra unos US$14,70 al mes. A cambio se pierden los respaldos gestionados, que en producción se reemplazarían con snapshots.
- Si el volumen se multiplicara por 10, el total subiría a unos US$21.

**Verificar:**
```bash
cat parcial3/cost_projection.yaml
```
- Muestra la sección 8 del PDF y el diagrama `docs/diagrams/07-arquitectura-aws-parcial3.png`.

🖥️ **AWS:**
1. **CloudFormation → AirlineP3 → Resources**: aparecen solo EC2, el security group, la base de Glue y el workgroup. Lo que cobra por hora queda fuera.
2. **EC2 → Instances**: una t3.small que tiene la API y PostgreSQL.
3. **S3 → p3-airline-891376990124 → Management → Lifecycle rules**: resultados de Athena y errores de Firehose se borran a los 7 días; el código, a los 30.

---

# SECCIÓN 5 DEL ENUNCIADO: decisiones que hay que justificar

Están en el **capítulo 6 del PDF**, cada una con su requisito y su pilar Well-Architected. Se explican, no se muestran en AWS.

**1. ¿Qué va al stream y qué no? ¿Por qué las búsquedas encajan en Kinesis y las reservas son delicadas? ¿Qué se puede perder? ¿Cómo evitar perder una reserva entre la base de datos y el stream? (§6.1)**
- Las búsquedas son muchas, baratas y perder una no daña a nadie.
- Una reserva es dinero: no se puede perder ni publicar si no quedó guardada.
- En producción usaríamos el patrón *outbox*: el evento se guarda en una tabla, en la misma transacción que la reserva, y otro proceso lo publica después y lo marca como enviado. Lo describimos, no lo implementamos.
- Pilares: confiabilidad y eficiencia de rendimiento.

**2. Dos caminos: ¿por qué la vista en vivo lee el stream y no Athena? ¿Por qué la estrella se refresca cada pocos minutos y no por evento? ¿Qué se rompería si se actualizara por evento? (§6.2)**
- La vista en vivo necesita segundos. Athena tarda segundos por consulta, cobra cada consulta y lee datos que se refrescan cada pocos minutos.
- Actualizar la estrella por evento crearía miles de archivos Parquet diminutos y miles de consultas al día, con un costo enorme. Además rompería la deduplicación y el manejo de eventos tardíos, que necesitan ver el lote completo.

**3. Landing zone: ¿cómo llegan los eventos de Kinesis a S3 y por qué? ¿Cuánto cuesta en latencia y en dinero? (§6.3)**
- Con Firehose: unos 60 s de latencia por el búfer y unos US$0,05 al mes.
- Lo comparamos con un consumidor propio que escriba a S3: es más código que mantener y es un punto de falla más.

**4. Diseño de la estrella: medida, hecho y dimensiones por pregunta, matriz bus, grano de cada hecho, dimensiones conformadas y atributos agregados. (§5 y §6.4)**
- Granos: una fila por búsqueda distinta y una fila por reserva o cancelación distinta.
- La matriz bus está en el PDF, §5.3.
- Las dimensiones conformadas son `dim_date` y `dim_route`.
- Los atributos agregados van en gris en el diagrama `08`: `month_name`, `year_month`, `is_business_day`, `version`, `fare_class_name`, `cabin_rank`, `days_to_travel`, entre otros.

**5. ETL: comparar alternativas (Athena CTAS, Lambda con pandas o DuckDB, Glue job) en costo por corrida y por mes, arranque frente al límite de 15 min, crecimiento, operación e idempotencia. ¿Cuándo cambiarían? (§6.5)**
- Elegimos Athena CTAS: no tiene servidores ni arranque en frío, corre en unos 30 s, cuesta centavos al mes y es idempotente por reconstrucción.
- Lambda tiene un tope de 15 min y 10 GB de memoria.
- Glue cobra un mínimo por DPU y tarda en arrancar.
- Lo cambiaríamos por un proceso incremental (Iceberg + `MERGE`, o Glue/EMR Serverless) si llegáramos a millones de eventos diarios.

**6. SCD: ¿por qué tipo 2 para la categoría? ¿Qué respondería mal una tipo 1? ¿Cómo eligen la versión para un evento tardío? (§6.6)**
- La respuesta está en R9.
- Al evento tardío se le asigna la versión por su `event_ts`, no por la fecha en que llegó.

**7. Eventos sucios: ¿cómo deduplican y qué cambian "tardío" y "fuera de orden" en el diseño? (§6.7)**
- La respuesta está en R8.

**8. Costo y ciclo de vida: ¿qué existe siempre y qué solo mientras se prueba? Tabla de justificación de servicios y narrativa de costos. (§6.8, §6.9 y §8)**
- Siempre existen: la EC2, el bucket, Glue y el workgroup.
- Solo mientras se prueba: el stream y Firehose (`crear_stream.sh` y `borrar_stream.sh`).
- Ciclo de vida en S3.
- Pilares: optimización de costos y sostenibilidad.

---

# ENTREGABLES

| Pide el parcial | Dónde está |
|---|---|
| Documento actualizado (secciones 5 y 6) | `parcial3/docs/PARCIAL3-ENTREGA.pdf` |
| Backend, consumidor y job de carga | `parcial3/backend/app/`: `events.py`, `live.py`, `star.py` y `star_sql.py` |
| Scripts para crear y borrar el stream | `parcial3/infra/crear_stream.sh` y `borrar_stream.sh` |
| `config.yaml` sin credenciales | `parcial3/config.yaml` |
| `cost_projection.yaml` | `parcial3/cost_projection.yaml` |
| `report.md` final | `parcial3/report.md` (70/70) |
| Apéndice de prompts | Capítulo 12 del PDF |

---

# CAMBIO EN VIVO (sección 8 del enunciado)

**Pide el parcial:** que el profesor pueda pedir un cambio en vivo, por ejemplo agregar una medida a un hecho o un atributo a una dimensión, y que el equipo diga qué partes del pipeline, de las tablas y de las pruebas se afectan.

**Respuesta (primero decirlo, después hacerlo).** Ejemplo: *"agreguen el ingreso bruto"*.
- **Pipeline:** solo cambia el SQL del hecho en `star_sql.py`. El evento ya trae `price_cents`, así que no se tocan la API, el stream ni `raw_events`.
- **Tablas:** `fact_booking_event` gana una columna. Las dimensiones no cambian.
- **Pruebas:** el harness no se rompe, porque el contrato permite columnas extra.

**Hacerlo:**
```bash
git switch -c cambio-en-vivo
# Editar parcial3/backend/app/star_sql.py, en select_fact_booking_event, ANTES de la línea de month:
#   CAST(CASE WHEN e.event_type = 'reservation_created' THEN e.price_cents ELSE 0 END AS bigint)
#     AS gross_revenue_cents,
(cd parcial3/backend && .venv/bin/python ../tools/verificar_estrella_local.py --harness ../../../parcial3-harness-estudiantes)
parcial3/infra/actualizar_codigo.sh
curl -s -XPOST $API/admin/refresh-star; echo; sleep 35; curl -s $API/admin/refresh-status; echo
q "SELECT d.year_month, sum(f.gross_revenue_cents)/100.0 AS bruto, sum(f.revenue_cents)/100.0 AS neto
   FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1 ORDER BY 1"
```
Para un atributo de dimensión (`DEFENSA.md` §5.2), por ejemplo temporada alta: en `select_dim_date` se agrega `month(day) IN (1, 6, 7, 12) AS is_high_season,`. Solo cambia `dim_date`; los hechos lo alcanzan por `date_key` sin tocarlos.

**Volver a como estaba:**
```bash
git restore parcial3/backend/app/star_sql.py && git switch master && git branch -D cambio-en-vivo
parcial3/infra/actualizar_codigo.sh
curl -s -XPOST $API/admin/refresh-star
```

---

# AL TERMINAR
```bash
parcial3/infra/borrar_stream.sh
```
El shard se cobra por hora.
