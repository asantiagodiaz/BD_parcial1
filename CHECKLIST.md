# Checklist del proyecto

Se va marcando a medida que se avanza. `[x]` = hecho · `[ ]` = pendiente.
Última actualización: 2026-10-13.

> Nota: "hecho" en el Parcial 1 significa que el archivo/funcionalidad existe en el repo
> (revisado por lectura). No se volvió a ejecutar nada contra AWS.

---

## Parcial 1 — Sistema de reservas aéreas (entregado)

### Entregables
- [x] Documento final unificado (`docs/PARCIAL1-ENTREGA.docx` y `.pdf`)
- [x] Diagramas drawio: E-R, backend, frontend, AWS (`docs/diagrams/`)
- [x] Evidencia de pruebas (`docs/evidencia/`): concurrencia local, HTTP y AWS; ETL y vistas; Glue
- [x] Guía de sustentación (`SUSTENTACION.md`)
- [x] README del proyecto

### Backend (FastAPI + PostgreSQL)
- [x] Modelo de datos: 19 tablas (`backend/app/models.py`) + migración Alembic con trigger append-only
- [x] Búsqueda de vuelos y disponibilidad (`GET /flights/search`, `/flights/{id}/availability`)
- [x] Crear reserva multi-tramo con bloqueo pesimista `FOR UPDATE` (`POST /reservations`)
- [x] Consultar reserva con historial (`GET /reservations/{codigo}`)
- [x] Auditoría de eventos (`evento_reserva`)
- [x] Datos de ejemplo (`seed/load.py`, `seed/demo_reservas.py`)
- [x] Pruebas de concurrencia: 20 hilos (servicio) y HTTP en vivo

### Analítica
- [x] Esquema estrella OLAP (`analytics/schema_olap.sql`) con 3 vistas de negocio
- [x] ETL OLTP → OLAP (`etl/etl.py`)
- [x] Glue Data Catalog (2 crawlers) definido en CDK

### Frontend y despliegue
- [x] SPA React + Vite: Buscar, Selección, Confirmación, Mi reserva
- [x] Infraestructura CDK (`infra/cdk/`) + `deploy.sh` / `validar.sh` / `demo.sh`
- [x] Scripts de verificación contra AWS en `tools/` (leen credenciales del entorno)

### Pendientes / deuda del Parcial 1
- [ ] Pago, confirmación y cancelación de reservas (hoy solo existen crear y consultar)
- [ ] Expiración de holds (`retenida_hasta` se guarda pero nada libera los asientos)
- [ ] Arreglar links del README a `docs/00…99-*.md` (los `.md` se borraron en el commit `fbb1901`)
- [ ] Limpieza menor de código: `Decimal` para dinero, `secrets` para el código de reserva, imports sin usar, validar demanda repetida del mismo vuelo/cabina
- [ ] Decidir si `infra/cdk/cdk.context.json` se deja de versionar (se regenera en cada despliegue)

---

## Parcial 2 — Panel gerencial (Big Data, EMR, Glue, Athena)

Enunciado: `docs/enunciado-parcial2.docx` · Harness: `../parcial2-harness-estudiantes/parcial2-harness`

### Datos de partida
- [x] Semilla del equipo: **963** (últimos 3 dígitos de la cédula). Datos derivados en `parcial2/BITACORA.md`
- [x] `config.yaml` del harness creado (local, semilla 963)
- [x] Datos generados (2.079.743 reservas, semilla 963) y subidos a S3
- [x] Nueva cuenta/Lab de AWS lista (937228084004)

### Entrega parcial (antes de construir)
- [x] Borrador de la sección 5 (`parcial2/docs/seccion5-borrador.md`)
- [ ] Diagrama de arquitectura
- [x] Tabla de justificación de servicios (incluida en el borrador)
- [x] Primera proyección de costos (`parcial2/cost_projection.yaml`)

### Requisitos del harness (70 pts)
- [x] **R1** (4) (pasa en AWS) `GET /flights/search` con p95 ≤ 1 s bajo 20 clientes concurrentes
- [x] **R2** (10) (pasa en AWS) Sin sobreventa: 1 asiento y K asientos con 50 peticiones simultáneas, nunca 5xx
- [x] **R3** (3) (pasa en AWS) `GET /reservations/{id}` devuelve 200 o 404
- [x] **R4** (8) (pasa en AWS) Job EMR (PySpark) aplica C1–C5 y escribe Parquet particionado por mes (24 particiones)
- [x] **R5** (6) (pasa en AWS) Tablas `reservations_curated` y `route_month_metrics` en Glue, con particiones
- [x] **R6** (8) (pasa en AWS) Athena: top-10 rutas correcto y consultas por mes sin escanear todo
- [x] **R7** (8) (pasa en AWS) `GET /analytics/occupancy?route=&month=` desde Athena en ≤ 10 s
- [x] **R8** (6) (pasa en AWS) Frontend: buscar, reservar y ver confirmación (selectores del Apéndice A.3)
- [x] **R9** (4) (pasa en AWS) Panel `/manager` muestra el mismo valor que el endpoint
- [x] **R10** (5) (pasa en AWS) Sin recursos EMR vivos; ≤ 150 horas normalizadas
- [x] **R11** (4) (pasa en AWS) Arquitectura simple: instancias pequeñas, sin Multi-AZ ni NAT, ≤ 8 servicios
- [x] **R12** (4) (pasa en AWS) `cost_projection.yaml` ≤ 1,5× la referencia y ≤ US$ 50, coherente con lo desplegado

