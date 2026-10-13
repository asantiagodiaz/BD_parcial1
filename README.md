# Sistema de reservas aéreas — Parcial 1

**Big Data e Ingeniería de Datos.** Diseño e implementación parcial del sistema de
reservas de una aerolínea regional, con despliegue en **AWS Academy Learner Lab**.

El enunciado evalúa la **coherencia y trazabilidad** entre las decisiones tomadas
y los requisitos que el equipo define; no hay una única respuesta correcta.

---

## 1. El problema

Una aerolínea regional necesita su sistema de reservas desde cero. Los puntos
críticos del escenario:

- Buscar vuelos (directos y con **escala**), reservar, pagar, consultar y cancelar.
- Venta **directa** y a través de **agencias asociadas** (con descuento/comisión).
- **Tarifas** según anticipación de compra y tipo de asiento (económica / ejecutiva).
- Una reserva puede ser un **itinerario multi-tramo** en una sola transacción.
- **"El sistema no debe vender más asientos de los que tiene el avión"** — el
  requisito central: evitar la **sobreventa** bajo peticiones simultáneas.
- La gerencia quiere analizar después **ocupación por ruta, ingresos por tarifa y
  patrones de cancelación**.

---

## 2. La solución, en una frase

Un **monolito FastAPI** sobre **PostgreSQL** que protege el inventario de asientos
con **bloqueo pesimista** (`SELECT ... FOR UPDATE` en orden determinista), más un
**pipeline analítico** (ETL Python → segunda PostgreSQL en esquema estrella →
**AWS Glue Data Catalog**), todo desplegado en el Learner Lab con **AWS CDK**.

---

## 3. Decisiones de diseño (y por qué)

| Decisión | Motivo | Requisito |
|---|---|---|
| **Monolito modular**, no microservicios | Una transacción ACID resuelve la no-sobreventa; repartir el inventario obligaría a saga/2PC | NFR-03 |
| **Bloqueo pesimista** (`FOR UPDATE`), no optimista ni cola | Alta contención sobre el asiento; el costo de un reintento fallido para el usuario es alto | NFR-03 |
| Orden determinista de los locks (`id_instancia_vuelo` asc) | Evita deadlocks entre reservas que tocan los mismos vuelos | NFR-04 |
| **Inventario por cabina** (contador), no por silla | La silla se asigna en el check-in (S7) | 5.3 |
| **`VUELO_PROGRAMADO`** (plantilla) ≠ **`INSTANCIA_VUELO`** (fecha concreta) | Un vuelo se repite a diario; el inventario es por instancia | 5.3 |
| **`ITINERARIO`** como entidad entre `RESERVA` e `INSTANCIA_VUELO` | Multi-tramo limpio: una reserva → un itinerario → N segmentos ordenados | 5.3 |
| **OLTP en 3FN**, **OLAP en esquema estrella** en **instancia separada** | Prioridades opuestas: integridad en escritura vs. lecturas analíticas rápidas | 5.3, NFR-08 |
| **Auditoría append-only** por trigger (rechaza UPDATE/DELETE en `evento_reserva`) | Reconstruir el historial completo de una reserva | NFR-09 |
| **Pago delegado** a pasarela externa; solo se guarda un token | Nunca almacenar PAN/CVV | NFR-06 |
| **SPA React**, no SSR | La búsqueda es exploratoria; cada cambio es una llamada JSON, no un re-render en servidor | NFR-01/02 |
| Manejo del **409** sin WebSocket | La garantía es el 409 + la transacción; el polling de disponibilidad es best-effort | NFR-03 |
| **ETL = script Python**, Glue solo para el Data Catalog | Volumen bajo, corre en la EC2 existente ($0 extra), trazable | 5.7 |

---

## 4. Estructura del repositorio

