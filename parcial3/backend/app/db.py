"""Acceso a PostgreSQL y esquema (2 tablas).

El esquema se crea al arrancar con CREATE TABLE IF NOT EXISTS: el contrato del
parcial 2 solo necesita vuelos y reservas, asi que no hace falta un gestor de
migraciones (una pieza menos que mantener y defender).
"""

from sqlalchemy import create_engine, text

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    pool_timeout=30,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
    flight_id   text PRIMARY KEY,
    route       text    NOT NULL,
    flight_date date    NOT NULL,
    capacity    integer NOT NULL CHECK (capacity > 0),
    seats_sold  integer NOT NULL DEFAULT 0,
    price_cents bigint  NOT NULL CHECK (price_cents >= 0),
    -- Ultima barrera del motor contra la sobreventa (R2)
    CONSTRAINT ck_no_overselling CHECK (seats_sold >= 0 AND seats_sold <= capacity)
);
CREATE INDEX IF NOT EXISTS ix_flights_route_date ON flights (route, flight_date);

CREATE TABLE IF NOT EXISTS reservations (
    reservation_id text PRIMARY KEY,
    flight_id      text NOT NULL REFERENCES flights (flight_id),
    passenger_name text NOT NULL,
    fare_class     text NOT NULL CHECK (fare_class IN ('ECONOMY', 'BUSINESS')),
    status         text NOT NULL DEFAULT 'CONFIRMED',
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reservations_flight ON reservations (flight_id);
"""


def init_schema() -> None:
    with engine.begin() as conn:
        # Evita que dos workers creen el esquema a la vez al arrancar.
        conn.execute(text("SELECT pg_advisory_xact_lock(9630001)"))
        conn.execute(text(SCHEMA))
