"""Background worker.

    python -m atlas.worker

Runs parse jobs and, once an hour, deletes uploaded files past their
retention date. Run as many copies as you like; jobs are claimed safely.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
from uuid import UUID

from . import analysis, datasets, db, export, jobs, storage
from .config import get_settings
from .errors import IngestError, new_reference
from .logs import setup_logging
from .sandbox import run_ingest

log = logging.getLogger("atlas.worker")
_stopping = False


def _stop(*_: object) -> None:
    global _stopping
    _stopping = True


def handle_parse(job: dict) -> None:
    org_id: UUID = job["org_id"]
    dataset_id = UUID(job["payload"]["dataset_id"])
    sheet = job["payload"].get("sheet")
    settings = get_settings()

    with db.tenant(org_id) as conn:
        dataset = conn.execute(
            """SELECT d.id, f.object_key, f.deleted_at FROM datasets d
                 JOIN dataset_files f ON f.dataset_id = d.id AND f.kind = 'upload' WHERE d.id = %s""",
            (dataset_id,),
        ).fetchone()
    if dataset is None:
        log.info("dataset gone before parsing", extra={"dataset_id": str(dataset_id)})
        return
    if dataset["deleted_at"] is not None:
        with db.tenant(org_id) as conn:
            datasets.mark_failed(conn, dataset_id, "not_found")
        return

    data = storage.get(dataset["object_key"])
    started = time.monotonic()
    try:
        result = run_ingest(data, sheet, settings.limits, settings.parse_timeout_seconds, settings.parse_memory_mb)
    except IngestError as error:
        with db.tenant(org_id) as conn:
            datasets.mark_failed(conn, dataset_id, error.code)
            datasets.audit(conn, org_id, None, "dataset.parse_failed", dataset_id, code=error.code)
        log.info("parse refused", extra={"dataset_id": str(dataset_id), "code": error.code})
        return

    with db.tenant(org_id) as conn:
        datasets.save_parse_result(conn, org_id, dataset_id, result)
        datasets.audit(
            conn, org_id, None, "dataset.parsed", dataset_id,
            rows_read=result.report["rows_read"], rows_ready=result.report["rows_ready"], format=result.format, kind=result.kind,
        )
    log.info(
        "parsed",
        extra={"dataset_id": str(dataset_id), "kind": result.kind, "rows": result.report["rows_read"], "ms": int((time.monotonic() - started) * 1000)},
    )


def handle_analyse(job: dict) -> None:
    dataset_id = UUID(job["payload"]["dataset_id"])
    started = time.monotonic()
    result = analysis.run(job["org_id"], dataset_id, job["payload"]["run_id"], job_id=job["id"], use_ai=True)
    if result is not None:
        log.info(
            "analysed",
            extra={"dataset_id": str(dataset_id), "items": result.stats["items"], "groups": result.stats["groups"], "ms": int((time.monotonic() - started) * 1000)},
        )


def handle_export(job: dict) -> None:
    dataset_id = UUID(job["payload"]["dataset_id"])
    started = time.monotonic()
    if export.run(job["org_id"], dataset_id, job["payload"]["run_id"]):
        log.info("exported", extra={"dataset_id": str(dataset_id), "ms": int((time.monotonic() - started) * 1000)})


HANDLERS = {jobs.PARSE_DATASET: handle_parse, jobs.ANALYSE_DATASET: handle_analyse, jobs.BUILD_EXPORT: handle_export}


def run_job(job: dict) -> None:
    handler = HANDLERS.get(job["kind"])
    try:
        if handler is None:
            raise RuntimeError(f"unknown job kind {job['kind']}")
        handler(job)
        jobs.complete(job)
    except Exception:
        reference = new_reference()
        log.exception("job failed", extra={"job_id": job["id"], "kind": job["kind"], "reference": reference})
        will_retry = jobs.retry_or_fail(job, reference)
        if not will_retry and job["kind"] == jobs.PARSE_DATASET:
            with db.tenant(job["org_id"]) as conn:
                datasets.mark_failed(conn, UUID(job["payload"]["dataset_id"]), "internal_error")
        if not will_retry and job["kind"] == jobs.BUILD_EXPORT:
            export.fail(job["org_id"], UUID(job["payload"]["dataset_id"]), job["payload"]["run_id"])
        if not will_retry and job["kind"] == jobs.ANALYSE_DATASET:
            analysis.fail(job["org_id"], UUID(job["payload"]["dataset_id"]), job["payload"]["run_id"], "analysis_failed")


def expire_files() -> None:
    with db.system() as conn:
        due = conn.execute("SELECT * FROM files_due_for_expiry(%s)", (200,)).fetchall()
    for item in due:
        try:
            storage.delete(item["object_key"])
        except Exception:
            log.exception("could not delete expired file", extra={"file_id": str(item["id"])})
            continue
        with db.tenant(item["org_id"]) as conn:
            conn.execute("UPDATE dataset_files SET deleted_at = now() WHERE id = %s", (item["id"],))
            conn.execute(
                "INSERT INTO audit_events (org_id, action, target_type, target_id) VALUES (%s, 'file.expired', 'dataset_file', %s)",
                (item["org_id"], str(item["id"])),
            )
    if due:
        log.info("expired raw files", extra={"count": len(due)})


def main() -> None:
    setup_logging()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    log.info("worker started", extra={"worker": worker_id})
    next_housekeeping = 0.0

    while not _stopping:
        now = time.monotonic()
        if now >= next_housekeeping:
            try:
                jobs.requeue_stale()
                expire_files()
            except Exception:
                log.exception("housekeeping failed")
            next_housekeeping = now + 3600

        job = jobs.claim(worker_id)
        if job is None:
            time.sleep(1.0)
            continue
        run_job(job)

    db.close_pool()
    log.info("worker stopped")


if __name__ == "__main__":
    main()
