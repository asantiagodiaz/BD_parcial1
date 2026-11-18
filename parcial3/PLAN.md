# Plan — Parcial 3 (eventos, vista en vivo y modelo estrella)

- Enunciado: `parcial_3/parcial32026-2-EN.pdf`
- Harness: `../parcial3-harness-estudiantes/` (extraído del zip, fuera del repo; tiene su propio `.venv`)
- **Semilla 963.** **PostgreSQL en la misma EC2** (sin RDS).
- Base: el sistema del Parcial 2 (FastAPI + React en EC2, S3/Glue/Athena).

## Datos de la semilla 963 (salen del harness, no son decisiones)

| Dato | Valor |
|---|---|
| Rutas (9) | CUC-BGA, CTG-BOG, CUC-SMR, ADZ-CTG, PSO-SMR, SMR-BAQ, ADZ-BAQ, PSO-CUC, BGA-BOG (las mismas del P2) |
| Rutas con 2 versiones (SCD2, cambio el 2025-02-01) | CTG-BOG (TRUNK→REGIONAL), CUC-SMR (REGIONAL→TRUNK), ADZ-BAQ (REGIONAL→TRUNK) |
| Replay | 20.509 registros enviados → 19.912 eventos distintos (17.000 búsquedas, 2.600 reservas, 312 cancelaciones) |
| Volumen del replay | ~5 MB de JSON; búsquedas por mes: 2025-01 = 5.824, 2025-02 = 5.146, 2025-03 = 6.030 |
| Festivos | `holidays_ref.csv`: 91 festivos colombianos 2023–2027 |

## Lo que revelan los tests (y cómo afecta el diseño)

1. **Un evento por registro de Kinesis.** El harness hace `json.loads(record.Data)` registro por registro, así que nunca se agrupan varios eventos en un mismo registro.
2. **El replay llega sin salto de línea.** El harness escribe directo al stream con `json.dumps` compacto. Firehose concatenaría `}{`, y la SerDe JSON de Athena exige un objeto por línea. Por eso Firehose tiene que llevar el procesador **AppendDelimiterToRecord**, que no necesita Lambda. R4 pasaría igual, porque busca los `event_id` con una regex, pero el ETL fallaría.
3. **Límite de lecturas del shard: 5 GetRecords/s, compartidas.** El harness lee cada 0,25 s, Firehose cada 1 s y nuestro consumidor también. Nuestro consumidor sondea cada 1 s para no provocar *throttling*. boto3 ya reintenta `ProvisionedThroughputExceeded`.
4. **R2 pide exactamente 200 eventos.** El publicador reintenta solo los registros que fallaron dentro del lote, y no todo el lote, para no duplicar. Los timeouts del cliente quedan holgados.
5. **R3 compara deltas exactos (+10 / +3 / +1) en 10 s** y después repite 20.000 eventos viejos que no deben contarse. El conteo se hace por `event_ts` y se deduplica por `event_id` dentro de la ventana.
6. **R5 revisa los tipos en Glue:** `date` para `full_date`, `valid_from` y `valid_to`; `boolean` para las banderas; enteros (cualquier tamaño). Las particiones deben estar **registradas en Glue** (con CTAS `partitioned_by` quedan registradas). `month` es string `YYYY-MM`.
7. **R9** compara cada versión con el historial: `valid_to` = `effective_date` de la versión siguiente, o `9999-12-31`; `is_current` solo en la última.
8. **R12:** en la copia del estudiante la referencia es US$60, así que el límite es min(60 × 1,5; 50) = US$50. El profesor pone su propio valor, así que conviene quedar lo más bajo posible. Deben aparecer las líneas Kinesis, S3 y Athena.
9. Los tests del stream crean eventos con fecha de hoy (2026-11) y el replay trae fechas de 2025. Todo cae dentro de `dim_date` 2023–2027, y las rutas de esos eventos son las 9 conocidas.

## Arquitectura

```
API FastAPI (EC2, 1 worker) ──PutRecords──▶ Kinesis (1 shard, provisionado, 24 h)
  │  búsquedas: cola en memoria + hilo        │                       │
  │  reservas: síncrono tras el commit        │                       ▼
  │                                           │       Firehose (búfer 60 s, delimitador \n, gzip)
  │  hilo consumidor (GetRecords cada 1 s) ◀──┘                       ▼
  │  contadores por event_ts, dedup por id                S3 raw/events/AAAA/MM/DD/HH/
  └─ GET /analytics/live                                              │
                                                                      ▼
  POST /admin/refresh-star (+ temporizador cada 10 min) ─▶ Athena CTAS ─▶ S3 star/<tabla>/<run>/ (Parquet)
                                                                      │
                                              Glue Data Catalog (3 dims + 2 facts) ─▶ Athena (workgroup ≤ 1 GB)
```

