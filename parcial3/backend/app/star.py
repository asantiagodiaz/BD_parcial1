"""Job que reconstruye el modelo estrella (POST /admin/refresh-star, R8).

Corre en un hilo del backend y lanza en orden las consultas de star_sql.py en Athena:
DDL -> 3 dimensiones -> 2 hechos (CTAS a Parquet). No hay servidores ni clusters que
arrancar: con ~20 mil eventos tarda 1-2 minutos (limite: 15). Ver la comparacion con
Lambda+DuckDB y Glue en el documento (seccion 5, ETL).

Reglas de estado:
* Un solo refresco a la vez (candado).
* Si llega un POST mientras otro corre, se agenda otra corrida que empieza al terminar la
  actual: asi el que pide el refresco siempre recibe datos que incluyen lo que ya habia en
  la landing zone cuando lo pidio. `state` sigue en RUNNING hasta que esa corrida termine.
* Ademas hay un temporizador cada `star_refresh_every_minutes` (micro-lotes); se salta la
  corrida si la landing zone no cambio desde la ultima (no se paga Athena por nada).
"""

from __future__ import annotations

import datetime as dt
import logging
import pathlib
import threading
import time
import uuid

from app import star_sql
from app.config import settings

log = logging.getLogger("airline.star")
UTC = dt.timezone.utc
REF_DIR = pathlib.Path(__file__).resolve().parents[2] / "ref"
REF_FILES = {"routes": "routes_ref.csv", "route_category_history": "route_category_history.csv",
             "holidays": "holidays_ref.csv"}


class Athena:
    def __init__(self) -> None:
        import boto3

        self.athena = boto3.client("athena", region_name=settings.aws_region)
        self.s3 = boto3.client("s3", region_name=settings.aws_region)

    def run(self, sql: str, timeout: float = 600) -> dict:
        kw = dict(QueryString=sql, WorkGroup=settings.athena_workgroup)
        if settings.athena_output:
            kw["ResultConfiguration"] = {"OutputLocation": settings.athena_output}
        qid = self.athena.start_query_execution(**kw)["QueryExecutionId"]
        t0 = time.time()
        while True:
            qe = self.athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
            st = qe["Status"]["State"]
            if st in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            if time.time() - t0 > timeout:
                self.athena.stop_query_execution(QueryExecutionId=qid)
                raise TimeoutError(f"Athena {qid} sigue {st} tras {timeout}s")
            time.sleep(1)
        if st != "SUCCEEDED":
            raise RuntimeError(f"Athena {qid} {st}: {qe['Status'].get('StateChangeReason')}")
        return {"id": qid, "bytes": int(qe.get("Statistics", {}).get("DataScannedInBytes", 0)),
                "ms": int(qe.get("Statistics", {}).get("TotalExecutionTimeInMillis", 0))}

    def delete_prefix(self, prefix: str, keep: str | None = None) -> int:
        n = 0
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=settings.data_bucket, Prefix=prefix):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", []) if not (keep and o["Key"].startswith(keep))]
            for i in range(0, len(keys), 1000):
                self.s3.delete_objects(Bucket=settings.data_bucket, Delete={"Objects": keys[i:i + 1000]})
                n += len(keys[i:i + 1000])
        return n

    def landing_signature(self) -> tuple[int, str]:
        """(numero de objetos, ultima modificacion) de la landing zone: cambia si llego algo."""
        n, last = 0, ""
        for page in self.s3.get_paginator("list_objects_v2").paginate(
                Bucket=settings.data_bucket, Prefix=settings.raw_events_prefix):
            for o in page.get("Contents", []):
                n += 1
                last = max(last, o["LastModified"].isoformat())
        return n, last


class StarJob:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._rerun = False
        self.status: dict = {"state": "SUCCEEDED", "job_id": None, "detail": "aun no se ha ejecutado"}
        self._last_signature = None
        self._timer: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ API
    def request(self) -> str:
        with self._lock:
            job_id = uuid.uuid4().hex[:12]
            if self._running:
                self._rerun = True  # corre otra vez al terminar la actual
                self.status["queued_job_id"] = job_id
                return job_id
            self._running = True
            self.status = {"state": "RUNNING", "job_id": job_id, "started_at": _now()}
        threading.Thread(target=self._loop, args=(job_id,), name="star-refresh", daemon=True).start()
        return job_id

    def state(self) -> dict:
        with self._lock:
            s = dict(self.status)
            if self._running or self._rerun:
                s["state"] = "RUNNING"
            return s

    def start_timer(self) -> None:
        if settings.star_refresh_every_minutes <= 0 or not settings.data_bucket or self._timer:
            return
        self._timer = threading.Thread(target=self._tick, name="star-timer", daemon=True)
        self._timer.start()

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ internos
    def _tick(self) -> None:
        while not self._stop.wait(settings.star_refresh_every_minutes * 60):
            try:
                if self._running:
                    continue
                sig = Athena().landing_signature()
                if sig != self._last_signature and sig[0] > 0:
                    log.info("refresco periodico: la landing zone cambio %s", sig)
                    self.request()
            except Exception as ex:
                log.warning("temporizador de la estrella: %s", ex)

    def _loop(self, job_id: str) -> None:
        while True:
            self._run_once(job_id)
            with self._lock:
                if not self._rerun:
                    self._running = False
                    return
                self._rerun = False
                job_id = self.status.pop("queued_job_id", uuid.uuid4().hex[:12])
                self.status = {"state": "RUNNING", "job_id": job_id, "started_at": _now()}

    def _run_once(self, job_id: str) -> None:
        t0 = time.time()
        steps = []
        try:
            if not settings.data_bucket:
                raise RuntimeError("DATA_BUCKET no esta configurado")
            ath = Athena()
            sig = ath.landing_signature()
            db, bucket = settings.athena_database, settings.data_bucket
            # 1) Archivos de referencia (los versiona el repo) -> S3, uno por carpeta.
            for folder, fname in REF_FILES.items():
                ath.s3.upload_file(str(REF_DIR / fname), bucket, f"{settings.ref_prefix}{folder}/{fname}")
            # 2) DDL
            for name, sql in star_sql.ddl(db, bucket, settings.raw_events_prefix, settings.ref_prefix):
                r = ath.run(sql)
                steps.append({"step": f"ddl:{name}", "bytes": r["bytes"], "ms": r["ms"]})
            # 3) Estrella: DROP + CTAS a un prefijo nuevo; luego se borran los prefijos viejos.
            run_id = dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + job_id[:6]
            for table, select_fn, part in star_sql.TABLES:
                base = f"{settings.star_prefix}{table}/"
                loc = f"s3://{bucket}/{base}{run_id}/"
                ath.run(f"DROP TABLE IF EXISTS {db}.{table}")
                r = ath.run(star_sql.ctas(db, table, select_fn(db), loc, part))
                ath.delete_prefix(base, keep=f"{base}{run_id}/")
                steps.append({"step": table, "bytes": r["bytes"], "ms": r["ms"]})
            self._last_signature = sig
            result = {"state": "SUCCEEDED"}
        except Exception as ex:
            log.exception("refresco de la estrella fallo")
            result = {"state": "FAILED", "error": str(ex)[:500]}
        with self._lock:
            self.status.update(result, finished_at=_now(), seconds=round(time.time() - t0, 1), steps=steps,
                               bytes_scanned=sum(s["bytes"] for s in steps))


def _now() -> str:
    return dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


job = StarJob()
