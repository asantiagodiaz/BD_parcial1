# Guía para la defensa oral — Parcial 3

La defensa es **eliminatoria por bloque**: si no sabemos sostener una decisión de un bloque, se pierden también los puntos que el harness ya dio en ese bloque. Los dos debemos poder responder cualquier pregunta. Los bloques son:

| Bloque | Requisitos | Puntos en juego | Archivos clave |
|---|---|---|---|
| A. Eventos y vista en vivo | R1–R4 | 24 | `backend/app/events.py`, `backend/app/live.py`, `backend/app/main.py`, `infra/crear_stream.sh` |
| B. Modelo estrella | R5–R10 | 41 | `backend/app/star_sql.py`, `backend/app/star.py`, `tools/verificar_estrella_local.py` |
| C. Costo y arquitectura | R11–R12 | 5 | `cost_projection.yaml`, `infra/lib/airline-p3-stack.ts`, `infra/*.sh` |

---

## 1. El recorrido de un evento (para explicarlo de memoria)

1. El cliente reserva → `POST /reservations` → un `UPDATE ... WHERE seats_sold < capacity RETURNING route, flight_date, price_cents` y un `INSERT`, en la misma transacción.
2. **Después del commit**: `publisher.publish_sync(...)` → `PutRecord` con clave de partición `flight_id` (hasta 5 intentos).
3. El evento queda en el shard (retención de 24 h).
4. **Camino rápido**: el hilo `live-consumer` hace `GetRecords` cada 1 s, guarda `{event_id: (tipo, event_ts)}` y `GET /analytics/live` cuenta los eventos con `event_ts` dentro de la ventana.
5. **Camino analítico**: Firehose lee el shard, agrega `\n` y cada 60 s escribe un `.gz` en `s3://…/raw/events/AAAA/MM/DD/HH/`.
6. `POST /admin/refresh-star` (o el temporizador de 10 min) → `star.py` sube `ref/*.csv`, corre el DDL y después, para cada tabla, `DROP TABLE` + CTAS a `star/<tabla>/<run_id>/`, y borra el prefijo viejo.
7. Athena responde Q1–Q8 haciendo join de los hechos con las dimensiones.

Una búsqueda sigue el mismo camino, salvo el paso 2: `publish_async` la encola, y el hilo `search-publisher` la envía en un lote con `PutRecords` (clave `session_id`).

---

## 2. Bloque A — Eventos y vista en vivo (R1–R4)

**¿Por qué las búsquedas son asíncronas y las reservas síncronas?**
Una búsqueda perdida no cambia nada y una búsqueda lenta sí molesta al cliente (R2: p95 ≤ 1 s). Una reserva perdida descuadra los ingresos, así que se publica dentro de la petición, pero después del commit, para no publicar nunca algo que no se guardó.

**¿Qué pasa si Kinesis falla?**
- Búsquedas: el hilo reintenta con espera creciente (hasta 8 veces, solo los registros que fallaron). Si se agota, las descarta y suma `dropped`, que se ve en `/health`. La API sigue respondiendo.
- Reservas: 5 intentos. Si todos fallan, se registra el error y la reserva queda guardada sin evento. Ese es el hueco que cerraría el patrón outbox.

**Explique el patrón outbox.**
En la misma transacción que la reserva se inserta `outbox(event_id, payload, published_at NULL)`. Un publicador aparte lee las filas pendientes, las envía a Kinesis y marca `published_at`. Si se cae antes de marcar, la reenvía con el mismo `event_id` (entrega "al menos una vez"). Los duplicados se eliminan en la estrella por `event_id`.

**¿Cómo evita duplicar eventos en la ráfaga de R2?**
`PutRecords` puede fallar a medias. Se reintentan solo los registros con `ErrorCode`, así que los que ya entraron no se reenvían.

**¿Por qué la clave de partición es `session_id` / `flight_id`?**
Lo pide el contrato. Además, con varios shards, `session_id` reparte las búsquedas y `flight_id` garantiza que la creación y la cancelación de una reserva queden en el mismo shard y en orden.

**¿Por qué la vista en vivo no consulta Athena?**
Athena lee S3, que llega con el retraso del búfer de Firehose (~60 s). Además tarda segundos y factura al menos 10 MB por consulta. R3 pide reflejar un evento en menos de 10 s; medimos 1,7 s.

