"""API del parcial 3 (contrato: harness/contract/API.md y EVENTS.md).

Se mantiene todo el Parcial 2 (vuelos, busqueda, reservas sin sobreventa) y se agrega:
  * un evento a Kinesis por cada busqueda, reserva y cancelacion (events.py),
  * POST /reservations/{id}/cancel,
  * GET /analytics/live alimentado por un consumidor del stream (live.py),
  * POST /admin/refresh-star y GET /admin/refresh-status (star.py).

Anti-sobreventa (sin cambios desde el P2): un UNICO UPDATE condicional por reserva,
    UPDATE flights SET seats_sold = seats_sold + 1 WHERE flight_id = :id AND seats_sold < capacity
"""

import datetime as dt
import logging
import os
import pathlib
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import events, live, star
from app.config import settings
from app.db import engine, init_schema
from app.schemas import FlightIn, FlightOut, LiveOut, ReservationIn, ReservationOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
_IATA = re.compile(r"^[A-Za-z]{3}$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_schema()
    events.publisher.start()
    live.consumer.start()
    star.job.start_timer()
    yield
    star.job.stop()
    live.consumer.stop()
    events.publisher.stop()


app = FastAPI(title="Reservas aereas - parcial 3", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "stream": settings.kinesis_stream or None,
        "publisher": {"sent": events.publisher.sent, "dropped": events.publisher.dropped},
        "consumer": {"records_read": live.consumer.records_read,
                     "last_poll": live.consumer.last_poll.isoformat() if live.consumer.last_poll else None,
                     "last_error": live.consumer.last_error},
    }


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
def buscar_vuelos(
    origin: str = Query(...),
    destination: str = Query(...),
    date: str = Query(...),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
):
    if not _IATA.match(origin) or not _IATA.match(destination):
        raise HTTPException(status_code=422, detail="origin/destination deben ser codigos de 3 letras")
    try:
        fecha = dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=422, detail="date debe tener formato YYYY-MM-DD")

    origin, destination = origin.upper(), destination.upper()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT flight_id, route, flight_date, capacity - seats_sold AS seats_available, price_cents "
                "FROM flights WHERE route = :route AND flight_date = :fecha AND seats_sold < capacity "
                "ORDER BY flight_id"
            ),
            {"route": f"{origin}-{destination}", "fecha": fecha},
        ).mappings().all()
    # Asincrono: solo se encola; la respuesta no espera a Kinesis (R2).
    events.publisher.publish_async(events.search_event(
        session_id=x_session_id or uuid.uuid4().hex, origin=origin, destination=destination,
        travel_date=fecha.isoformat(), results_count=len(rows)))
    return [dict(r) for r in rows]


@app.post("/reservations", response_model=ReservationOut, status_code=201)
def crear_reserva(r: ReservationIn):
    reservation_id = uuid.uuid4().hex
    with engine.begin() as conn:  # una sola transaccion: cupo + reserva
        vuelo = conn.execute(
            text(
                "UPDATE flights SET seats_sold = seats_sold + 1 "
                "WHERE flight_id = :fid AND seats_sold < capacity "
                "RETURNING route, flight_date, price_cents"
            ),
            {"fid": r.flight_id},
        ).mappings().first()
        if vuelo is None:
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
    # DESPUES del commit: nunca se publica una reserva que no quedo guardada.
    events.publisher.publish_sync(events.booking_event(
        "reservation_created", reservation_id, r.flight_id, vuelo["route"],
        str(vuelo["flight_date"]), r.fare_class, vuelo["price_cents"]))
    return ReservationOut(reservation_id=reservation_id, flight_id=r.flight_id,
                          status="CONFIRMED", passenger_name=r.passenger_name)


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


@app.post("/reservations/{reservation_id}/cancel", response_model=ReservationOut)
def cancelar_reserva(reservation_id: str):
    with engine.begin() as conn:
        # Condicional igual que la reserva: dos cancelaciones simultaneas -> solo una gana.
        res = conn.execute(
            text(
                "UPDATE reservations SET status = 'CANCELLED' "
                "WHERE reservation_id = :rid AND status <> 'CANCELLED' "
                "RETURNING reservation_id, flight_id, passenger_name, fare_class"
            ),
            {"rid": reservation_id},
        ).mappings().first()
        if res is None:
            existe = conn.execute(
                text("SELECT 1 FROM reservations WHERE reservation_id = :rid"), {"rid": reservation_id}
            ).first()
            if existe is None:
                raise HTTPException(status_code=404, detail="reserva no encontrada")
            raise HTTPException(status_code=409, detail="la reserva ya estaba cancelada")
        vuelo = conn.execute(  # libera el asiento
            text(
                "UPDATE flights SET seats_sold = seats_sold - 1 WHERE flight_id = :fid "
                "RETURNING route, flight_date, price_cents"
            ),
            {"fid": res["flight_id"]},
        ).mappings().first()
    events.publisher.publish_sync(events.booking_event(
        "reservation_cancelled", reservation_id, res["flight_id"], vuelo["route"],
        str(vuelo["flight_date"]), res["fare_class"], vuelo["price_cents"]))
    return ReservationOut(reservation_id=reservation_id, flight_id=res["flight_id"],
                          status="CANCELLED", passenger_name=res["passenger_name"])


@app.get("/analytics/live", response_model=LiveOut)
def vista_en_vivo(window: int = Query(5, ge=1, le=settings.live_max_window_minutes)):
    # Sale de memoria (lo que el consumidor leyo del stream): no consulta Athena ni la base.
    return live.counter.counts(window)


@app.post("/admin/refresh-star", status_code=202)
def refrescar_estrella():
    return {"job_id": star.job.request(), "state": "RUNNING"}


@app.get("/admin/refresh-status")
def estado_refresco():
    return JSONResponse(star.job.state())


# --- Frontend (React compilado): mismo proceso y mismo origen ---
_FRONTEND = pathlib.Path(
    os.environ.get("FRONTEND_DIR", pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist")
)
if _FRONTEND.is_dir():

    @app.get("/manager", include_in_schema=False)
    @app.get("/manager/", include_in_schema=False)
    def panel_gerencial():
        return FileResponse(_FRONTEND / "index.html")

    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="frontend")
