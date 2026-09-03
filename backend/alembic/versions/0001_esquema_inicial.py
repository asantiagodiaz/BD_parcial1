"""Esquema inicial - implementa el modelo entidad-relacion de docs/03.

Crea todas las tablas desde Base.metadata y anade el trigger que hace
EVENTO_RESERVA append-only (NFR-09): rechaza UPDATE y DELETE.

Revision ID: 0001
Revises:
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op

from app.db import Base
import app.models  # noqa: F401

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGER_APPEND_ONLY = """
CREATE OR REPLACE FUNCTION evento_reserva_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'evento_reserva es append-only (NFR-09): no se permite % ', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_evento_reserva_append_only
BEFORE UPDATE OR DELETE ON evento_reserva
FOR EACH ROW EXECUTE FUNCTION evento_reserva_append_only();
"""


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    op.execute(_TRIGGER_APPEND_ONLY)


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP TRIGGER IF EXISTS trg_evento_reserva_append_only ON evento_reserva")
    op.execute("DROP FUNCTION IF EXISTS evento_reserva_append_only()")
    Base.metadata.drop_all(bind=bind)
