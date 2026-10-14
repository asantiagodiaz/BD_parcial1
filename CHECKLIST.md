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
- [ ] Generar datos: `python -m airline_data.generate --seed <SEMILLA> --rows 2000000 --out raw/`
- [x] Nueva cuenta/Lab de AWS lista (937228084004)

### Entrega parcial (antes de construir)
- [x] Borrador de la sección 5 (`parcial2/docs/seccion5-borrador.md`)
- [ ] Diagrama de arquitectura
- [x] Tabla de justificación de servicios (incluida en el borrador)
- [x] Primera proyección de costos (`parcial2/cost_projection.yaml`)

### Requisitos del harness (70 pts)
- [x] **R1** (4) (pasa en local) `GET /flights/search` con p95 ≤ 1 s bajo 20 clientes concurrentes
- [x] **R2** (10) (pasa en local) Sin sobreventa: 1 asiento y K asientos con 50 peticiones simultáneas, nunca 5xx
- [x] **R3** (3) (pasa en local) `GET /reservations/{id}` devuelve 200 o 404
- [ ] **R4** (8) Job EMR (PySpark) aplica C1–C5 y escribe Parquet particionado por mes (24 particiones)
- [ ] **R5** (6) Tablas `reservations_curated` y `route_month_metrics` en Glue, con particiones
- [ ] **R6** (8) Athena: top-10 rutas correcto y consultas por mes sin escanear todo
- [ ] **R7** (8) `GET /analytics/occupancy?route=&month=` desde Athena en ≤ 10 s
- [x] **R8** (6) (pasa en local) Frontend: buscar, reservar y ver confirmación (selectores del Apéndice A.3)
- [ ] **R9** (4) Panel `/manager` muestra el mismo valor que el endpoint
- [ ] **R10** (5) Sin recursos EMR vivos; ≤ 150 horas normalizadas
- [ ] **R11** (4) Arquitectura simple: instancias pequeñas, sin Multi-AZ ni NAT, ≤ 8 servicios
- [ ] **R12** (4) `cost_projection.yaml` ≤ 1,5× la referencia y ≤ US$ 50, coherente con lo desplegado

### Construcción
- [x] Backend adaptado al contrato (`POST /admin/flights`, `/flights/search`, `/reservations`, `/analytics/occupancy`, `/health`)
- [x] Job PySpark de limpieza C1–C5 (verificado contra el oráculo en local; falta correrlo en EMR real)
- [ ] Tablas en Glue/Athena + endpoint de analítica
- [x] Frontend con las páginas `/` y `/manager` (`/manager` sin probar: depende de Athena)
- [x] Stack CDK simplificado + script `run_emr.sh` escritos en `parcial2/infra/` (plantilla generada; falta desplegar)
- [x] Probar que el Lab permite EMR con los roles disponibles (OK: cluster 1 x m4.large, job verificado contra el oráculo)

### Entrega final
- [ ] Ejecutar el harness completo y guardar `report.md`
- [ ] Documento final (secciones 5 y 6, explicación de fallos si los hay)
- [ ] Apéndice con el registro de prompts
- [ ] Repo limpio: sin credenciales y con `config.yaml` sin secretos
- [ ] Terminar siempre EMR y destruir el stack al acabar cada sesión
- [ ] Preparar la defensa oral (cada integrante debe poder explicar y modificar cualquier parte)