**¿Cómo sabe que no cuenta el replay viejo?**
Cuenta por `event_ts`, no por la hora de llegada. El replay trae fechas de 2025, y `LiveCounter.add` ni siquiera guarda los eventos de más de 60 minutos.

**¿Qué pasa si se reinicia la API?**
El consumidor arranca con `AT_TIMESTAMP` desde hace 60 minutos y reconstruye los contadores. Al deduplicar por `event_id`, no cuenta doble.

**¿Por qué lee cada 1 s y no más seguido?**
Un shard admite 5 `GetRecords` por segundo compartidas. Firehose usa 1, el harness hasta 4 mientras verifica, y nosotros 1.

**¿Por qué un solo worker de uvicorn?**
Los contadores viven en memoria del proceso. Con 4 workers habría 4 consumidores y cada petición vería el contador de un worker distinto, aunque en realidad cada uno lee el shard completo. Para escalar, los contadores irían a un almacén compartido.

**¿Por qué Firehose y no escribir a S3 desde el consumidor?**
Sería gratis, pero ataría la landing zone (la copia durable) a la disponibilidad de la EC2. Firehose es gestionado: reintenta y separa los errores. Cuesta unos US$0,05 al mes.

**¿Para qué sirve `AppendDelimiterToRecord`?**
El harness escribe JSON sin `\n`. Sin el delimitador, el archivo queda `{...}{...}` y la SerDe JSON de Athena (un objeto por línea) no lo puede leer.

---

## 3. Bloque B — Modelo estrella (R5–R10)

**¿Cuál es el grano de cada hecho?**
`fact_search`: una fila por búsqueda distinta. `fact_booking_event`: una fila por evento de reserva distinto, sea creación o cancelación.

**¿Por qué la cancelación es una fila y no un UPDATE?**
Los hechos quedan inmutables, igual que la landing zone, y el ingreso neto es un `SUM(revenue_cents)`. Cada reverso queda en su fecha real (Q1 por mes).

**¿Qué es una dimensión conformada? ¿Cuáles tiene?**
Una dimensión compartida por varios hechos con las mismas claves. Aquí son `dim_date` y `dim_route`, y son las que permiten Q6 (conversión por ruta) y Q7 (festivos frente a otros días).

**¿Qué atributos agregaron y por qué?**
Ver la sección 5.2 del documento. Por ejemplo, `is_business_day` y `year_month` en `dim_date`, `version` en `dim_route`, `cabin_rank` en `dim_fare_class`, los miembros 0 "UNKNOWN" y `days_to_travel` en `fact_search`.

**¿Cómo se calcula `is_long_weekend`?**
Un lunes o viernes, si es festivo. Un sábado, si el día anterior (viernes) o el lunes siguiente (+2) es festivo. Un domingo, si el viernes (−2) o el día siguiente (lunes) es festivo. En SQL son 5 `LEFT JOIN` a los festivos con desplazamientos de −2 a +2 días.

**¿Cómo deduplican?**
`ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_ts)` y se queda la fila 1.

**¿Qué cambia un evento tardío?**
Nada en el resultado: `date_key` y `month` salen de `event_ts`, y cada refresco relee toda la landing zone. Por eso no se filtra por la carpeta de S3, que corresponde a la hora de llegada.

**¿Por qué SCD tipo 2? ¿Qué daría mal una tipo 1?**
Q5 pide la categoría vigente el día del evento. Con tipo 1, el ingreso de enero de 2025 de CTG-BOG saldría como REGIONAL (era TRUNK), y el de CUC-SMR y ADZ-BAQ como TRUNK (eran REGIONAL).

**¿Cómo se elige la versión de la ruta?**
Join as-of: `event_date >= valid_from AND event_date < valid_to`. `valid_to` es la `effective_date` siguiente, que se obtiene con `LEAD(...)`, o 9999-12-31 para la vigente.

**¿Por qué Athena CTAS y no Glue o Lambda?**
Cuesta US$0,0004 por corrida frente a US$0,03 de Glue, no tiene arranque, Glue registra las particiones solo y es idempotente por diseño. Se cambiaría a un proceso incremental (o a Iceberg con MERGE) si la reconstrucción completa escaneara decenas de GB.

