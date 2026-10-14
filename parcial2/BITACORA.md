# Bitácora — Parcial 2

Registro de lo que se hizo, los datos de la semilla y el porqué de cada decisión.
Última actualización: 2026-10-14.

---

## 1. Datos del equipo (semilla 963)

La semilla son los tres últimos dígitos de la cédula. Todo lo demás sale de ella
(`airline_data/params.py` del harness), así que no son decisiones nuestras sino parámetros fijos:

| Dato | Valor | Para qué sirve |
|---|---|---|
| Semilla | **963** | Determina el dataset y las respuestas esperadas |
| Rutas (9) | CUC-BGA, CTG-BOG, CUC-SMR, ADZ-CTG, PSO-SMR, SMR-BAQ, ADZ-BAQ, PSO-CUC, BGA-BOG | Las únicas rutas que existen en el historial |
| Capacidad por vuelo | **150** asientos | Capacidad de cada vuelo en `flights.csv`; base del cálculo de ocupación |
| K (R2) | **8** | En la prueba de concurrencia, un vuelo con 8 asientos: exactamente 8 de 50 clientes deben recibir 201 |
| Ocupación media | ~79 % | Qué tan llenos van los vuelos en el historial |
| Tasa de cancelación | ~12,5 % | Proporción de reservas CANCELLED |
| Ventana | 2023-01 a 2024-12 (24 meses) | Las 24 particiones `month=` que debe tener la tabla curada |
| Filas | 2.000.000 | Tamaño del historial (`--rows 2000000`) |

Notas:
- Cada ruta tiene un factor de ocupación distinto (entre ~0,67 y ~0,91) con estacionalidad suave, así que el top-10 de R6 sí discrimina entre rutas.
- El profesor aplica una `probe_salt` secreta para elegir los pares (ruta, mes) de R7 y R9; no se pueden precalcular.

---

## 2. Qué se construyó (carpeta `parcial2/`)

El Parcial 1 queda intacto. El Parcial 2 vive en `parcial2/` porque el contrato cambió por completo.

| Pieza | Archivos | Estado |
|---|---|---|
| Backend FastAPI | `backend/app/` | Hecho. **R1, R2, R3 pasan en local: 17/17 pts** |
| Frontend | `frontend/` | Hecho. **R8 pasa en local: 6/6 pts** |
| Job PySpark (EMR) | `emr/job.py` | Escrito. Lógica verificada contra el oráculo del harness (`emr/verificar_local.py`: TODO OK) |
| Endpoint de analítica | `backend/app/athena.py` | Escrito. **Sin probar**: requiere Athena (AWS) |
| Infraestructura (CDK) | – | Pendiente |
| Tablas Glue / Athena | – | Pendiente |
| `cost_projection.yaml` y documento | – | Pendiente |

Lo que sólo se puede probar con AWS (R4–R7, R9–R12) queda para cuando pases las credenciales.

---

## 3. Decisiones y por qué

### 3.1 Backend: esquema de 2 tablas (no las 19 del Parcial 1)
El contrato del Parcial 2 sólo maneja vuelos y reservas planas. Las 19 tablas (tarifas, itinerarios multi-tramo, agencias, billetes...) no aportan a ningún requisito. Menos tablas = menos código que defender (defensa oral), menos consultas por petición (R1) y nada que mantener. *Requisitos: R1, R2, R11. Pilares: Optimización de costos, Excelencia operativa.*

### 3.2 Anti-sobreventa con un único `UPDATE` condicional
```sql
UPDATE flights SET seats_sold = seats_sold + 1
WHERE flight_id = :id AND seats_sold < capacity
```
- Si afecta 1 fila → hay cupo (se inserta la reserva en la misma transacción). Si afecta 0 → 409 (o 404 si el vuelo no existe).
- PostgreSQL bloquea la fila y, cuando otra transacción termina, vuelve a evaluar la condición. Resultado: exactamente `capacity` éxitos, sin ventana de carrera.
- Respecto al `SELECT ... FOR UPDATE` del Parcial 1: es el mismo bloqueo pesimista de fila, pero con un viaje menos a la base. Menos latencia bajo 50 clientes simultáneos.
- Última barrera: `CHECK (seats_sold <= capacity)` en la tabla.
- *Requisito: R2. Pilares: Confiabilidad, Eficiencia de rendimiento.*

