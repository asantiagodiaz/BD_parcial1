# ETL — OLTP → OLAP (sección 5.7)

Script Python que copia y **transforma** datos del sistema transaccional al
almacén analítico en esquema estrella.

Diseño y justificación completos: [`../docs/07-aws-etl-glue-costos.md`](../docs/07-aws-etl-glue-costos.md).

## Uso

Requiere las dos bases PostgreSQL accesibles (ver
[`../backend/setup-postgres-local.sh`](../backend/setup-postgres-local.sh)) y las
variables `OLTP_DATABASE_URL` / `OLAP_DATABASE_URL` (se leen del `.env` del backend
o del entorno).

```bash
# usar el venv del backend (ya tiene sqlalchemy + psycopg)
cd ..
export OLTP_DATABASE_URL="postgresql+psycopg://aerolinea:aerolinea@localhost:5432/aerolinea_oltp"
export OLAP_DATABASE_URL="postgresql+psycopg://aerolinea:aerolinea@localhost:5432/aerolinea_olap"

backend/.venv/bin/python etl/etl.py --init      # crea el esquema OLAP (una vez)
backend/.venv/bin/python etl/etl.py --full      # carga completa
backend/.venv/bin/python etl/etl.py             # carga incremental (upsert, idempotente)
```

Para tener datos con estados variados (confirmadas, canceladas, retenidas):

```bash
cd backend && .venv/bin/python -m seed.demo_reservas
```

## Consultar las 3 preguntas de negocio

```sql
SELECT * FROM v_ocupacion_por_ruta;      -- ocupación por ruta
SELECT * FROM v_ingresos_por_tarifa;     -- ingresos por tarifa
SELECT * FROM v_patrones_cancelacion;    -- patrones de cancelación
```

Evidencia de una ejecución: [`../docs/evidencia/etl-vistas-negocio.txt`](../docs/evidencia/etl-vistas-negocio.txt).

## En AWS

El despliegue crea las 2 RDS, corre `etl.py --init` + `--full` y registra ambas
bases en el Glue Data Catalog automáticamente (ver
[`../infra/cdk/`](../infra/cdk/) y `SUSTENTACION.md`). Para la carga diaria en la
EC2: `crontab -e` → `0 3 * * * cd /opt/aerolinea && backend/.venv/bin/python etl/etl.py`.