**¿Por qué es idempotente?**
Nunca hay `INSERT INTO` sobre lo anterior: cada corrida hace `DROP` + CTAS a un prefijo nuevo y borra el viejo. Correr dos veces el mismo lote da las mismas filas.

**¿Qué pasa si piden un refresco mientras otro corre?**
`StarJob.request()` marca `_rerun`. El estado sigue en RUNNING hasta que termine una corrida que empezó después del pedido.

**¿Cómo se cumple R10?**
Los hechos están particionados por `month`, así que `WHERE month = '2025-01'` lee solo esa carpeta (34 % de los bytes). El workgroup `airline-p3` tiene `BytesScannedCutoffPerQuery = 1 GB`.

**¿Por qué `EnforceWorkGroupConfiguration = false`?**
Con `true`, Athena rechaza los CTAS con `external_location`. El tope de bytes se aplica igual.

**¿Qué pasa con una ruta desconocida o una fecha fuera de 2023–2027?**
- Ruta o clase desconocida: van al miembro 0, así que no quedan huérfanas (R6).
- Fecha fuera del rango: se descarta del hecho. No se agrega una fila "desconocida" a `dim_date` porque R5 exige exactamente un día por fila de 2023 a 2027.

---

## 4. Bloque C — Costo y arquitectura (R11–R12)

**¿Qué existe siempre y qué solo mientras se prueba?**
Siempre: la EC2, el bucket, la base de Glue y el workgroup. Solo mientras se prueba: el stream y Firehose (`crear_stream.sh` / `borrar_stream.sh`).

**¿Por qué provisionado y no on-demand?**
On-demand cobra por stream-hora más por GB, y a este volumen sale más caro que un shard provisionado. R11 además lo exige.

**¿Por qué no hay consumidores EFO?**
*Enhanced fan-out* cuesta por consumidor-hora y por GB leído. Con tres lectores y 5 lecturas por segundo compartidas nos alcanza.

**Desglose del costo.**
EC2 15,18 + EBS 1,60 + Kinesis 0,92 + Firehose 0,05 + S3 0,10 + Athena 0,30 + Glue 0 = **US$18,15**. El 92 % es la EC2 con su disco.

**¿Qué ahorra PostgreSQL en la EC2?**
Unos US$14,70 al mes frente a una RDS db.t3.micro. A cambio se pierden los respaldos gestionados, que en producción reemplazaríamos con snapshots de EBS.

**¿Y si el volumen se multiplica por 10?**
Unos US$21. Crecen Firehose, S3 y Athena; el shard aguanta 1.000 registros por segundo.

**Sostenibilidad.**
Hay una sola instancia, los servicios serverless solo consumen cuando hay trabajo, el stream existe solo durante las pruebas, el refresco se salta si no hay datos nuevos, los datos van en Parquet comprimido y particionado, y los temporales expiran solos.

---

## 5. Cambios en vivo que puede pedir el profesor

Procedimiento general para cualquier cambio en la estrella:
1. Editar `backend/app/star_sql.py`.
2. Verificar en local: `cd parcial3/backend && .venv/bin/python ../tools/verificar_estrella_local.py --harness ../../../parcial3-harness-estudiantes`.
3. Subir el código: `source parcial3/aws-env.sh && parcial3/infra/actualizar_codigo.sh`.
4. Lanzar `POST /admin/refresh-star` y esperar SUCCEEDED (unos 30 s).
5. Consultar en Athena y, si hace falta, correr el harness.

Las columnas extra están permitidas por el contrato, así que **agregar columnas no rompe ninguna prueba del harness**. Quitar o renombrar una columna del contrato sí rompe R5.

### 5.1 "Agreguen una medida a un hecho"
*Ejemplo:* ingreso bruto (sin restar cancelaciones) en `fact_booking_event`.
- **Pipeline:** solo `select_fact_booking_event` en `star_sql.py`:
  ```sql
  CAST(CASE WHEN e.event_type = 'reservation_created' THEN e.price_cents ELSE 0 END AS bigint) AS gross_revenue_cents,
  ```
  Va antes de `substr(e.event_ts, 1, 7) AS month`, porque la columna de partición debe quedar al final.
