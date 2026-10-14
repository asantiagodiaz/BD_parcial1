"""Consulta de ocupacion en Athena (R7).

Cada peticion a /analytics/occupancy lanza una consulta real a Athena sobre la
tabla route_month_metrics (el harness revisa el historial de consultas). No hay
cache: con 5 pares de prueba el costo por consulta es de fracciones de centavo
y evitamos servir datos viejos.
"""

import re
import time

import boto3

from app.config import settings

_ROUTE = re.compile(r"^[A-Z]{3}-[A-Z]{3}$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

_client = None


def _athena():
    global _client
    if _client is None:
        _client = boto3.client("athena", region_name=settings.aws_region)
    return _client


def query_occupancy(route: str, month: str) -> dict | None:
    """Devuelve {route, month, occupancy, seats_sold, seats_capacity} o None si no hay datos."""
    # Los valores se interpolan en el SQL (Athena no admite parametros en este
    # modo simple), por eso se validan con una lista blanca estricta.
    if not _ROUTE.match(route) or not _MONTH.match(month):
        raise ValueError("route o month con formato invalido")

    sql = (
        "SELECT route, month, occupancy, seats_sold, seats_capacity "
        f"FROM {settings.athena_database}.{settings.athena_metrics_table} "
        f"WHERE route = '{route}' AND month = '{month}' LIMIT 1"
    )
    kwargs = {
        "QueryString": sql,
        "WorkGroup": settings.athena_workgroup,
        "QueryExecutionContext": {"Database": settings.athena_database},
    }
    if settings.athena_output:
        kwargs["ResultConfiguration"] = {"OutputLocation": settings.athena_output}

    client = _athena()
    qid = client.start_query_execution(**kwargs)["QueryExecutionId"]

    deadline = time.monotonic() + settings.athena_timeout_seconds
    delay = 0.25
    while True:
        state = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if state["State"] == "SUCCEEDED":
            break
        if state["State"] in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena {state['State']}: {state.get('StateChangeReason', '')}")
        if time.monotonic() > deadline:
            raise TimeoutError("Athena no respondio a tiempo")
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)

    rows = client.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    if len(rows) < 2:  # la fila 0 es el encabezado
        return None
    v = [c.get("VarCharValue") for c in rows[1]["Data"]]
    return {
        "route": v[0],
        "month": v[1],
        "occupancy": float(v[2]),
        "seats_sold": int(v[3]),
        "seats_capacity": int(v[4]),
    }
