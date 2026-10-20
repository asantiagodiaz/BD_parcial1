"""Crea vuelos de demostracion en la API (POST /admin/flights) para probar el frontend.

Un vuelo por ruta y por dia, con las 9 rutas de la semilla 963. Es idempotente: si el
vuelo ya existe la API responde 409 y se cuenta como "ya existian". Solo usa la
libreria estandar.

Uso:
  python parcial2/tools/crear_vuelos.py --api http://<ip>:8000
  python parcial2/tools/crear_vuelos.py --api http://127.0.0.1:8000 --dias 30 --capacidad 150
"""

import argparse
import datetime as dt
import json
import urllib.error
import urllib.request

# Rutas del equipo (semilla 963, ver parcial2/BITACORA.md)
RUTAS = [
    "CUC-BGA", "CTG-BOG", "CUC-SMR", "ADZ-CTG", "PSO-SMR",
    "SMR-BAQ", "ADZ-BAQ", "PSO-CUC", "BGA-BOG",
    # tambien la inversa de las mas comunes, para poder probar BOG-MDE como en las capturas
    "BOG-MDE", "MDE-BOG",
]


def crear(api: str, vuelo: dict) -> int:
    req = urllib.request.Request(
        f"{api}/admin/flights",
        data=json.dumps(vuelo).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api", required=True, help="URL base, p. ej. http://32.192.74.169:8000")
    ap.add_argument("--dias", type=int, default=14, help="cuantos dias hacia adelante (por defecto 14)")
    ap.add_argument("--capacidad", type=int, default=150)
    a = ap.parse_args()
    api = a.api.rstrip("/")

    hoy = dt.date.today()
    nuevos = existian = errores = 0
    for d in range(a.dias):
        fecha = hoy + dt.timedelta(days=d)
        for i, ruta in enumerate(RUTAS):
            vuelo = {
                "flight_id": f"RA-{ruta}-{fecha:%Y%m%d}",
                "route": ruta,
                "flight_date": fecha.isoformat(),
                "capacity": a.capacidad,
                "price_cents": (250_000 + 15_000 * i) * 100,  # en centavos de COP
            }
            codigo = crear(api, vuelo)
            if codigo == 201:
                nuevos += 1
            elif codigo == 409:
                existian += 1
            else:
                errores += 1
                print(f"  error {codigo} creando {vuelo['flight_id']}")

    print(f"vuelos creados: {nuevos} | ya existian: {existian} | errores: {errores}")
    print(f"Prueba en el navegador: {api}/  (por ejemplo BOG -> MDE, fecha {hoy:%Y-%m-%d})")


if __name__ == "__main__":
    main()
