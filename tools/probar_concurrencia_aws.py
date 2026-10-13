"""Prueba de concurrencia EN VIVO contra la API desplegada en AWS (uso local
para la sustentacion, no forma parte de la entrega).

Deja 1 asiento libre en el vuelo RA101 (via conexion directa a la RDS OLTP) y
lanza N peticiones HTTP simultaneas de reserva contra POST /reservations.
Resultado esperado: 1x 201 Created, (N-1)x 409 Conflict, sin sobreventa.

Uso:
    API_URL=http://<ip-ec2>:8000 OLTP_DATABASE_URL=postgresql://usuario:clave@host:5432/aerolinea \\
        python tools/probar_concurrencia_aws.py
"""
import concurrent.futures as cf
import json
import os
import sys
import urllib.error
import urllib.request

import psycopg

API_URL = os.environ.get("API_URL", "").rstrip("/")  # IP actual de la EC2 (ver validar.sh)
DB_URL = os.environ.get("OLTP_DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
if not API_URL or not DB_URL:
    sys.exit("Faltan las variables de entorno API_URL y/o OLTP_DATABASE_URL")
N = 20


def preparar() -> tuple[int, int]:
    """Deja el vuelo RA101 (primera instancia) con 1 asiento ECONOMICA libre."""
    conn = psycopg.connect(DB_URL, connect_timeout=8)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT iv.id_instancia_vuelo
        FROM instancia_vuelo iv
        JOIN vuelo_programado vp ON vp.id_vuelo_programado = iv.id_vuelo_programado
        WHERE vp.numero_vuelo = 'RA101'
        ORDER BY iv.salida_utc
        LIMIT 1
        """
    )
    id_instancia = cur.fetchone()[0]

    cur.execute(
        """
        SELECT id_inventario_asientos, asientos_totales
        FROM inventario_asientos
        WHERE id_instancia_vuelo = %s AND cabina = 'ECONOMICA'
        """,
        (id_instancia,),
    )
    id_inventario, totales = cur.fetchone()

    cur.execute(
        """
        UPDATE inventario_asientos
        SET asientos_vendidos = %s, asientos_retenidos = 0
        WHERE id_inventario_asientos = %s
        """,
        (totales - 1, id_inventario),
    )

    cur.execute(
        """
        SELECT t.id_tarifa
        FROM tarifa t
        JOIN vuelo_programado vp ON vp.id_ruta = t.id_ruta
        WHERE vp.numero_vuelo = 'RA101' AND t.cabina = 'ECONOMICA'
        ORDER BY t.monto_precio
        LIMIT 1
        """
    )
    id_tarifa = cur.fetchone()[0]

    conn.commit()
    conn.close()
    print(f"preparado: instancia={id_instancia}  tarifa={id_tarifa}  ECONOMICA disponibles=1")
    return id_instancia, id_tarifa


def post_reserva(i: int, id_instancia: int, id_tarifa: int) -> int:
    body = {
        "segmentos": [{"id_instancia_vuelo": id_instancia, "cabina": "ECONOMICA", "id_tarifa": id_tarifa}],
        "pasajeros": [
            {
                "tipo_documento": "CC",
                "numero_documento": f"H{i:05d}",
                "nombre_completo": f"Cliente Concurrencia {i}",
                "es_contacto_principal": True,
            }
        ],
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_URL}/reservations",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    id_instancia, id_tarifa = preparar()

    with cf.ThreadPoolExecutor(max_workers=N) as pool:
        resultados = list(pool.map(lambda i: post_reserva(i, id_instancia, id_tarifa), range(N)))

    ok = resultados.count(201)
    conflicto = resultados.count(409)
    otros = [r for r in resultados if r not in (201, 409)]

    print("=" * 60)
    print(f"POST /reservations x{N} simultaneos por 1 asiento (vuelo RA101)")
    print(f"  201 Created : {ok}")
    print(f"  409 Conflict: {conflicto}")
    print(f"  otros       : {otros}")
    print("=" * 60)
    if ok == 1 and conflicto == N - 1 and not otros:
        print("OK: exactamente 1 reserva confirmada, sin sobreventa (NFR-03)")
    else:
        print("ATENCION: el resultado no coincide con lo esperado, revisar")


if __name__ == "__main__":
    main()
