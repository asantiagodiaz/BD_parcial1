"""Levanta el backend en local SIN PostgreSQL ni AWS, solo para pruebas de humo.

* La base se reemplaza por SQLite (archivo temporal). El codigo de la API no cambia: usa el
  mismo SQL (UPDATE ... RETURNING funciona en SQLite >= 3.35). La concurrencia real (R2 del P2)
  solo se prueba con PostgreSQL en la EC2.
* Kinesis se simula con moto en modo servidor: exportar AWS_ENDPOINT_URL_KINESIS antes.

    .venv/bin/moto_server -p 5005 &
    export AWS_ENDPOINT_URL_KINESIS=http://127.0.0.1:5005 AWS_ACCESS_KEY_ID=x AWS_SECRET_ACCESS_KEY=x
    aws kinesis create-stream --stream-name airline-events --shard-count 1
    KINESIS_STREAM=airline-events .venv/bin/python ../tools/correr_local.py
"""

import os
import sys
import tempfile

import uvicorn
from sqlalchemy import create_engine, event, text

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import app.db as db  # noqa: E402

path = os.path.join(tempfile.mkdtemp(), "local.sqlite")
engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30})


@event.listens_for(engine, "connect")
def _wal(conn, _):
    conn.execute("PRAGMA journal_mode=WAL")


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS flights (flight_id text PRIMARY KEY, route text NOT NULL,
       flight_date text NOT NULL, capacity integer NOT NULL, seats_sold integer NOT NULL DEFAULT 0,
       price_cents integer NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS reservations (reservation_id text PRIMARY KEY, flight_id text NOT NULL,
       passenger_name text NOT NULL, fare_class text NOT NULL, status text NOT NULL DEFAULT 'CONFIRMED')""",
]


def init_schema():
    with engine.begin() as c:
        for s in SCHEMA:
            c.execute(text(s))


db.engine = engine
db.init_schema = init_schema

from app.main import app  # noqa: E402  (importa despues del reemplazo)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