```
docs/            Los documentos del parcial (fuente .md + entrega .docx)
  00 … 07        Contexto y supuestos, y secciones 5.1 a 5.7
  99             Apéndice: registro de prompts
  PARCIAL1-ENTREGA.docx   Documento final unificado (00–07 + 99)
  diagrams/      Los 4 diagramas en .drawio (E-R, backend, frontend, AWS)
  evidencia/     Salidas de las pruebas de concurrencia y del ETL

backend/         API FastAPI + BD (sección 5.6)
  app/           config, modelos (19 tablas = modelo 5.3), routers, servicios
  app/services/booking.py    crear_reserva con SELECT ... FOR UPDATE
  alembic/       migración 0001: esquema + trigger append-only
  seed/          datos de ejemplo (load) + reservas demo (demo_reservas)
  tests/         test_concurrencia.py (20 hilos) + concurrencia_http.py (API en vivo)

analytics/schema_olap.sql   Esquema estrella: fact_reserva_segmento + 5 dims + 3 vistas
etl/etl.py                  ETL OLTP → OLAP (EXTRACT / TRANSFORM / LOAD idempotente)

frontend/        SPA React + Vite (sección 5.5)
  src/pages/     Buscar, Selección, Confirmación, Mi reserva
  src/api.js     cliente HTTP; src/i18n/  textos externalizados

infra/cdk/       Infraestructura como código (AWS CDK, TypeScript)
  lib/aerolinea-stack.ts   VPC + SG + 2× RDS + EC2 + Glue Data Catalog
  deploy.sh      despliegue completo   ·   validar.sh   verificación (15 chequeos)

tools/           md2docx.py (Markdown → Word) · compilar_entrega.py (documento final)
                 probar_concurrencia_aws.py · consultar_reservas.py · ver_vistas_negocio.py
                 (pruebas contra lo desplegado en AWS; leen API_URL / OLTP_DATABASE_URL / OLAP_DATABASE_URL del entorno)

SUSTENTACION.md  Cómo correr todo, todas las URLs, guion de demo y FAQ de defensa
```

---

## 5. Cómo correrlo

Guía completa en **[`SUSTENTACION.md`](SUSTENTACION.md)**. Resumen:

### Local

```bash
# backend + bases
cd backend
bash setup-postgres-local.sh
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m seed.load && .venv/bin/python -m seed.demo_reservas
.venv/bin/uvicorn app.main:app --reload        # http://localhost:8000/docs

# ETL
cd .. && backend/.venv/bin/python etl/etl.py --init && backend/.venv/bin/python etl/etl.py --full

# frontend
cd frontend && npm install && cp .env.example .env && npm run dev   # http://localhost:5173
```

### AWS (Learner Lab)

```bash
cd infra/cdk && npm install
AWS_PROFILE=academy ./deploy.sh      # despliega todo y deja la API funcionando
AWS_PROFILE=academy ./validar.sh     # verifica: 15 OK / 0 FALLA
AWS_PROFILE=academy ./deploy.sh destroy   # al terminar la sesión
```

---

## 6. Prueba de concurrencia (la evidencia clave — NFR-03)

20 peticiones simultáneas por **el último asiento** de un vuelo:

```
201 Created : 1
409 Conflict: 19
sin sobreventa  (vendidos + retenidos <= totales)
```

Dos implementaciones de la prueba, ambas pasan:
`backend/tests/test_concurrencia.py` (capa de servicio, 20 hilos) y
`backend/tests/concurrencia_http.py` (contra la API HTTP en vivo).
Salidas en [`docs/evidencia/`](docs/evidencia/).

---

## 7. Pipeline analítico (5.7)

- **`etl/etl.py`**: 1 consulta a nivel de segmento → desnormaliza y deriva
  columnas (`par_ruta`, `temporada`, `ventana_compra`, banderas de estado,
  comisión prorrateada) → `upsert` idempotente en `fact_reserva_segmento`.
- **3 vistas** = las 3 preguntas de negocio: `v_ocupacion_por_ruta`,
  `v_ingresos_por_tarifa`, `v_patrones_cancelacion`.
- **Glue Data Catalog** `aerolinea_catalog`: 2 crawlers catalogan las 19 tablas
  `oltp_*` y las 9 `olap_*`.
- **Costos** (`docs/07`): ~$16,5/mes en el Lab · escenario ×10 → sube ~2,5×, no
  10× (conectado a los pilares Optimización de costos y Sostenibilidad).

---

## 8. Documentos

Cada uno tiene su versión **`.md`** (fuente) y **`.docx`** (entrega). El `.docx`
se regenera con `python tools/md2docx.py`. El documento final unificado se genera
con `python tools/compilar_entrega.py` → `docs/PARCIAL1-ENTREGA.docx`.

| Documento | Sección |
|---|---|
| [00 — Contexto y supuestos](docs/00-contexto-supuestos.md) | Contexto |
| [01 — Requisitos funcionales](docs/01-requisitos-funcionales.md) | 5.1 |
| [02 — Requisitos no funcionales](docs/02-requisitos-no-funcionales.md) | 5.2 |
| [03 — Modelo entidad-relación](docs/03-modelo-entidad-relacion.md) | 5.3 |
| [04 — Arquitectura del backend](docs/04-arquitectura-backend.md) | 5.4 |
| [05 — Arquitectura del frontend](docs/05-arquitectura-frontend.md) | 5.5 |
| [06 — Implementación del backend](docs/06-implementacion-backend.md) | 5.6 |
| [07 — AWS: ETL, Glue y costos](docs/07-aws-etl-glue-costos.md) | 5.7 |
| [99 — Registro de prompts](docs/99-prompt-log.md) | Apéndice §4 |
