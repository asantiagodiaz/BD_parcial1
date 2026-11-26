# Cómo correr y comprobar el Parcial 3

Todos los comandos se corren desde la raíz del repo (`BD_parcial1/`), salvo que se indique otra carpeta.
`API` es la URL del backend. Hoy es `http://44.200.115.10:8000`, pero cambia si el Lab reinicia la EC2.

---

## 1. Encender todo (al empezar cada sesión del Learner Lab)

```bash
# 1) En AWS Academy: Start Lab, luego "AWS Details" → copiar las credenciales
#    y pegarlas en parcial3/aws-credentials (debajo de [learnerlab]). Guardar.
source parcial3/aws-env.sh                      # credenciales SOLO en esta terminal
aws sts get-caller-identity                     # debe mostrar la cuenta 891376990124

# 2) ¿Sigue la EC2? Si responde CREATE_COMPLETE, sáltate el deploy
aws cloudformation describe-stacks --stack-name AirlineP3 \
  --query 'Stacks[0].[StackStatus,Outputs[?OutputKey==`ApiUrl`].OutputValue]' --output text
# si no existe:  (cd parcial3/infra && ./deploy.sh)     ← ~5 min

# 3) Crear el stream y Firehose (cobran por hora: borrarlos al terminar, paso 5)
parcial3/infra/crear_stream.sh

# 4) Comprobar que la API ve el stream (el consumidor se reconecta solo en ~10 s)
API=http://44.200.115.10:8000          # usar la ApiUrl del paso 2
curl -s $API/health                    # "consumer" ya no debe mostrar last_error
```

Si la IP cambió, hay que actualizar `base_url` en `../parcial3-harness-estudiantes/config.yaml`.

### 5. Apagar al terminar

```bash
parcial3/infra/borrar_stream.sh                 # siempre
(cd parcial3/infra && ./deploy.sh destroy)      # solo cuando ya no se necesite la EC2
```

---

## 2. Correr el harness (la nota automática, 70 %)

```bash
cd ../parcial3-harness-estudiantes
source ../BD_parcial1/parcial3/aws-env.sh
.venv/bin/pytest                                # ~4 min → report.md y report.json
cp report.md report.json ../BD_parcial1/parcial3/
```

Solo una parte: `.venv/bin/pytest tests/test_1_stream.py` (R1–R4), `tests/test_2_star.py` (R5–R10)
o `tests/test_3_cost.py` (R11–R12). Para que R1–R10 pasen, el stream tiene que existir.

## 3. Probar sin AWS (no gasta nada)

```bash
cd parcial3/backend
.venv/bin/pytest                                                       # 5 pruebas unitarias
.venv/bin/python ../tools/verificar_estrella_local.py \
  --harness ../../../parcial3-harness-estudiantes                      # SQL de la estrella vs oráculo → "TODO OK"
```

Para levantar la API en local, con SQLite y un Kinesis simulado:

```bash
cd parcial3/backend
.venv/bin/moto_server -p 5005 &
export AWS_ENDPOINT_URL_KINESIS=http://127.0.0.1:5005 AWS_ACCESS_KEY_ID=x AWS_SECRET_ACCESS_KEY=x AWS_REGION=us-east-1
aws kinesis create-stream --stream-name airline-events --shard-count 1
KINESIS_STREAM=airline-events .venv/bin/python ../tools/correr_local.py   # API en http://127.0.0.1:8000
```

## 4. Frontend

- `$API/`: buscar vuelos, reservar y cancelar.
- `$API/manager`: panel gerencial en vivo (búsquedas, reservas, cancelaciones y conversión en 5/15/60 min) y botón de refrescar la estrella.

---

## 5. Lo que pide el profesor y cómo comprobarlo uno mismo

Preparación para las consultas de esta sección:

```bash
source parcial3/aws-env.sh
source parcial3/tools/athena_q.sh        # define q "SQL" → resultado + bytes escaneados
API=http://44.200.115.10:8000
B=s3://p3-airline-891376990124
```

### Bloque 1: eventos y vista en vivo (R1–R4)