### 3.3 Base transaccional: PostgreSQL
El `UPDATE` condicional necesita bloqueo de filas real. SQLite no sirve para validar R2 de forma honesta. En AWS: RDS `db.t3.micro`, una sola AZ, sin Multi-AZ (R11). Alternativa más barata a evaluar en el CDK: PostgreSQL en la propia EC2 (ahorra ~US$14/mes, pero se pierde la gestión de respaldos de RDS; se decide en el borrador de costos).

### 3.4 Sin ORM de modelos ni migraciones
SQLAlchemy sólo como pool de conexiones y SQL explícito; el esquema se crea con `CREATE TABLE IF NOT EXISTS` al arrancar. Con dos tablas, Alembic sería una pieza más sin beneficio. El pool (20 + 40 de desborde) se dimensionó para 50 reservas simultáneas.

### 3.5 Frontend: HTML + JS plano servido por el mismo backend
Se evaluó reutilizar el React del Parcial 1 (~1000 líneas, Vite, router). Se descartó: está hecho para otra API (búsqueda con `pax`/`cabin`/`with_stops`, opciones multi-tramo, tarifas, consulta por código) y reutilizarlo exigía reescribir `api.js` y casi todas las páginas, añadir los `data-testid` y la página `/manager`. Además necesita Node y un paso de build. La versión simple:
- no requiere Node ni build en la EC2;
- se sirve desde el mismo proceso FastAPI (un servicio menos que operar y pagar);
- sólo 2 páginas pequeñas y fáciles de explicar.
Del Parcial 1 se reutilizó la idea de diseño (estilos claro/oscuro). *Requisitos: R8, R9, R11. Pilares: Optimización de costos, Excelencia operativa.* Si el equipo prefiere React, se puede portar sin cambiar el backend.

### 3.6 `/analytics/occupancy`: consulta Athena en cada petición, sin caché
El contrato exige que la primera petición por (ruta, mes) consulte Athena. Se consulta siempre: son pocas llamadas, cada consulta escanea KBs (fracciones de centavo) y evitamos servir datos viejos. Los parámetros se validan con lista blanca (regex) antes de interpolarlos en el SQL, porque Athena en este modo no admite parámetros. Timeout interno de 9 s para cumplir el límite de 10 s de R7. *Requisito: R7. Pilares: Seguridad, Eficiencia de rendimiento.*

### 3.7 Job PySpark
- Reglas C1–C5 aplicadas exactamente como el enunciado. En C5, "primero" se hace determinista con `row_number()` sobre `monotonically_increasing_id()`.
- Salida curada particionada por `month` con `repartition("month")`: un archivo por mes (24 archivos), sin miles de archivos pequeños. Eso mantiene el escaneo de una consulta mensual cerca de 1 partición (R6 permite hasta 2×).
- Métricas: capacidad = suma de **todos** los vuelos de la ruta y mes (aunque no tengan reservas); 9 rutas × 24 meses = 216 filas en un solo archivo.
- Verificado contra el oráculo del harness con 200 mil filas: filas curadas, ingresos por mes, capacidad, vendidos, cancelaciones y ocupación coinciden exactamente.

---

## 4. Hallazgos a comentar con el profesor

