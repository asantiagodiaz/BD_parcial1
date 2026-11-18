"""Camino rapido: consumidor del stream de Kinesis que alimenta GET /analytics/live (R3).

Un hilo del mismo proceso de la API lee el unico shard cada `live_poll_seconds` con
GetRecords (consumidor estandar: sin enhanced fan-out, R11) y guarda en memoria los eventos
de la ultima hora, indexados por event_id:

* Cuenta por event_ts (cuando ocurrio), no por la hora de llegada: un evento viejo que llega
  tarde (o el replay del harness, con fechas de 2025) cae fuera de la ventana.
* Deduplica por event_id: un reintento del productor no se cuenta dos veces.
* Al arrancar lee desde hace `live_max_window_minutes` (AT_TIMESTAMP), asi un reinicio de la
  API no deja la vista en cero.

Por que no Athena: Athena tarda segundos por consulta, cobra por datos escaneados y lee la
landing zone, que llega con el retraso del bufer de Firehose (~60 s). El requisito pide ver
un evento en menos de 10 s.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time

from app.config import settings

log = logging.getLogger("airline.live")
UTC = dt.timezone.utc
TYPES = {"search_performed": "searches", "reservation_created": "reservations",
         "reservation_cancelled": "cancellations"}


def _parse_ts(s: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


class LiveCounter:
    """Eventos recientes por event_id. Seguro para hilos."""

    def __init__(self, keep_minutes: int) -> None:
        self.keep = dt.timedelta(minutes=keep_minutes)
        self._events: dict[str, tuple[str, dt.datetime]] = {}
        self._lock = threading.Lock()

    def add(self, e: dict, now: dt.datetime | None = None) -> bool:
        kind = TYPES.get(e.get("event_type"))
        ts = _parse_ts(e.get("event_ts"))
        eid = e.get("event_id")
        if not kind or ts is None or not eid:
            return False
        now = now or dt.datetime.now(UTC)
        if ts < now - self.keep:  # demasiado viejo para cualquier ventana: no se guarda
            return False
        with self._lock:
            self._events.setdefault(eid, (kind, ts))
        return True

    def prune(self, now: dt.datetime | None = None) -> None:
        cutoff = (now or dt.datetime.now(UTC)) - self.keep
        with self._lock:
            for k in [k for k, (_, ts) in self._events.items() if ts < cutoff]:
                del self._events[k]

    def counts(self, window_minutes: int, now: dt.datetime | None = None) -> dict:
        now = now or dt.datetime.now(UTC)
        start = now - dt.timedelta(minutes=window_minutes)
        # Tolerancia de 60 s hacia el futuro por diferencias de reloj entre productores.
        end = now + dt.timedelta(seconds=60)
        out = {"searches": 0, "reservations": 0, "cancellations": 0}
        with self._lock:
            for kind, ts in self._events.values():
                if start < ts <= end:
                    out[kind] += 1
        conv = out["reservations"] / out["searches"] if out["searches"] else 0.0
        return {"window_minutes": window_minutes, **out, "conversion": round(conv, 6)}


class StreamConsumer:
    def __init__(self, counter: LiveCounter) -> None:
        self.counter = counter
        self.stream = settings.kinesis_stream
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.records_read = 0
        self.last_poll: dt.datetime | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        if not self.stream or self._thread:
            return
        self._thread = threading.Thread(target=self._run, name="live-consumer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def _client(self):
        import boto3
        from botocore.config import Config

        return boto3.client("kinesis", region_name=settings.aws_region,
                            config=Config(connect_timeout=3, read_timeout=10,
                                          retries={"max_attempts": 3, "mode": "standard"}))

    def _iterators(self, k, positions: dict[str, str]) -> dict[str, str]:
        """Un iterador por shard abierto: continua tras el ultimo leido o empieza hace 1 h."""
        its = {}
        start = dt.datetime.now(UTC) - dt.timedelta(minutes=settings.live_max_window_minutes)
        for sh in k.list_shards(StreamName=self.stream)["Shards"]:
            sid = sh["ShardId"]
            if sid in positions:
                kw = {"ShardIteratorType": "AFTER_SEQUENCE_NUMBER", "StartingSequenceNumber": positions[sid]}
            else:
                kw = {"ShardIteratorType": "AT_TIMESTAMP", "Timestamp": start}
            its[sid] = k.get_shard_iterator(StreamName=self.stream, ShardId=sid, **kw)["ShardIterator"]
        return its

    def _run(self) -> None:
        positions: dict[str, str] = {}
        its: dict[str, str] = {}
        k = None
        last_prune = time.monotonic()
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                if k is None:
                    k = self._client()
                if not its:
                    its = self._iterators(k, positions)
                for sid, it in list(its.items()):
                    # Varias paginas seguidas solo si hay atraso (p. ej. tras el replay).
                    for _ in range(10):
                        r = k.get_records(ShardIterator=it, Limit=10000)
                        for rec in r["Records"]:
                            positions[sid] = rec["SequenceNumber"]
                            try:
                                self.counter.add(json.loads(rec["Data"]))
                            except (ValueError, TypeError):
                                pass
                        self.records_read += len(r["Records"])
                        it = r.get("NextShardIterator")
                        if not it or r.get("MillisBehindLatest", 0) == 0:
                            break
                        time.sleep(0.25)
                    if it:
                        its[sid] = it
                    else:  # shard cerrado (resharding): se vuelven a listar
                        its = {}
                self.last_poll = dt.datetime.now(UTC)
                self.last_error = None
            except Exception as ex:  # iterador vencido, throttling, stream borrado...
                self.last_error = str(ex)
                log.warning("consumidor: %s", ex)
                its = {}
                time.sleep(2)
            if time.monotonic() - last_prune > 30:
                self.counter.prune()
                last_prune = time.monotonic()
            self._stop.wait(max(0.0, settings.live_poll_seconds - (time.monotonic() - t0)))


counter = LiveCounter(settings.live_max_window_minutes)
consumer = StreamConsumer(counter)
