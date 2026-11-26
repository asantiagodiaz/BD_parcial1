"""Pruebas unitarias (sin AWS ni base): contador en vivo y contrato de eventos.

    cd parcial3/backend && .venv/bin/pytest -q
"""

import datetime as dt
import json

from app import events
from app.live import LiveCounter

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC)


def ev(eid, kind, minutes_ago):
    ts = (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"event_id": eid, "event_type": kind, "event_ts": ts}


def test_cuenta_por_event_ts_no_por_llegada():
    c = LiveCounter(60)
    c.add(ev("a", "search_performed", 1), now=NOW)
    c.add(ev("b", "search_performed", 4), now=NOW)
    c.add(ev("c", "search_performed", 10), now=NOW)       # fuera de la ventana de 5 min
    c.add({"event_id": "old", "event_type": "search_performed", "event_ts": "2025-01-15T10:00:00Z"}, now=NOW)
    out = c.counts(5, now=NOW)
    assert out["searches"] == 2
    assert c.counts(15, now=NOW)["searches"] == 3


def test_deduplica_por_event_id():
    c = LiveCounter(60)
    for _ in range(3):
        c.add(ev("dup", "reservation_created", 1), now=NOW)
    assert c.counts(5, now=NOW)["reservations"] == 1


def test_conversion_y_cero_sin_busquedas():
    c = LiveCounter(60)
    assert c.counts(5, now=NOW)["conversion"] == 0.0
    for i in range(4):
        c.add(ev(f"s{i}", "search_performed", 1), now=NOW)
    c.add(ev("r", "reservation_created", 1), now=NOW)
    c.add(ev("x", "reservation_cancelled", 1), now=NOW)
    out = c.counts(5, now=NOW)
    assert (out["searches"], out["reservations"], out["cancellations"]) == (4, 1, 1)
    assert out["conversion"] == 0.25
    assert out["window_minutes"] == 5


def test_ignora_eventos_invalidos_y_poda():
    c = LiveCounter(60)
    assert not c.add({"event_type": "search_performed", "event_ts": "mal"}, now=NOW)
    assert not c.add({"event_id": "z", "event_type": "otro", "event_ts": "2026-11-18T11:59:00Z"}, now=NOW)
    c.add(ev("a", "search_performed", 30), now=NOW)
    c.prune(now=NOW + dt.timedelta(minutes=45))
    assert c.counts(60, now=NOW)["searches"] == 0


def test_contrato_de_eventos():
    s = events.search_event("sess-1", "CUC", "BGA", "2031-03-10", 2)
    b = events.booking_event("reservation_created", "r1", "F1", "CUC-BGA", "2031-03-10", "ECONOMY", 100000)
    for e in (s, b):
        assert e["schema_version"] == 1
        dt.datetime.strptime(e["event_ts"], "%Y-%m-%dT%H:%M:%SZ")
        assert "passenger_name" not in e
        assert json.loads(events.encode(e)) == e  # un evento por registro, JSON valido
    assert events.partition_key(s) == "sess-1"
    assert events.partition_key(b) == "F1"
    assert isinstance(s["results_count"], int) and isinstance(b["price_cents"], int)


def test_consumidor_se_recupera_si_el_stream_se_recrea():
    """Tras borrar y crear el stream, la posicion guardada es invalida: debe leer desde hace 1 h."""
    import boto3
    from moto import mock_aws

    from app import live

    with mock_aws():
        k = boto3.client("kinesis", region_name="us-east-1")
        k.create_stream(StreamName="s-recreado", ShardCount=1)
        c = live.StreamConsumer(live.LiveCounter(60))
        c.stream = "s-recreado"
        sid = k.list_shards(StreamName="s-recreado")["Shards"][0]["ShardId"]
        positions = {sid: "49680341969505631912957003602989225834573903007819235330"}

        class Falso:  # moto no valida el origen del numero de secuencia: se simula el rechazo de AWS
            exceptions = k.exceptions

            def list_shards(self, **kw):
                return k.list_shards(**kw)

            def get_shard_iterator(self, **kw):
                if kw["ShardIteratorType"] == "AFTER_SEQUENCE_NUMBER":
                    raise k.exceptions.InvalidArgumentException(
                        {"Error": {"Code": "InvalidArgumentException", "Message": "did not come from this stream"}},
                        "GetShardIterator")
                assert kw["ShardIteratorType"] == "AT_TIMESTAMP"
                return k.get_shard_iterator(**kw)

        its = c._iterators(Falso(), positions)
        assert sid in its and sid not in positions