1. **Inconsistencia en `bookings`.** El enunciado (A.2) y `contract/DATA.md` dicen que `bookings` cuenta sólo reservas CONFIRMED, pero el oráculo del harness (`airline_data/oracle.py`, `route_month_metrics`) lo calcula sobre todas las reservas válidas (confirmadas + canceladas). Ningún test compara esa columna (sólo nombres), así que no afecta la nota. Seguimos el contrato escrito (`bookings = seats_sold`).
2. **Spark en Windows** no escribe archivos locales sin `winutils.exe` (binario de terceros que no se instaló). Por eso `verificar_local.py` valida la lógica de transformación en memoria; la E/S a S3 y Parquet se probará en EMR real.

---

## 5. Entorno local (para repetir las pruebas)

- Python 3.14 con venv en `parcial2/.venv` (ignorado por git).
- PostgreSQL 16 portátil en `C:\Users\LENOVO\tools\pgsql` (datos en `...\pgdata`), puerto **5433**, base `airline2`, sin contraseña, sólo local. Se arranca con `pg_ctl -D C:\Users\LENOVO\tools\pgdata -o "-p 5433" start`.
- Java 17 (JRE) en `C:\Users\LENOVO\tools\jdk` y PySpark 3.5.3 para probar el job.
- Chromium de Playwright instalado para R8.
- Harness: `C:\Users\LENOVO\Desktop\Uni\Big Data\parcial2-harness-estudiantes\parcial2-harness` con `config.yaml` (semilla 963, URLs locales). No se sube al repo.

Arrancar el backend y correr el harness:
```bash
cd parcial2/backend
DATABASE_URL="postgresql+psycopg://postgres@localhost:5433/airline2" ../.venv/Scripts/python -m uvicorn app.main:app --port 8000
# en otra terminal, desde la carpeta del harness:
../../BD_parcial1/parcial2/.venv/Scripts/python -m pytest tests/test_backend.py tests/test_frontend.py -k "not manager"
```

## 6. Pendiente (en orden)
1. Entrega parcial: diagrama de arquitectura, tabla de servicios, primera proyección de costos.
2. CDK simplificado: S3, EC2 (+ RDS o Postgres local), Glue DB + 2 tablas con partition projection, workgroup de Athena.
3. Script `run_emr.sh` (cluster `m4.large`, `--auto-terminate`). Probar primero que el Lab permita EMR.
4. Generar los 2M de filas, subir a S3, correr EMR, validar R4–R7 con credenciales.
5. `cost_projection.yaml`, documento (sección 5), registro de prompts, `report.md` final.

---

## 7. Prueba real en EMR (2026-10-14, cuenta 937228084004)

- Cuenta nueva del Lab: existen `EMR_DefaultRole`, `EMR_EC2_DefaultRole` y `LabInstanceProfile`; EMR con `m4.large` **sí está permitido**.
- Bucket de datos: `s3://p2-airline-937228084004` (privado, sin acceso público).
- **Primer intento falló por memoria**: cluster de 1 × `m4.large` con la configuración por defecto de Spark. En modo `cluster` el driver ocupa casi toda la memoria de YARN y los ejecutores nunca se asignaron (12 min con un solo contenedor). Se canceló el cluster a mano.
- **Corrección**: `run_emr.sh` fija la memoria explícitamente (`--driver-memory 1g`, ejecutor de 3 GB y 2 núcleos, sin asignación dinámica). Con eso el job corrió en ~2 min.
- Resultado con muestra de 200 mil filas (semilla 963): step `COMPLETED`, el cluster se apagó solo, 24 prefijos `month=` con 1 archivo Parquet cada uno (~85 KB) y 1 archivo de métricas. Comparado con el oráculo del harness: filas curadas (203.824), ingresos por mes, capacidad, vendidos, cancelaciones y ocupación coinciden exactamente.
- Tiempos: ~4,5 min de arranque del cluster + ~2 min de job. Cada corrida de 1 nodo cuenta unas 2–3 horas normalizadas (tope R10: 150).
- Pendiente de esta prueba: correr con los 2 M de filas y registrar tiempos reales.
