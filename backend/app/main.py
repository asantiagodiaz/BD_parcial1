from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import flights, reservations

app = FastAPI(
    title="API de reservas aereas - Parcial 1 Big Data",
    version="0.1.0",
    description=(
        "Primera implementacion del backend (seccion 5.6). "
        "Operaciones criticas: buscar vuelos, crear reserva (con bloqueo pesimista), "
        "consultar reserva."
    ),
)

# La SPA (5.5) es un origen distinto (Vite en :5173, o el sitio estatico de S3),
# asi que necesita CORS. `cors_origins` se configura en .env; por defecto abierto
# para la demo del Learner Lab.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(flights.router)
app.include_router(reservations.router)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}
