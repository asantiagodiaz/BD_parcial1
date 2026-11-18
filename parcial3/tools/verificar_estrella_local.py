"""Verifica en local (DuckDB) el SQL de la estrella contra el oraculo del harness.

Usa EXACTAMENTE el texto de backend/app/star_sql.py: sqlglot lo traduce de Trino (Athena) a
DuckDB. Carga como eventos crudos el replay sucio del harness (duplicados, tardios y
desordenados) mas algunos eventos "ajenos" (sin prefijo rp-) y comprueba R5 (dim_date), R6,
R7 (Q1-Q8), R8 y R9 con las mismas consultas que el harness.

    cd parcial3/backend
    .venv/bin/python ../tools/verificar_estrella_local.py --harness ../../../parcial3-harness-estudiantes
"""

import argparse
import json
import os
import sys

import duckdb
import pandas as pd
import sqlglot

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
from app import star_sql  # noqa: E402

DB = "s"


def to_duck(sql: str) -> str:
    return sqlglot.transpile(sql, read="trino", write="duckdb")[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True)
    ap.add_argument("--seed", type=int, default=963)
    a = ap.parse_args()
    sys.path.insert(0, os.path.abspath(a.harness))
    from airline_data.events import StarTruth, calendar_dates, holiday_calendar

    truth = StarTruth(a.seed)
    ref = os.path.join(HERE, "..", "ref")
    con = duckdb.connect()
    con.execute(f"CREATE SCHEMA {DB}")
    # CSV de referencia como texto (igual que la tabla externa de Athena)
    for t, f in [("ref_routes", "routes_ref.csv"), ("ref_route_category_history", "route_category_history.csv"),
                 ("ref_holidays", "holidays_ref.csv")]:
        df = pd.read_csv(os.path.join(ref, f), dtype=str)
        if t == "ref_holidays":
            df.columns = ["holiday_date", "holiday_name"]
        con.register("tmp", df)
        con.execute(f"CREATE TABLE {DB}.{t} AS SELECT * FROM tmp")
        con.unregister("tmp")

    # Eventos crudos: el replay sucio + eventos ajenos de "hoy" (lo que generan R1-R3)
    raw = list(truth.arrivals)
    raw += [{"event_id": "x-1", "event_type": "search_performed", "event_ts": "2026-11-18T10:00:00Z",
             "schema_version": 1, "session_id": "s", "origin": "zzz", "destination": "yyy",
             "travel_date": "2031-03-10", "results_count": 2},
            {"event_id": "x-2", "event_type": "reservation_created", "event_ts": "2026-11-18T10:00:01Z",
             "schema_version": 1, "reservation_id": "r", "flight_id": "f", "route": "CUC-BGA",
             "flight_date": "2031-03-10", "fare_class": "ECONOMY", "price_cents": 100000}]
    cols = ["event_id", "event_type", "event_ts", "schema_version", "session_id", "origin", "destination",
            "travel_date", "results_count", "reservation_id", "flight_id", "route", "flight_date",
            "fare_class", "price_cents"]
    rdf = pd.DataFrame([{c: e.get(c) for c in cols} for e in raw])
    rdf["results_count"] = rdf["results_count"].astype("Int32")
    rdf["price_cents"] = rdf["price_cents"].astype("Int64")
    con.register("tmp", rdf)
    con.execute(f"CREATE TABLE {DB}.raw_events AS SELECT * FROM tmp")
    con.unregister("tmp")
    print(f"raw_events: {len(rdf)} registros")

    for name, fn, _ in star_sql.TABLES:
        sql = to_duck(fn(DB))
        con.execute(f"CREATE TABLE {DB}.{name} AS {sql}")
        print(f"{name}: {con.execute(f'SELECT COUNT(*) FROM {DB}.{name}').fetchone()[0]} filas")
    con.execute(f"SET schema = '{DB}'")

    def q(sql):
        return con.execute(to_duck(sql)).fetchall()

    fails = []

    def check(label, ok, detail=""):
        print(("OK   " if ok else "FAIL ") + label + (f"  {detail}" if not ok else ""))
        if not ok:
            fails.append(label)

    LIKE = "LIKE 'rp-%'"
    b = lambda x: str(x).lower() == "true"

    # R5 dim_date
    exp = calendar_dates().set_index("date_key")
    rows = q("SELECT date_key, CAST(full_date AS VARCHAR), weekday, weekday_name, quarter, is_holiday, "
             "is_long_weekend, holiday_name FROM dim_date")
    bad = 0
    for r in rows:
        e = exp.loc[int(r[0])]
        if (r[1][:10], int(r[2]), r[3], int(r[4]), b(r[5]), b(r[6])) != (
                e.full_date, int(e.weekday), e.weekday_name, int(e.quarter), bool(e.is_holiday), bool(e.is_long_weekend)):
            bad += 1
        if bool(e.is_holiday) and not r[7]:
            bad += 1
    check("R5 dim_date", len(rows) == len(exp) and bad == 0, f"{len(rows)} filas, {bad} errores")

    # R6
    for t, k in [("dim_date", "date_key"), ("dim_route", "route_key"), ("dim_fare_class", "fare_class_key")]:
        n, d = q(f"SELECT COUNT(*), COUNT(DISTINCT {k}) FROM {t}")[0]
        check(f"R6 {t}.{k} unica", n == d and n > 0)
    for f, k, d in [("fact_search", "route_key", "dim_route"), ("fact_search", "date_key", "dim_date"),
                    ("fact_booking_event", "route_key", "dim_route"), ("fact_booking_event", "date_key", "dim_date"),
                    ("fact_booking_event", "fare_class_key", "dim_fare_class")]:
        n = q(f"SELECT COUNT(*) FROM {f} x LEFT JOIN {d} y ON x.{k} = y.{k} WHERE y.{k} IS NULL")[0][0]
        check(f"R6 sin huerfanos {f}.{k}", n == 0, n)
    for f in ("fact_search", "fact_booking_event"):
        n, d = q(f"SELECT COUNT(*), COUNT(DISTINCT event_id) FROM {f}")[0]
        check(f"R6 grano {f}", n == d)

    # R7
    got = {(int(r[0]), int(r[1]), r[2]): int(r[3]) for r in q(
        f"SELECT d.year, d.month, c.fare_class, SUM(f.revenue_cents) FROM fact_booking_event f JOIN dim_date d "
        f"ON f.date_key = d.date_key JOIN dim_fare_class c ON f.fare_class_key = c.fare_class_key "
        f"WHERE f.event_id {LIKE} GROUP BY 1, 2, 3")}
    check("R7 Q1", got == truth.q1())
    got = {r[0]: (int(r[1]), int(r[2])) for r in q(
        f"SELECT r.route, SUM(f.cancellations), SUM(f.bookings) FROM fact_booking_event f JOIN dim_route r "
        f"ON f.route_key = r.route_key WHERE f.event_id {LIKE} GROUP BY 1")}
    check("R7 Q2", got == truth.q2())
    got = {r[0]: int(r[1]) for r in q(f"SELECT d.weekday_name, SUM(f.bookings) FROM fact_booking_event f JOIN dim_date d "
                                      f"ON f.date_key = d.date_key WHERE f.event_id {LIKE} GROUP BY 1")}
    check("R7 Q3", got == truth.q3())
    got = [(r[0], int(r[1])) for r in q(
        f"SELECT r.route, SUM(f.revenue_cents) AS rev FROM fact_booking_event f JOIN dim_route r ON f.route_key = r.route_key "
        f"WHERE f.event_id {LIKE} GROUP BY 1 ORDER BY rev DESC, r.route LIMIT 10")]
    check("R7 Q4", got == truth.q4(10))
    s = {b(r[0]): int(r[1]) for r in q(f"SELECT d.is_holiday, COUNT(*) FROM fact_search f JOIN dim_date d "
                                       f"ON f.date_key = d.date_key WHERE f.event_id {LIKE} GROUP BY 1")}
    bk = {b(r[0]): int(r[1]) for r in q(f"SELECT d.is_holiday, SUM(f.bookings) FROM fact_booking_event f JOIN dim_date d "
                                        f"ON f.date_key = d.date_key WHERE f.event_id {LIKE} GROUP BY 1")}
    check("R7 Q7", {k: (s.get(k, 0), bk.get(k, 0)) for k in (False, True)} == truth.q7())
    got = {b(r[0]): int(r[1]) for r in q(f"SELECT d.is_long_weekend, SUM(f.bookings) FROM fact_booking_event f JOIN dim_date d "
                                         f"ON f.date_key = d.date_key WHERE f.event_id {LIKE} GROUP BY 1")}
    check("R7 Q8", {k: got.get(k, 0) for k in (False, True)} == truth.q8())
    s = {r[0]: int(r[1]) for r in q(f"SELECT r.route, COUNT(*) FROM fact_search f JOIN dim_route r ON f.route_key = r.route_key "
                                    f"WHERE f.event_id {LIKE} GROUP BY 1")}
    bk = {r[0]: int(r[1]) for r in q(f"SELECT r.route, SUM(f.bookings) FROM fact_booking_event f JOIN dim_route r "
                                     f"ON f.route_key = r.route_key WHERE f.event_id {LIKE} GROUP BY 1")}
    e6 = truth.q6()
    check("R7 Q6", {r: (s.get(r, 0), bk.get(r, 0)) for r in e6} == e6)

    # R8
    for f, n_exp in (("fact_search", truth.n_search_unique), ("fact_booking_event", truth.n_booking_unique)):
        n, d = q(f"SELECT COUNT(*), COUNT(DISTINCT event_id) FROM {f} WHERE event_id {LIKE}")[0]
        check(f"R8 dedup {f}", n == n_exp == d, f"{n}/{d} vs {n_exp}")
    exp_d = {int(k.replace("-", "")): v for k, v in truth.per_date_counts()["search"].items()}
    got = {int(r[0]): int(r[1]) for r in q(f"SELECT date_key, COUNT(*) FROM fact_search WHERE event_id {LIKE} GROUP BY 1")}
    check("R8 fecha por event_ts", got == exp_d)

    # R9
    rows = q("SELECT route, route_category, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR), is_current "
             "FROM dim_route ORDER BY route, valid_from")
    by = {}
    for r in rows:
        by.setdefault(r[0], []).append((r[1], r[2][:10], r[3][:10], b(r[4])))
    ok = True
    for route, h in truth.hist.groupby("route"):
        h = h.sort_values("effective_date")
        v = by.get(route, [])
        for i in range(len(h)):
            last = i == len(h) - 1
            want = (h.iloc[i]["route_category"], h.iloc[i]["effective_date"],
                    "9999-12-31" if last else h.iloc[i + 1]["effective_date"], last)
            if len(v) != len(h) or v[i] != want:
                ok = False
    check("R9 SCD2", ok)
    got = {(r[0], int(r[1]), int(r[2])): int(r[3]) for r in q(
        f"SELECT r.route_category, d.year, d.month, SUM(f.revenue_cents) FROM fact_booking_event f JOIN dim_route r "
        f"ON f.route_key = r.route_key JOIN dim_date d ON f.date_key = d.date_key WHERE f.event_id {LIKE} GROUP BY 1, 2, 3")}
    check("R9 Q5", got == truth.q5())

    # R10 (aqui solo el conteo; el ratio de bytes se mide en Athena)
    n_jan = int((truth.searches.ym == "2025-01").sum())
    check("R10 conteo 2025-01", q("SELECT COUNT(*) FROM fact_search WHERE month = '2025-01'")[0][0] == n_jan)

    print("\n" + ("TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
