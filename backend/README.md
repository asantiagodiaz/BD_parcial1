# Backend — API de reservas aéreas (sección 5.6)

Monolito modular FastAPI + PostgreSQL. Implementa las operaciones críticas:
**buscar vuelos**, **crear reserva** (con bloqueo pesimista contra la sobreventa) y
**consultar reserva**.

Diseño: [`../docs/04-arquitectura-backend.md`](../docs/04-arquitectura-backend.md) ·
Modelo de datos: [`../docs/03-modelo-entidad-relacion.md`](../docs/03-modelo-entidad-relacion.md) ·
Esta implementación: [`../docs/06-implementacion-backend.md`](../docs/06-implementacion-backend.md)

## Requisitos

- Python 3.11+
- PostgreSQL 14+ (nativo)

## Puesta en marcha

### 1. PostgreSQL (una sola vez)

```bash
bash setup-postgres-local.sh
```

Instala PostgreSQL, crea el usuario `aerolinea` y las dos bases (`aerolinea_oltp`,
`aerolinea_olap`) en la instancia local (puerto 5432). En AWS estas serán dos
instancias RDS separadas (ver [`../docs/07-aws-etl-glue-costos.md`](../docs/07-aws-etl-glue-costos.md)).

<details><summary>Si prefieres hacerlo a mano</summary>

```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE ROLE aerolinea LOGIN PASSWORD 'aerolinea';"
sudo -u postgres createdb -O aerolinea aerolinea_oltp
sudo -u postgres createdb -O aerolinea aerolinea_olap
```
</details>

### 2. Entorno Python

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
```

### 3. Esquema + datos de ejemplo

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m seed.load          # --reset para recargar
```

### 4. API

```bash
.venv/bin/uvicorn app.main:app --reload
#   docs interactivas: http://127.0.0.1:8000/docs
```

## Operaciones

```bash
# Buscar (directos + 1 escala)
curl "http://127.0.0.1:8000/flights/search?origin=BOG&dest=MDE&date=2026-09-12&pax=1&cabin=ECONOMICA"

# Crear reserva (estado RETENIDA, hold de 15 min)
curl -X POST http://127.0.0.1:8000/reservations -H 'content-type: application/json' -d '{
  "segmentos":[{"id_instancia_vuelo":11,"cabina":"ECONOMICA","id_tarifa":2}],
  "pasajeros":[{"tipo_documento":"CC","numero_documento":"1090123456",
                "nombre_completo":"Ana Perez","es_contacto_principal":true}]
}'

# Consultar
curl http://127.0.0.1:8000/reservations/H3TI24
```

## Prueba de concurrencia (NFR-03)

```bash
# Capa de servicio, 20 hilos con conexiones independientes:
.venv/bin/pytest tests/test_concurrencia.py -s

# API HTTP en vivo (requiere la API corriendo en :8000):
.venv/bin/python -m seed.load
.venv/bin/uvicorn app.main:app &                     # en otra terminal
PREP=$(.venv/bin/python -m tests.concurrencia_http --preparar)   # deja 1 asiento
# usar la instancia/tarifa que imprime:
.venv/bin/python -m tests.concurrencia_http --instancia 1 --tarifa 1 --n 20
```

Salidas guardadas como evidencia en [`../docs/evidencia/`](../docs/evidencia/).

## Estructura

```
app/
  config.py        variables de entorno
  db.py            engine + Session + get_db
  models.py        19 tablas = modelo ER de docs/03
  schemas.py       contratos Pydantic
  services/
    search.py      FR-01/02/03  (sin locks)
    booking.py     FR-04/05/06 + FR-12  -> SELECT ... FOR UPDATE (NFR-03/04)
  routers/
    flights.py     GET /flights/search, GET /flights/{id}/availability
    reservations.py POST /reservations, GET /reservations/{codigo}
alembic/versions/0001_esquema_inicial.py   crea el esquema + trigger append-only
seed/load.py       datos de ejemplo (5 aeropuertos, 10 vuelos, 30 dias, tarifas, agencias)
tests/             test_concurrencia.py, concurrencia_http.py
```
