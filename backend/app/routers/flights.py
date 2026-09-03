import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import InventarioAsientos
from app.schemas import BusquedaResultado, DisponibilidadOut
from app.services import search

router = APIRouter(prefix="/flights", tags=["vuelos"])


@router.get("/search", response_model=BusquedaResultado)
def buscar_vuelos(
    origin: str = Query(..., min_length=3, max_length=3, description="IATA origen"),
    dest: str = Query(..., min_length=3, max_length=3, description="IATA destino"),
    date: dt.date = Query(..., description="fecha de salida"),
    pax: int = Query(1, ge=1, le=9),
    cabin: str = Query("ECONOMICA"),
    with_stops: bool = Query(True, description="incluir itinerarios con 1 escala"),
    db: Session = Depends(get_db),
):
    """FR-01 / FR-02 / FR-03: busca vuelos directos y con 1 escala."""
    return search.buscar(db, origin, dest, date, pax, cabin, with_stops)


@router.get("/{id_instancia_vuelo}/availability", response_model=DisponibilidadOut)
def disponibilidad(id_instancia_vuelo: int, cabin: str = "ECONOMICA", db: Session = Depends(get_db)):
    """Contador orientativo para el polling del frontend (NFR-03, best-effort)."""
    inv = db.scalar(
        select(InventarioAsientos).where(
            InventarioAsientos.id_instancia_vuelo == id_instancia_vuelo,
            InventarioAsientos.cabina == cabin.upper(),
        )
    )
    if inv is None:
        from fastapi import HTTPException

        raise HTTPException(404, "vuelo/cabina no encontrado")
    return DisponibilidadOut(
        id_instancia_vuelo=id_instancia_vuelo,
        cabina=cabin.upper(),
        asientos_disponibles=inv.disponibles,
    )
