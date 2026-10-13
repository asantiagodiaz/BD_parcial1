"""Script de consulta rapida a la RDS OLTP en AWS (uso local, no forma parte de la entrega).
Uso:  OLTP_DATABASE_URL=postgresql://usuario:clave@host:5432/aerolinea python tools/consultar_reservas.py
"""
import os
import sys

import psycopg

DB_URL = os.environ.get("OLTP_DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
if not DB_URL:
    sys.exit("Falta la variable de entorno OLTP_DATABASE_URL")

conn = psycopg.connect(DB_URL, connect_timeout=8)
cur = conn.cursor()
cur.execute(
    """
    SELECT codigo_reserva, estado, canal, monto_total, creada_en
    FROM reserva
    ORDER BY creada_en DESC
    LIMIT 10
    """
)
print(f"{'codigo':<8} {'estado':<12} {'canal':<8} {'monto':>12}  creada_en")
for codigo, estado, canal, monto, creada_en in cur.fetchall():
    print(f"{codigo:<8} {estado:<12} {canal:<8} {monto:>12}  {creada_en}")

conn.close()
