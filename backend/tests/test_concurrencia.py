"""Prueba de concurrencia contra la sobreventa - EVIDENCIA para la seccion 5.6.

Escenario del NFR-03 (docs/02): N clientes intentan reservar SIMULTANEAMENTE
el ultimo asiento de un vuelo. El sistema debe garantizar:

  - exactamente 1 reserva CONFIRMADA/RETENIDA,
  - las otras N-1 rechazadas con HTTP 409,
  - invariante: asientos_vendidos + asientos_retenidos <= asientos_totales.

Mecanismo verificado: bloqueo pesimista (SELECT ... FOR UPDATE) en
app/services/booking.py, decision de docs/04 seccion 5.4.2.

Cada hilo abre su PROPIA conexion/transaccion a PostgreSQL (como harian N
procesos web reales). No se comparte la Session entre hilos.
"""

from __future__ import annotations

import concurrent.futures as cf

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db import SessionLocal
from app.models import InventarioAsientos
from app.schemas import PasajeroIn, ReservaIn, SegmentoIn
from app.services import booking

N_CLIENTES = 20


def _intentar_reserva(data: dict, indice: int) -> tuple[int, str]:
    """Una reserva completa en su propia transaccion. Devuelve (indice, resultado)."""
    db = SessionLocal()
    try:
        payload = ReservaIn(
            segmentos=[
                SegmentoIn(
                    id_instancia_vuelo=data["id_instancia_vuelo"],
                    cabina="ECONOMICA",
                    id_tarifa=data["id_tarifa"],
                )
            ],
            pasajeros=[
                PasajeroIn(
                    tipo_documento="CC",
                    numero_documento=f"C{indice:05d}",
                    nombre_completo=f"Pasajero {indice}",
                    es_contacto_principal=True,
                )
            ],
        )
        reserva = booking.crear_reserva(db, payload)
        db.commit()
        return indice, f"OK:{reserva.codigo_reserva}"
    except HTTPException as exc:
        db.rollback()
        return indice, f"HTTP {exc.status_code}"
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return indice, f"ERR:{type(exc).__name__}:{exc}"
    finally:
        db.close()


@pytest.mark.usefixtures("limpiar_reservas")
def test_no_sobreventa_con_N_clientes_simultaneos(datos_base, capsys):
    data = datos_base

    with cf.ThreadPoolExecutor(max_workers=N_CLIENTES) as pool:
        resultados = list(
            pool.map(lambda i: _intentar_reserva(data, i), range(N_CLIENTES))
        )

    exitos = [r for _, r in resultados if r.startswith("OK")]
    conflictos = [r for _, r in resultados if r == "HTTP 409"]
    otros = [r for _, r in resultados if not r.startswith("OK") and r != "HTTP 409"]

    # --- inventario final ---
    s = SessionLocal()
    inv = s.scalar(
        select(InventarioAsientos).where(
            InventarioAsientos.id_instancia_vuelo == data["id_instancia_vuelo"],
            InventarioAsientos.cabina == "ECONOMICA",
        )
    )
    vendidos, retenidos, totales = (
        inv.asientos_vendidos,
        inv.asientos_retenidos,
        inv.asientos_totales,
    )
    s.close()

    # --- EVIDENCIA impresa (queda en el log del test) ---
    with capsys.disabled():
        print("\n" + "=" * 64)
        print(f"PRUEBA DE CONCURRENCIA  -  {N_CLIENTES} clientes por 1 asiento")
        print("=" * 64)
        print(f"  reservas OK (hold)     : {len(exitos)}   {exitos}")
        print(f"  rechazos HTTP 409      : {len(conflictos)}")
        print(f"  otros errores          : {len(otros)}   {otros}")
        print(f"  inventario final       : vendidos={vendidos} retenidos={retenidos} "
              f"totales={totales}")
        print(f"  invariante (v+r <= t)  : "
              f"{vendidos + retenidos} <= {totales}  -> "
              f"{'OK' if vendidos + retenidos <= totales else 'FALLA'}")
        print("=" * 64)

    # --- aserciones (NFR-03) ---
    assert not otros, f"errores inesperados: {otros}"
    assert len(exitos) == 1, f"se esperaba 1 reserva, hubo {len(exitos)}"
    assert len(conflictos) == N_CLIENTES - 1
    assert vendidos + retenidos <= totales, "SOBREVENTA: invariante violado"
    assert retenidos == 1, f"se esperaba 1 asiento retenido, hay {retenidos}"


@pytest.mark.usefixtures("limpiar_reservas")
def test_segunda_tanda_ya_no_hay_cupo(datos_base):
    """Tras agotar el asiento, cualquier nueva reserva -> 409."""
    data = datos_base
    idx, r1 = _intentar_reserva(data, 100)
    assert r1.startswith("OK")
    idx, r2 = _intentar_reserva(data, 101)
    assert r2 == "HTTP 409"
