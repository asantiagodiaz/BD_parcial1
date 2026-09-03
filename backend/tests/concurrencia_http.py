"""Prueba de concurrencia contra la API HTTP EN VIVO (no la capa de servicio).

Complementa tests/test_concurrencia.py: demuestra el mismo escenario del NFR-03
lanzando N peticiones HTTP reales y simultaneas contra POST /reservations.

Uso:
    # 1. levantar db + api  (ver README)
    # 2. dejar 1 asiento en un vuelo:
    #    python -m tests.concurrencia_http --preparar
    # 3. lanzar la prueba:
    #    python -m tests.concurrencia_http --instancia <id> --tarifa <id> --n 20
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf

import requests
from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import InstanciaVuelo, InventarioAsientos, VueloProgramado

API = "http://127.0.0.1:8000"


def preparar() -> None:
    """Deja el vuelo RA101 (primera instancia) con 1 asiento ECONOMICA libre."""
    s = SessionLocal()
    inst = s.scalar(
        select(InstanciaVuelo)
        .join(VueloProgramado)
        .where(VueloProgramado.numero_vuelo == "RA101")
        .order_by(InstanciaVuelo.fecha_salida)
    )
    inv = s.scalar(
        select(InventarioAsientos).where(
            InventarioAsientos.id_instancia_vuelo == inst.id_instancia_vuelo,
            InventarioAsientos.cabina == "ECONOMICA",
        )
    )
    s.execute(text("DELETE FROM billete"))
    s.execute(text("DELETE FROM evento_reserva"))
    s.execute(text("DELETE FROM segmento_itinerario"))
    s.execute(text("DELETE FROM itinerario"))
    s.execute(text("DELETE FROM reserva_pasajero"))
    s.execute(text("DELETE FROM pago"))
    s.execute(text("DELETE FROM reserva"))
    inv.asientos_vendidos = inv.asientos_totales - 1
    inv.asientos_retenidos = 0
    s.commit()
    tarifa_id = s.execute(
        text(
            "SELECT t.id_tarifa FROM tarifa t JOIN vuelo_programado vp ON vp.id_ruta = t.id_ruta "
            "WHERE vp.numero_vuelo='RA101' AND t.cabina='ECONOMICA' ORDER BY t.monto_precio LIMIT 1"
        )
    ).scalar()
    print(f"instancia={inst.id_instancia_vuelo}  tarifa={tarifa_id}  ECONOMICA disponibles=1")
    s.close()


def _post(i: int, instancia: int, tarifa: int) -> str:
    body = {
        "segmentos": [{"id_instancia_vuelo": instancia, "cabina": "ECONOMICA", "id_tarifa": tarifa}],
        "pasajeros": [
            {
                "tipo_documento": "CC",
                "numero_documento": f"H{i:05d}",
                "nombre_completo": f"Cliente HTTP {i}",
                "es_contacto_principal": True,
            }
        ],
    }
    r = requests.post(f"{API}/reservations", json=body, timeout=10)
    if r.status_code == 201:
        return f"201 {r.json()['codigo_reserva']}"
    return f"{r.status_code}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preparar", action="store_true")
    ap.add_argument("--instancia", type=int)
    ap.add_argument("--tarifa", type=int)
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()

    if args.preparar:
        preparar()
        return

    with cf.ThreadPoolExecutor(max_workers=args.n) as pool:
        res = list(pool.map(lambda i: _post(i, args.instancia, args.tarifa), range(args.n)))

    ok = [x for x in res if x.startswith("201")]
    c409 = [x for x in res if x == "409"]
    otros = [x for x in res if not x.startswith("201") and x != "409"]

    print("=" * 60)
    print(f"POST /reservations x{args.n} simultaneos por 1 asiento")
    print(f"  201 Created : {len(ok)}   {ok}")
    print(f"  409 Conflict: {len(c409)}")
    print(f"  otros       : {len(otros)}   {otros}")
    print("=" * 60)
    assert len(ok) == 1 and len(c409) == args.n - 1 and not otros, "FALLA: sobreventa o error"
    print("OK: exactamente 1 reserva, sin sobreventa")


if __name__ == "__main__":
    main()
