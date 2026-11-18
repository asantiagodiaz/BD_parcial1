#!/usr/bin/env bash
# Se ejecuta DENTRO de la EC2 (como ec2-user) desde el UserData del stack.
# El .env ya lo escribio el UserData. El esquema de la base lo crea la propia API al arrancar.
set -xe
cd /opt/airline/parcial3/backend
python3.11 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

# Comprobar que PostgreSQL local acepta la conexion de la API.
set -a; . ./.env; set +a
for i in $(seq 1 20); do
  if .venv/bin/python - <<'PY'
import os, sys
import psycopg
raw = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
try:
    psycopg.connect(raw, connect_timeout=5).close()
except Exception as e:
    print(e); sys.exit(1)
PY
  then echo "PostgreSQL listo"; break; fi
  echo "esperando PostgreSQL... ($i/20)"; sleep 5
done
echo ">> provisioning terminado"