- **Tablas:** `fact_booking_event` gana una columna. Glue se actualiza solo con el CTAS. Las dimensiones no cambian.
- **Pruebas:** el harness no se afecta. Se puede agregar una comprobación en `verificar_estrella_local.py`.
- **Si la medida necesita un dato que el evento no trae** (por ejemplo, el número de pasajeros), también cambian el contrato del evento (`events.py`), la tabla `raw_events` (DDL en `star_sql.ddl`) y la API. Los eventos viejos tendrían ese campo en NULL, y habría que decidir si llevan `COALESCE` y si se sube `schema_version`.

*Otro ejemplo, en `fact_search`:* `CAST(results_count = 0 AS integer) AS searches_without_results`, para medir búsquedas sin oferta.

### 5.2 "Agreguen un atributo a una dimensión"
*Ejemplo:* temporada alta en `dim_date` (diciembre, enero, junio, julio y Semana Santa).
- **Pipeline:** en `select_dim_date`:
  ```sql
  month(day) IN (1, 6, 7, 12) AS is_high_season,
  ```
- **Tablas:** solo `dim_date`. Los hechos no cambian: el atributo se alcanza por `date_key`, sin tocar ningún hecho. Esa es la ventaja de la estrella.
- **Pruebas:** R5 compara solo las columnas del contrato, así que no se afecta.

*Ejemplo en `dim_route`:* indicar si la ruta pasa por BOG (`origin = 'BOG' OR destination = 'BOG' AS touches_hub`). Si el atributo cambia en el tiempo y se quiere su historia, necesita su propio historial y entra en la SCD tipo 2 como `route_category`: con una nueva versión cada vez que cambie.

### 5.3 "Agreguen una nueva pregunta de negocio"
Primero se ubica en la matriz bus: ¿qué medida y qué dimensión necesita? Si ambas existen, es solo una consulta. Si no, se aplica 5.1 o 5.2. Ejemplo, "anticipación promedio de las búsquedas por ruta": `SELECT r.route, AVG(f.days_to_travel) FROM fact_search f JOIN dim_route r ON f.route_key = r.route_key GROUP BY 1`. No requiere ningún cambio.

### 5.4 "Cambien la ventana de la vista en vivo" o "agreguen un contador"
- Ventana máxima: `LIVE_MAX_WINDOW_MINUTES` en `.env` (por defecto 60).
- Nuevo contador (por ejemplo, ingresos en vivo): en `live.py`, guardar `price_cents` en `_events` y sumarlo en `counts()`; agregar el campo a `LiveOut` en `schemas.py`. El camino analítico no cambia.

### 5.5 "Conviertan la categoría en tipo 1" (pregunta trampa)
Se haría con `WHERE is_current` en `select_dim_route`, dejando una fila por ruta. Hay que decir que **rompe Q5 y R9**: ese es justo el error que explicamos en el bloque B.

### 5.6 "¿Qué pasa si llega un evento duplicado con otra hora?"
La deduplicación se queda con el de menor `event_ts` (`ORDER BY event_ts`). Según el contrato, un reintento reutiliza el mismo `event_id` y el mismo contenido, así que en la práctica son idénticos.

---

## 6. Comandos útiles durante la defensa

```bash
source parcial3/aws-env.sh                        # credenciales solo en esta terminal
parcial3/infra/crear_stream.sh                    # antes de probar (cobra por hora)
curl -s http://IP:8000/health                     # registros leídos por el consumidor y errores
curl -s "http://IP:8000/analytics/live?window=5"
curl -s -XPOST http://IP:8000/admin/refresh-star; curl -s http://IP:8000/admin/refresh-status
parcial3/infra/actualizar_codigo.sh               # subir un cambio sin recrear la EC2
cd ../parcial3-harness-estudiantes && .venv/bin/pytest   # harness completo (~4 min)
parcial3/infra/borrar_stream.sh                   # al terminar
```

Si el Lab se reinició: la IP de la EC2 cambia (ver la salida `ApiUrl` del stack) y hay que actualizar `backend.base_url` en el `config.yaml` del harness. PostgreSQL conserva los datos en el disco, y la estrella y la landing zone siguen en S3.