### Construcción
- [x] Backend adaptado al contrato (`POST /admin/flights`, `/flights/search`, `/reservations`, `/analytics/occupancy`, `/health`)
- [x] Job PySpark de limpieza C1–C5 (verificado contra el oráculo en local; falta correrlo en EMR real)
- [x] Tablas en Glue/Athena + endpoint de analítica
- [x] Frontend con las páginas `/` y `/manager` (`/manager` sin probar: depende de Athena)
- [x] Stack CDK simplificado + script `run_emr.sh` escritos en `parcial2/infra/` (plantilla generada; falta desplegar)
- [x] Probar que el Lab permite EMR con los roles disponibles (OK: cluster 1 x m4.large, job verificado contra el oráculo)

### Entrega final
- [x] Ejecutar el harness completo y guardar `report.md` (70/70 en AWS, `parcial2/report.md`)
- [ ] Documento final (secciones 5 y 6, explicación de fallos si los hay)
- [ ] Apéndice con el registro de prompts
- [ ] Repo limpio: sin credenciales y con `config.yaml` sin secretos
- [ ] Terminar siempre EMR y destruir el stack al acabar cada sesión
- [ ] Preparar la defensa oral (cada integrante debe poder explicar y modificar cualquier parte)

---

## Parcial 3 — Eventos, vista en vivo y modelo estrella (Kinesis, Firehose, Athena)

Enunciado: `parcial3/docs/parcial32026-2-EN.pdf` · Harness: `../parcial3-harness-estudiantes` · Plan: `parcial3/PLAN.md` · Bitácora: `parcial3/BITACORA.md`

### Datos de partida
- [x] Semilla **963**; `ref/` generado con `airline_data.generate_p3` y versionado en `parcial3/ref/`
- [x] PostgreSQL en la misma EC2 (sin RDS) para bajar el costo
- [x] Credenciales del Lab solo para el proyecto (`source parcial3/aws-env.sh`, nunca en `~/.aws`)

### Entrega parcial (antes de construir)
- [x] Borrador de la sección 5 (`parcial3/docs/seccion5-borrador.md`): eventos, dos caminos, landing zone, estrella, ETL, SCD, eventos sucios, costos
- [x] Diagrama del modelo estrella con granos y matriz bus (`parcial3/docs/diagrams/08-modelo-estrella-parcial3.png`)
- [x] Diagrama de arquitectura (`parcial3/docs/diagrams/07-arquitectura-aws-parcial3.*`)
- [x] Primera proyección de costos (`parcial3/cost_projection.yaml`, US$ 18,15/mes)

### Requisitos del harness (70 pts) — 70/70 en AWS el 2026-11-18
- [x] **R1** (7) Un evento válido por búsqueda, reserva y cancelación; clave de partición; sin datos personales
- [x] **R2** (6) Ráfaga de 200 búsquedas: p95 0,335 s y 200/200 eventos
- [x] **R3** (7) `/analytics/live` refleja eventos en 1,7 s y cuenta por `event_ts`
- [x] **R4** (4) 19.912/19.912 eventos en la landing zone a los 68 s
- [x] **R5** (7) Tablas en Glue con tipos del contrato, Parquet, `dim_date` enriquecida, `fact_search` particionada
- [x] **R6** (5) Claves únicas, sin huérfanos, una fila por `event_id`
- [x] **R7** (11) Q1, Q2, Q3, Q4, Q6, Q7, Q8 exactas
- [x] **R8** (6) Dedup, tardíos por fecha de evento, refresco en 31 s
- [x] **R9** (8) `dim_route` SCD tipo 2 y Q5 con la versión vigente
- [x] **R10** (4) Un mes escanea 34 % de todo; workgroup con tope de 1 GB
- [x] **R11** (3) Stream provisionado, 1 shard, 24 h, sin EFO
- [x] **R12** (2) Proyección de US$ 18,15 con Kinesis, S3 y Athena

### Entrega final
- [x] Repositorio: backend, consumidor, job de carga, scripts para crear y borrar el stream, `config.yaml` sin credenciales, `cost_projection.yaml`, `report.md`
- [x] Documento final con secciones 5 y 6 (`parcial3/docs/documento-final.html` → `PARCIAL3-ENTREGA.pdf`)
- [x] Apéndice con el registro de prompts (sección 12 del documento)
- [x] Borrar el stream y Firehose al terminar cada sesión (`./borrar_stream.sh`)
- [ ] Destruir el stack (`./deploy.sh destroy`) cuando ya no se necesite la EC2
- [x] Guía de defensa oral por bloques (`parcial3/docs/DEFENSA.md`)
- [ ] Practicar la defensa en equipo (cada integrante debe poder explicar y modificar cualquier parte)