**R1 (7 pts). Cada búsqueda, reserva y cancelación publica exactamente un evento válido.**
```bash
curl -s -X POST $API/admin/flights -H 'Content-Type: application/json' \
  -d '{"flight_id":"PRUEBA-1","route":"CTG-BOG","flight_date":"2026-12-20","capacity":5,"price_cents":250000}'
curl -s -H 'X-Session-Id: sesion-prueba' "$API/flights/search?origin=CTG&destination=BOG&date=2026-12-20"
curl -s -X POST $API/reservations -H 'Content-Type: application/json' \
  -d '{"flight_id":"PRUEBA-1","passenger_name":"Ana Prueba","fare_class":"ECONOMY"}'   # copiar reservation_id
curl -s -X POST $API/reservations/<reservation_id>/cancel     # 200; repetir → 409; id inventado → 404

# leer lo que llegó al stream en los últimos 2 minutos
IT=$(aws kinesis get-shard-iterator --stream-name airline-events --shard-id shardId-000000000000 \
     --shard-iterator-type AT_TIMESTAMP --timestamp $(date -d '-2 min' +%s) --query ShardIterator --output text)
aws kinesis get-records --shard-iterator "$IT" --limit 100 --query 'Records[].Data' --output text \
  | tr '\t' '\n' | while read -r d; do echo "$d" | base64 -d; echo; done
```
Qué revisar:
- Aparecen 3 eventos: `search_performed`, `reservation_created` y `reservation_cancelled`.
- Cada uno trae `event_id`, `event_ts` (UTC) y `schema_version: 1`.
- No aparece el nombre del pasajero.

**R2 (6 pts). Una ráfaga no pierde eventos y la API sigue rápida.**
- Revisar `curl -s $API/health`: `publisher.dropped` debe estar en 0.
- La prueba completa (200 búsquedas, 50 a la vez) es `pytest tests/test_1_stream.py -k burst`.

**R3 (7 pts). La vista en vivo refleja eventos nuevos en menos de 10 s y cuenta por hora del evento.**
```bash
curl -s "$API/analytics/live?window=5"; echo
curl -s -H 'X-Session-Id: s2' "$API/flights/search?origin=CTG&destination=BOG&date=2026-12-20" >/dev/null
sleep 3; curl -s "$API/analytics/live?window=5"; echo          # searches subió en 1
```
También se ve en `$API/manager`. Los eventos con fecha de 2025 (los del replay) no suman, porque la ventana usa `event_ts`.

**R4 (4 pts). Todos los eventos llegan a S3 en menos de 5 min.** Esperar 60–90 s, por el búfer de Firehose:
```bash
aws s3 ls $B/raw/events/ --recursive | tail -3
aws s3 cp $B/raw/events/<ruta-de-un-objeto> - | gunzip | head -3   # un JSON por línea
```

### Bloque 2: modelo estrella (R5–R10)

Primero hay que refrescar la estrella:
```bash
curl -s -X POST $API/admin/refresh-star; sleep 40; curl -s $API/admin/refresh-status
```
Debe responder `SUCCEEDED` en menos de 15 min (R8); normalmente tarda ~30 s.

**R5 (7 pts). Tablas en Glue con columnas, tipos, Parquet, partición por mes y `dim_date` enriquecida.**
```bash
aws glue get-tables --database-name airline_star --query 'TableList[].Name'
aws glue get-table --database-name airline_star --name fact_search \
  --query 'Table.[StorageDescriptor.Columns[].[Name,Type], PartitionKeys, StorageDescriptor.SerdeInfo.SerializationLibrary]'
aws glue get-partitions --database-name airline_star --table-name fact_search --query 'Partitions[].Values'
q "SELECT count(*), min(full_date), max(full_date) FROM dim_date"           # 1826 | 2023-01-01 | 2027-12-31
q "SELECT full_date, weekday_name, quarter, is_holiday, holiday_name, is_long_weekend
   FROM dim_date WHERE full_date BETWEEN DATE '2025-01-03' AND DATE '2025-01-07' ORDER BY 1"
```
En la segunda consulta, el lunes festivo 6 de enero (Reyes) hace que el sábado 4, el domingo 5 y el lunes 6 tengan `is_long_weekend = true`. El viernes 3 y el martes 7 quedan en `false`.