| Decisión | Elección | Por qué |
|---|---|---|
| Publicar búsquedas | Cola en memoria + hilo que envía con `PutRecords` en lotes | No frena la API (R2); perder una búsqueda es aceptable |
| Publicar reservas | `PutRecord` síncrono después del commit, con reintentos | Es una transacción; en producción se usaría *outbox* (solo se describe) |
| Vista en vivo | Hilo consumidor dentro del backend | Latencia de segundos, US$0 extra; Athena es lento y cobra por consulta |
| Landing zone | Firehose | Gestionado, < 5 min (R4), centavos al mes; es consumidor estándar, no EFO (R11) |
| ETL | Athena CTAS con reconstrucción completa | Sin servidores ni arranque en frío, idempotente, unos 10 MB escaneados por consulta |
| `dim_route` | SCD2 + miembro "desconocido" (`route_key = 0`) | R9 y Q5; ningún hecho huérfano (R6) |
| Particiones | `fact_search` por `month` (y también `fact_booking_event`) | R10 |
| Base de datos | PostgreSQL en la misma EC2 | Unos US$14/mes menos que RDS (R12) |

En el documento se comparan las alternativas: consumidor propio a S3 frente a Firehose, y Lambda + DuckDB o un Glue job frente a Athena CTAS.

## Fases

### Fase 0 — Insumos ✅
- [x] Harness extraído y leído; `ref/` generado con la semilla 963.
- [x] Crear `parcial3/` con la estructura de `parcial2/` (copiar backend/frontend/infra, mover el PDF y el zip a `parcial3/docs/`, copiar `ref/`).

### Fase 1 — Entrega parcial (antes de construir)
- [x] Borrador de la sección 5 (los 7 bloques de decisiones, cada uno con requisito y pilar).
- [x] Diagrama del modelo estrella con granos + matriz bus (Q1–Q8 × dimensiones). (`docs/diagrams/08-modelo-estrella-parcial3.png`)
- [x] Diagrama de arquitectura (`docs/diagrams/07-arquitectura-aws-parcial3.*`, mismo motor que el P2)
- [x] Primera `cost_projection.yaml`.

### Fase 2 — Infraestructura
- [x] `crear_stream.sh` / `borrar_stream.sh`: Kinesis (1 shard) + Firehose. Se crea al empezar cada sesión y se borra al terminar.
- [x] Bucket: `raw/events/`, `ref/`, `star/`, `athena-results/`; base Glue `airline_star`; workgroup con `BytesScannedCutoffPerQuery` ≤ 1 GB.
- [x] CDK adaptado: EC2 con PostgreSQL local (sin RDS) y variables de entorno del stream.

### Fase 3 — Backend
- [x] `events.py`: sobre A.1 (`event_id` UUID, `event_ts` UTC, `schema_version` 1, clave de partición, sin datos personales).
- [x] `events.py` (clase `Publisher`): cola y hilo de lotes para búsquedas; envío síncrono con reintentos para reservas.
- [x] `GET /flights/search` lee `X-Session-Id` (si no viene, genera uno).
- [x] `POST /reservations` publica después del commit; nuevo `POST /reservations/{id}/cancel` (200 / 404 / 409, libera el asiento).
- [x] `live.py` + `GET /analytics/live?window=5`.
- [x] `star.py` + `star_sql.py`: `POST /admin/refresh-star`, `GET /admin/refresh-status`, candado contra corridas simultáneas y temporizador periódico.

### Fase 4 — ETL de la estrella (SQL en Athena)
- [x] Tablas externas: `raw_events` (JSON, gzip) y los 3 CSV de `ref/`.
- [x] `dim_date` con `sequence()`: día de la semana, nombre, trimestre, festivo + nombre, fin de semana largo (misma regla que el oráculo).
- [x] `dim_route` SCD2 con `LEAD(effective_date)`, más el miembro desconocido; `dim_fare_class`.
- [x] Hechos: `ROW_NUMBER() OVER (PARTITION BY event_id)`, fecha por `event_ts`, join as-of `valid_from <= fecha < valid_to`.
- [x] Idempotencia: cada corrida escribe en un prefijo nuevo, `DROP` + CTAS y luego se borra el prefijo anterior.
- [x] Verificación local del SQL equivalente con DuckDB contra `StarTruth` (Q1–Q8, R8, R9) antes de pasar a AWS.

### Fase 5 — Despliegue y harness
- [x] `config.yaml` del harness (sin credenciales), desplegar, `pytest`, iterar hasta 70/70, guardar `report.md`. (**70/70** el 2026-11-18)
- [x] Borrar el stream y Firehose al terminar cada sesión.

### Fase 6 — Documento final
- [x] Secciones 5 y 6, tabla de servicios, narrativa de costos, pilares Well-Architected (`docs/documento-final.html` → `docs/PARCIAL3-ENTREGA.pdf`).
- [x] `BITACORA.md`, `CHECKLIST.md`, apéndice de prompts, PDF de entrega.
- [x] Guía de defensa por bloques: `docs/DEFENSA.md` (falta practicarla en equipo).

## Riesgos
- Que el Learner Lab no permita Firehose con `LabRole`. Plan B: el mismo hilo consumidor escribe lotes en S3 cada 60 s.
- Que la ventana de 5 min "suelte" eventos viejos durante R3 y descuadre los deltas. Es poco probable, porque R1 y R2 ocurren menos de 2 min antes.
- Que el shard (US$0,015/h) quede encendido por olvido: el script de borrado va en el flujo de cada sesión.
