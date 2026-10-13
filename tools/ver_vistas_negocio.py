"""Consulta las 3 vistas de negocio del pipeline analitico (OLAP) en AWS
(uso local para la sustentacion, no forma parte de la entrega).

Responden las 3 preguntas de negocio del enunciado (seccion 2):
ocupacion por ruta, ingresos por tarifa, y patrones de cancelacion.

Uso:
    OLAP_DATABASE_URL=postgresql://usuario:clave@host:5432/aerolinea python tools/ver_vistas_negocio.py
"""
import os
import sys

import psycopg

DB_URL = os.environ.get("OLAP_DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
if not DB_URL:
    sys.exit("Falta la variable de entorno OLAP_DATABASE_URL")

VISTAS = [
    ("v_ocupacion_por_ruta", "Ocupacion por ruta"),
    ("v_ingresos_por_tarifa", "Ingresos por tarifa"),
    ("v_patrones_cancelacion", "Patrones de cancelacion"),
]


def main() -> None:
    conn = psycopg.connect(DB_URL, connect_timeout=8)
    cur = conn.cursor()

    for vista, titulo in VISTAS:
        print("=" * 70)
        print(titulo, f"({vista})")
        print("=" * 70)
        cur.execute(f"SELECT * FROM {vista}")
        columnas = [c.name for c in cur.description]
        print(" | ".join(columnas))
        for fila in cur.fetchall():
            print(" | ".join(str(v) for v in fila))
        print()

    conn.close()


if __name__ == "__main__":
    main()
