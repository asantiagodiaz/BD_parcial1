# Bitácora — Parcial 3

Registro de lo que se hizo, los datos de la semilla y el porqué de cada decisión.
Última actualización: 2026-11-18.

---

## 1. Datos del equipo (semilla 963)

Todo sale de la semilla (`airline_data/params.py` y `events.py` del harness):

| Dato | Valor |
|---|---|
| Rutas (9) | CUC-BGA, CTG-BOG, CUC-SMR, ADZ-CTG, PSO-SMR, SMR-BAQ, ADZ-BAQ, PSO-CUC, BGA-BOG |
| Cambian de categoría el 2025-02-01 | CTG-BOG (TRUNK→REGIONAL), CUC-SMR (REGIONAL→TRUNK), ADZ-BAQ (REGIONAL→TRUNK) |
| Replay del harness | 20.509 registros → 19.912 eventos distintos: 17.000 búsquedas, 2.600 reservas, 312 cancelaciones |
| Fechas del replay | 2025-01-01 a 2025-03-31 (búsquedas: ene 5.824, feb 5.146, mar 6.030) |
| Festivos | 91 festivos colombianos 2023–2027 (`ref/holidays_ref.csv`) |

Los archivos `ref/*.csv` se generaron con `python -m airline_data.generate_p3 --seed 963 --out ref/` y se versionan en el repo. El refresco de la estrella los sube a S3 en cada corrida.

---

## 2. Qué se construyó (carpeta `parcial3/`)

El Parcial 2 queda intacto en `parcial2/`. El Parcial 3 parte de una copia de su backend, frontend e infraestructura.

| Pieza | Archivos | Estado |
|---|---|---|
| Eventos y publicación | `backend/app/events.py` | Hecho. R1 y R2 pasan en AWS |
| Cancelación | `backend/app/main.py` | Hecho. 200 / 409 / 404, libera el asiento |
| Vista en vivo | `backend/app/live.py` | Hecho. R3 pasa en AWS |
| ETL de la estrella | `backend/app/star_sql.py`, `backend/app/star.py` | Hecho. R5–R10 pasan en AWS (refresco en 31 s) |
| Infraestructura | `infra/` (CDK + `crear_stream.sh` / `borrar_stream.sh` + `actualizar_codigo.sh`) | Desplegada en el Learner Lab. R4 y R11 pasan |
| Frontend | `frontend/` | Botón de cancelar y panel gerencial en vivo |
| Costos | `cost_projection.yaml` | US$18,15/mes. R12 pasa |
| Documento | `docs/seccion5-borrador.md` | Borrador de la entrega parcial |

---

## 3. Decisiones y por qué

Resumen. La justificación completa, con requisitos y pilares, está en `docs/seccion5-borrador.md`.

### 3.1 Dos formas de publicar
- **Búsquedas**: se encolan en memoria y un hilo las envía con `PutRecords` en lotes de hasta 500. Solo se reintentan los registros que fallaron, para no duplicar (R2 pide exactamente 200). La petición nunca espera a Kinesis.
- **Reservas y cancelaciones**: `PutRecord` síncrono **después del commit**, con 5 reintentos. Se evita así publicar una reserva que no quedó guardada. En producción se usaría el patrón *outbox* (descrito, no implementado).

### 3.2 Vista en vivo dentro de la API
- Un hilo del mismo proceso lee el único shard cada 1 s. Hay un solo worker de uvicorn, así que los contadores viven en ese proceso.
- Guarda una hora de eventos por `event_id` (deduplica) y cuenta por `event_ts` (el replay de 2025 no suma).
- Al arrancar lee con `AT_TIMESTAMP` desde hace una hora: un reinicio no deja la vista en cero.
- Por qué cada 1 s: el shard admite 5 `GetRecords` por segundo **compartidas**, y el harness lee cada 0,25 s mientras Firehose lee cada 1 s.

### 3.3 Landing zone con Firehose y delimitador de línea
El harness escribe el replay sin `\n`, y sin delimitador Firehose concatena `}{`. Por eso se activa el procesador `AppendDelimiterToRecord`. R4 pasaría igual, porque busca con una regex, pero Athena no podría leer los eventos.

### 3.4 ETL con Athena CTAS (reconstrucción completa)
- DROP y CTAS a `star/<tabla>/<run_id>/`, y después se borra el prefijo anterior. Es idempotente por diseño.
- Si llega un POST mientras corre otro refresco, se agenda otra corrida que empieza al terminar la actual. Así el harness nunca recibe un SUCCEEDED de una corrida que empezó antes de que sus eventos llegaran a S3.
- El temporizador (cada 10 min) se salta la corrida si la landing zone no cambió.

