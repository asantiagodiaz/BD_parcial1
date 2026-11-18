"""Eventos de negocio y su publicacion en Kinesis (contrato: harness/contract/EVENTS.md).

Dos formas de publicar, porque los eventos no valen lo mismo:

* Busquedas (`publish_async`): muchas y prescindibles. Se encolan en memoria y un hilo las
  envia en lotes con PutRecords. La peticion HTTP nunca espera a Kinesis (R2: p95 <= 1 s).
  Si la cola se llena o Kinesis falla demasiadas veces, la busqueda se pierde: es aceptable.
* Reservas y cancelaciones (`publish_sync`): pocas y son transacciones de negocio. Se envian
  con PutRecord dentro de la peticion, DESPUES del commit, con reintentos. Si aun asi fallan
  se registra el error. En produccion se usaria el patron outbox (fila en la misma
  transaccion + un publicador que la reintenta hasta confirmar); aqui solo se describe.

Ningun evento lleva el nombre del pasajero ni otros datos personales.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import queue
import threading
import time
import uuid

from app.config import settings

log = logging.getLogger("airline.events")


def now_ts() -> str:
    """Momento en que ocurre el evento, UTC, YYYY-MM-DDTHH:MM:SSZ."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(event_type: str) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_ts": now_ts(),
        "schema_version": 1,
    }


def search_event(session_id: str, origin: str, destination: str, travel_date: str, results_count: int) -> dict:
    e = _envelope("search_performed")
    e.update(session_id=session_id, origin=origin, destination=destination,
             travel_date=travel_date, results_count=int(results_count))
    return e


def booking_event(event_type: str, reservation_id: str, flight_id: str, route: str,
                  flight_date: str, fare_class: str, price_cents: int) -> dict:
    e = _envelope(event_type)
    e.update(reservation_id=reservation_id, flight_id=flight_id, route=route,
             flight_date=flight_date, fare_class=fare_class, price_cents=int(price_cents))
    return e


def partition_key(e: dict) -> str:
    """search -> session_id (reparte la carga); reservas -> flight_id (orden por vuelo)."""
    return e["session_id"] if e["event_type"] == "search_performed" else e["flight_id"]


def encode(e: dict) -> bytes:
    # Un evento por registro de Kinesis, JSON compacto. El salto de linea en S3 lo agrega
    # Firehose (AppendDelimiterToRecord), asi tambien quedan separados los eventos que otros
    # productores escriben sin "\n".
    return json.dumps(e, separators=(",", ":")).encode()


class Publisher:
    def __init__(self) -> None:
        self.stream = settings.kinesis_stream
        self._q: queue.Queue[dict] = queue.Queue(maxsize=settings.search_queue_max)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._client = None
        self.dropped = 0
        self.sent = 0

    @property
    def enabled(self) -> bool:
        return bool(self.stream)

    def _kinesis(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "kinesis", region_name=settings.aws_region,
                config=Config(connect_timeout=3, read_timeout=10,
                              retries={"max_attempts": 4, "mode": "standard"}))
        return self._client

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="search-publisher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------------ busquedas
    def publish_async(self, e: dict) -> None:
        if not self.enabled:
            return
        try:
            self._q.put_nowait(e)
        except queue.Full:
            self.dropped += 1  # perder una busqueda es aceptable; frenar la API no

    def _next_batch(self) -> list[dict]:
        try:
            batch = [self._q.get(timeout=0.5)]
        except queue.Empty:
            return []
        deadline = time.monotonic() + settings.search_linger_seconds
        while len(batch) < settings.search_batch_max:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            try:
                batch.append(self._q.get(timeout=left))
            except queue.Empty:
                break
        return batch

    def _run(self) -> None:
        while not (self._stop.is_set() and self._q.empty()):
            batch = self._next_batch()
            if batch:
                self._send_batch(batch)

    def _send_batch(self, batch: list[dict]) -> None:
        """PutRecords reintentando SOLO los registros que fallaron (sin duplicar los demas)."""
        pending = batch
        for attempt in range(8):
            try:
                r = self._kinesis().put_records(
                    StreamName=self.stream,
                    Records=[{"Data": encode(e), "PartitionKey": partition_key(e)} for e in pending])
            except Exception as ex:  # red / throttling de toda la llamada
                log.warning("PutRecords fallo (intento %d): %s", attempt + 1, ex)
                time.sleep(min(0.2 * 2 ** attempt, 5))
                continue
            failed = [e for e, res in zip(pending, r["Records"]) if "ErrorCode" in res]
            self.sent += len(pending) - len(failed)
            if not failed:
                return
            pending = failed
            time.sleep(min(0.2 * 2 ** attempt, 5))
        self.dropped += len(pending)
        log.error("se descartaron %d eventos de busqueda tras reintentar", len(pending))

    # ------------------------------------------------------------------ reservas
    def publish_sync(self, e: dict, attempts: int = 5) -> bool:
        if not self.enabled:
            return False
        for attempt in range(attempts):
            try:
                self._kinesis().put_record(StreamName=self.stream, Data=encode(e), PartitionKey=partition_key(e))
                self.sent += 1
                return True
            except Exception as ex:
                log.warning("PutRecord %s fallo (intento %d): %s", e["event_id"], attempt + 1, ex)
                time.sleep(min(0.2 * 2 ** attempt, 3))
        # En produccion: el evento quedaria en la tabla outbox y se reintentaria despues.
        log.error("no se pudo publicar %s %s", e["event_type"], e["event_id"])
        return False


publisher = Publisher()