**R6 (5 pts). Integridad: claves únicas, sin huérfanos y una fila por evento.** Las tres columnas deben dar 0:
```bash
q "SELECT (SELECT count(*) - count(DISTINCT route_key) FROM dim_route) AS claves_repetidas,
          (SELECT count(*) FROM fact_booking_event f LEFT JOIN dim_route r ON f.route_key = r.route_key
           WHERE r.route_key IS NULL) AS huerfanos,
          (SELECT count(*) - count(DISTINCT event_id) FROM fact_search) AS eventos_repetidos"
```

**R7 (11 pts). Las preguntas Q1–Q4 y Q6–Q8 dan los números correctos.** Por ejemplo, Q1 (ingreso neto por mes y clase):
```bash
q "SELECT d.year_month, c.fare_class, sum(f.revenue_cents)/100.0 AS ingreso_neto
   FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
   JOIN dim_fare_class c ON f.fare_class_key = c.fare_class_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1, 2 ORDER BY 1, 2"
```
Las demás preguntas:
```bash
# Q2: reservas, cancelaciones y tasa de cancelación por ruta
q "SELECT r.route, sum(f.bookings) AS reservas, sum(f.cancellations) AS cancelaciones,
          round(1.0*sum(f.cancellations)/sum(f.bookings), 4) AS tasa
   FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1 ORDER BY 1"
# Q3: reservas por día de la semana, de lunes a domingo
q "SELECT d.weekday, d.weekday_name, sum(f.bookings) AS reservas
   FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1, 2 ORDER BY 1"
# Q4: las 10 rutas con más ingreso neto
q "SELECT r.route, sum(f.revenue_cents)/100.0 AS ingreso
   FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
# Q6: conversión por ruta (los dos hechos comparten dim_route)
q "WITH s AS (SELECT r.route, sum(f.searches) b FROM fact_search f JOIN dim_route r ON f.route_key = r.route_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1),
        k AS (SELECT r.route, sum(f.bookings) v FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1)
   SELECT s.route, s.b AS busquedas, k.v AS reservas, round(1.0*k.v/s.b, 4) AS conversion
   FROM s JOIN k ON s.route = k.route ORDER BY 1"
# Q7: festivos frente a los demás días (los dos hechos comparten dim_date)
q "WITH s AS (SELECT d.is_holiday h, sum(f.searches) b FROM fact_search f JOIN dim_date d ON f.date_key = d.date_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1),
        k AS (SELECT d.is_holiday h, sum(f.bookings) v FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
              WHERE f.event_id LIKE 'rp-%' GROUP BY 1)
   SELECT s.h AS festivo, s.b AS busquedas, k.v AS reservas FROM s JOIN k ON s.h = k.h"
# Q8: reservas en días de puente festivo
q "SELECT d.is_long_weekend, sum(f.bookings) AS reservas
   FROM fact_booking_event f JOIN dim_date d ON f.date_key = d.date_key
   WHERE f.event_id LIKE 'rp-%' GROUP BY 1"
```
Para revisar que los resultados cuadran: en Q3 y Q8 las reservas suman 2.600, y en Q7 las búsquedas suman 17.000.
La comparación contra el valor esperado exacto solo la hace el harness (`pytest tests/test_2_star.py -k q`), o en local `verificar_estrella_local.py`.

**R8 (6 pts). Se quitan duplicados, los eventos tardíos usan su propia fecha y el refresco termina a tiempo.**
```bash
q "SELECT event_type, count(*) FROM fact_booking_event WHERE event_id LIKE 'rp-%' GROUP BY 1"  # 2600 y 312
q "SELECT month, count(*) FROM fact_search WHERE event_id LIKE 'rp-%' GROUP BY 1 ORDER BY 1"   # 5824 / 5146 / 6030
```
El harness envía 20.509 registros (con un 3 % de duplicados), y en la estrella quedan exactamente 17.000 búsquedas, 2.600 reservas y 312 cancelaciones.

