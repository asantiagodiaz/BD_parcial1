#!/usr/bin/env bash
# Se ejecuta DENTRO de la EC2 (como ec2-user) desde el UserData del stack CDK.
# El .env ya fue escrito por el UserData con los endpoints de las RDS.
set -xe

cd /opt/aerolinea/backend

# Cargar OLTP_DATABASE_URL / OLAP_DATABASE_URL ANTES de usarlas.
set -a; . /opt/aerolinea/backend/.env; set +a

python3.11 -m venv .venv
.venv/bin/pip install -q -e ".[dev]"

# Esperar a que la RDS OLTP acepte conexiones (el stack ya crea la dependencia,
# pero el endpoint tarda un poco mas en estar 'available' y resolver DNS).
for i in $(seq 1 60); do
  if .venv/bin/python - <<'PY'
import os, sys
import psycopg
raw = os.environ["OLTP_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
try:
    psycopg.connect(raw, connect_timeout=5).close()
except Exception as e:
    print(e); sys.exit(1)
PY
  then echo "RDS OLTP lista"; break; fi
  echo "esperando RDS OLTP... ($i/60)"; sleep 15
done

echo ">> migraciones OLTP (modelo 5.3 + trigger append-only)"
.venv/bin/alembic upgrade head

echo ">> datos de ejemplo"
.venv/bin/python -m seed.load
.venv/bin/python -m seed.demo_reservas

echo ">> esquema OLAP + ETL"
.venv/bin/python ../etl/etl.py --init
.venv/bin/python ../etl/etl.py --full

# NOTA: NO se corre `pytest tests/test_concurrencia.py` aqui: su fixture `_schema`
# hace drop_all en el teardown y borraria las tablas de la RDS. La evidencia de
# concurrencia en AWS se toma con el test HTTP en vivo (concurrencia_http.py),
# que no toca el esquema. Se lanza al final, cuando la API ya esta arriba.

echo ">> provisioning terminado"