### 3.5 Miembros "desconocido" en las dimensiones
`route_key = 0` y `fare_class_key = 0` reciben las rutas o clases que no están en la referencia. Así no hay hechos huérfanos (R6) aunque alguien busque una ruta inexistente desde el frontend. A `dim_date` **no** se le agrega un miembro desconocido, porque R5 exige exactamente un día por fila de 2023 a 2027. Los eventos fuera de ese rango se descartan del hecho.

### 3.6 PostgreSQL en la EC2 (sin RDS)
Decisión del equipo para bajar el costo (R12): ahorra ~US$14,70 al mes. PostgreSQL escucha solo en 127.0.0.1 y pide contraseña (scram).

### 3.7 Se quitó `/analytics/occupancy`
El contrato del Parcial 3 no lo pide y sus tablas (historial del P2) no existen en esta base. El panel gerencial ahora muestra la vista en vivo y el estado del refresco de la estrella.

---

## 4. Cómo se probó sin AWS
- **SQL**: `tools/verificar_estrella_local.py` traduce el SQL de Athena a DuckDB con sqlglot, carga el replay sucio del harness y repite R5 (dim_date), R6, R7 (Q1–Q8), R8 y R9. Resultado: todo OK.
- **API**: `tools/correr_local.py` levanta el backend con SQLite y Kinesis simulado por moto, y contra él se corrieron los tests R1–R3 del harness: **20/20**, p95 = 0,045 s en la ráfaga de R2.
- **Unitarias**: `backend/tests/` (contador en vivo y contrato de eventos), 5 de 5.

## 5. Corrida en AWS (2026-11-18): 70/70

Harness completo contra el Learner Lab: **70 / 70**, 29 pruebas en 3 min 34 s (`report.md`).

| Requisito | Evidencia |
|---|---|
| R1 | 30 eventos de búsqueda para 30 llamadas; 4 de reserva (3 + 1 cancelación) |
| R2 | 200 búsquedas, concurrencia 50: p95 = 0,335 s; 200 eventos en el stream |
| R3 | deltas 10/3/1 visibles a los 1,7 s; tras el replay de 17.000 búsquedas viejas la vista marca 243 (solo las de los tests) |
| R4 | 19.912 / 19.912 eventos distintos en S3 a los 68 s |
| R8 | refresco SUCCEEDED en 31 s (límite: 15 min) |
| R10 | un mes escanea 3.804 B frente a 11.210 B de todos los meses (0,34; límite 0,6) |
| R11 | PROVISIONED, 1 shard, 24 h, 0 consumidores EFO |
| R12 | US$18,15/mes declarados |

### Problemas que solo aparecieron en AWS
1. **`Unresolved resource dependencies [ApiInstanceRole...]`.** CDK deja un `DependsOn` hacia el rol IAM que se quita para usar `LabInstanceProfile`. En el P2 no se notaba porque ese `DependsOn` se sobrescribía con la RDS. Arreglo: `addDeletionOverride("DependsOn")`.
2. **CTAS con `external_location` rechazado.** El workgroup tenía `EnforceWorkGroupConfiguration = true`. Se puso en `false`: el tope de 1 GB por consulta (R10) se aplica igual.
3. **`timestamp(0)` en `full_date`.** En Athena, `sequence()` sobre fechas devuelve timestamps (en DuckDB no). Arreglo: `CAST(d AS date)`. La verificación local sigue en OK.
4. Firehose aceptó `AppendDelimiterToRecord` con `LabRole`, y cada objeto en S3 trae un evento por línea en gzip. El plan B no hizo falta.

Para subir cambios de código sin recrear la EC2 (redesplegar cambiaría el UserData y reiniciaría la instancia con otra IP) se usa `infra/actualizar_codigo.sh` (por SSH).

## 6. Documentación (2026-11-18)
- Diagramas generados con el mismo motor del P2 (`docs/diagrams/`): arquitectura (`07-*`, en .drawio, .svg y .png) y modelo estrella (`08-*`).
- Documento final `docs/documento-final.html` → `docs/PARCIAL3-ENTREGA.pdf` (18 páginas), con secciones 5 y 6, costos, problemas, limitaciones, apéndice de IA y glosario. Se genera con `docs/generar_pdf.py` usando el Chrome del sistema.
- Guía de defensa oral por bloques, con los cambios en vivo más probables: `docs/DEFENSA.md`.
- `config.yaml` del harness (sin credenciales) copiado a `parcial3/config.yaml`.

## 7. Pendiente
- Practicar la defensa en equipo con `docs/DEFENSA.md`.
- Destruir el stack (`infra/deploy.sh destroy`) cuando ya no se necesite la EC2. El stream ya está borrado.