**R9 (8 pts). `dim_route` es SCD tipo 2 y los hechos usan la versión vigente en la fecha del evento.**
```bash
q "SELECT route, route_category, valid_from, valid_to, is_current FROM dim_route
   WHERE route IN ('CTG-BOG','CUC-SMR','ADZ-BAQ') ORDER BY route, valid_from"
q "SELECT f.month, r.route_category, sum(f.revenue_cents)/100.0 FROM fact_booking_event f
   JOIN dim_route r ON f.route_key = r.route_key WHERE f.event_id LIKE 'rp-%' GROUP BY 1, 2 ORDER BY 1, 2"   # Q5
```
Las tres rutas deben tener dos versiones que cambian el 2025-02-01. Solo la última tiene `is_current = true` y `valid_to = 9999-12-31`.

**R10 (4 pts). Filtrar por mes no escanea todo, y el workgroup tiene un tope de 1 GB por consulta.**
```bash
q "SELECT sum(results_count) FROM fact_search WHERE month = '2025-02'"     # ~3.400 bytes
q "SELECT sum(results_count) FROM fact_search"                             # ~11.200 bytes  → razón ≈ 0,3 (límite 0,6)
aws athena get-work-group --work-group airline-p3 --query 'WorkGroup.Configuration.BytesScannedCutoffPerQuery'   # 1000000000
```
No hay que usar `count(*)` para esta prueba: Athena lo responde con metadatos y escanea 0 bytes.

### Bloque 3: costo y arquitectura (R11–R12)

**R11 (3 pts). Stream mínimo: provisionado, 1 shard, retención de 24 h y sin enhanced fan-out.**
```bash
aws kinesis describe-stream-summary --stream-name airline-events \
  --query 'StreamDescriptionSummary.[StreamModeDetails.StreamMode,OpenShardCount,RetentionPeriodHours,ConsumerCount]'
# → PROVISIONED  1  24  0
```

**R12 (2 pts). La proyección de costos es como máximo 1,5 veces la referencia del profesor, nunca supera US$50 e incluye Kinesis, S3 y Athena.**
```bash
cat parcial3/cost_projection.yaml        # total US$18,15/mes
```

---

## 6. Lo que no revisa el harness (30 % de la nota)

| Pide el enunciado | Dónde está | Cómo comprobarlo |
|---|---|---|
| Sección 5 del enunciado: qué va al stream y qué no; *outbox* para no perder reservas | Documento final §6.1 | Leer el PDF (las decisiones están en su capítulo 6): cada una cita un requisito y un pilar |
| Dos caminos: vista en vivo desde el stream, estrella refrescada cada pocos minutos | §6.2 | Mismo PDF |
| Landing zone (Firehose vs. consumidor propio), con latencia y costo | §6.3 | Mismo PDF |
| Diseño de la estrella: medida, hecho y dimensiones por pregunta; matriz bus; granos; dimensiones conformadas; atributos extra | §5 y §6.4, diagrama `08-modelo-estrella-parcial3` | Comparar el diagrama con `aws glue get-table` |
| ETL: comparar Athena CTAS, Lambda+DuckDB y Glue job (costo por corrida y por mes, arranque, crecimiento, operación, idempotencia) | §6.5 | Mismo PDF |
| SCD tipo 2: por qué, qué fallaría con tipo 1, cómo se elige la versión para un evento tardío | §6.6 | Consulta de R9 |
| Eventos sucios: deduplicar, tardíos y desordenados | §6.7 | Consulta de R8 |
| Costo y ciclo de vida: qué existe siempre y qué solo al probar; tabla de servicios; narrativa | §6.8, §6.9, §8 y `cost_projection.yaml` | Mismo PDF |
| Sección 6 del enunciado: resultados del harness | §9 y `report.md` | 70/70 |
| Entregables: backend, consumidor, ETL, scripts para crear y borrar el stream, `config.yaml` sin credenciales, `cost_projection.yaml`, `report.md` y apéndice de prompts | `parcial3/` (apéndice de IA en §12) | `git ls-files parcial3` (no deben aparecer `aws-credentials` ni `.pem`) |
| Diagramas que coinciden con lo desplegado | `docs/diagrams/07-*` | Comparar con la consola de AWS |
| Defensa oral (eliminatoria por bloque) | `docs/DEFENSA.md` | Que cada integrante explique un bloque y haga un cambio en vivo |

El PDF que se entrega es `parcial3/docs/PARCIAL3-ENTREGA.pdf`. Para regenerarlo después de editar `documento-final.html`:
`cd parcial3/docs && .venv/bin/python generar_pdf.py`.
