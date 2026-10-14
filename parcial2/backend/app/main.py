"""API del parcial 2 (contrato: harness/contract/API.md).

Anti-sobreventa (R2): un UNICO UPDATE condicional por reserva,

    UPDATE flights SET seats_sold = seats_sold + 1
    WHERE flight_id = :id AND seats_sold < capacity

PostgreSQL toma el lock de la fila y re-evalua la condicion cuando una
transaccion concurrente termina, de modo que exactamente `capacity` UPDATEs
tienen exito y el resto afecta 0 filas -> 409. El CHECK de la tabla es la ultima
barrera. Sin SELECT previo: menos viajes a la base y sin ventana de carrera.
"""

import datetime as dt
import os
import pathlib
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import athena
from app.config import settings
from app.db import engine, init_schema
from app.schemas import (
    MONTH_PATTERN,
    ROUTE_PATTERN,
    FlightIn,
    FlightOut,
    OccupancyOut,
    ReservationIn,
    ReservationOut,
)

_IATA = re.compile(r"^[A-Za-z]{3}$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_schema()
    yield


app = FastAPI(title="Reservas aereas - parcial 2", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/flights", response_model=FlightIn, status_code=201)
def crear_vuelo(f: FlightIn):
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO flights (flight_id, route, flight_date, capacity, price_cents) "
                    "VALUES (:flight_id, :route, :flight_date, :capacity, :price_cents)"
                ),
                f.model_dump(),
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"el vuelo {f.flight_id} ya existe")
    return f


@app.get("/flights/search", response_model=list[FlightOut])
def buscar_vuelos(origin: str = Query(...), destination: str = Query(...), date: str = Query(...)):
    if not _IATA.match(origin) or not _IATA.match(destination):
        raise HTTPException(status_code=422, detail="origin/destination deben ser codigos de 3 letras")
    try:
        fecha = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date debe tener formato YYYY-MM-DD")

    ruta = f"{origin.upper()}-{destination.upper()}"
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT flight_id, route, flight_date, capacity - seats_sold AS seats_available, price_cents "
                "FROM flights WHERE route = :route AND flight_date = :fecha AND seats_sold < capacity "
                "ORDER BY flight_id"
            ),
            {"route": ruta, "fecha": fecha},
        ).mappings().all()
    return [dict(r) for r in rows]


@app.post("/reservations", response_model=ReservationOut, status_code=201)
def crear_reserva(r: ReservationIn):
    reservation_id = uuid.uuid4().hex
    with engine.begin() as conn:  # una sola transaccion: cupo + reserva
        updated = conn.execute(
            text(
                "UPDATE flights SET seats_sold = seats_sold + 1 "
                "WHERE flight_id = :fid AND seats_sold < capacity"
            ),
            {"fid": r.flight_id},
        ).rowcount
        if updated == 0:
            existe = conn.execute(
                text("SELECT 1 FROM flights WHERE flight_id = :fid"), {"fid": r.flight_id}
            ).first()
            if existe is None:
                raise HTTPException(status_code=404, detail=f"vuelo {r.flight_id} no existe")
            raise HTTPException(status_code=409, detail=f"vuelo {r.flight_id} sin asientos disponibles")

        conn.execute(
            text(
                "INSERT INTO reservations (reservation_id, flight_id, passenger_name, fare_class) "
                "VALUES (:rid, :fid, :name, :fare)"
            ),
            {"rid": reservation_id, "fid": r.flight_id, "name": r.passenger_name, "fare": r.fare_class},
        )
    return ReservationOut(
        reservation_id=reservation_id,
        flight_id=r.flight_id,
        status="CONFIRMED",
        passenger_name=r.passenger_name,
    )


@app.get("/reservations/{reservation_id}", response_model=ReservationOut)
def consultar_reserva(reservation_id: str):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT reservation_id, flight_id, status, passenger_name "
                "FROM reservations WHERE reservation_id = :rid"
            ),
            {"rid": reservation_id},
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="reserva no encontrada")
    return dict(row)


@app.get("/analytics/occupancy", response_model=OccupancyOut)
def ocupacion(
    route: str = Query(..., pattern=ROUTE_PATTERN),
    month: str = Query(..., pattern=MONTH_PATTERN),
):
    try:
        resultado = athena.query_occupancy(route, month)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Athena no respondio a tiempo")
    except Exception as e:  # credenciales, permisos, tabla inexistente...
        raise HTTPException(status_code=502, detail=f"error consultando Athena: {e}")
    if resultado is None:
        raise HTTPException(status_code=404, detail="sin datos para esa ruta y mes")
    return resultado


# --- Frontend estatico (mismo proceso, mismo origen: un servicio menos que operar) ---
# Se monta al final para que no tape las rutas de la API. "/" -> index.html y
# "/manager" -> manager/index.html. Si el directorio no existe, solo se sirve la API.
_FRONTEND = pathlib.Path(os.environ.get("FRONTEND_DIR", pathlib.Path(__file__).resolve().parents[2] / "frontend"))
if _FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="frontend")
