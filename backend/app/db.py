from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# pool_pre_ping evita conexiones muertas tras suspender la instancia RDS del Learner Lab.
engine = create_engine(settings.oltp_database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesion por request, siempre cerrada."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
