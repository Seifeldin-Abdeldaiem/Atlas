"""A small Postgres job queue. Jobs are rows in `jobs`; workers claim them with
FOR UPDATE SKIP LOCKED, so any number of workers can run safely. Enqueuing
happens in the same transaction as the change that needs it, so a job can
never exist without its data or vice versa."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import db

PARSE_DATASET = "parse_dataset"
ANALYSE_DATASET = "analyse_dataset"
BUILD_EXPORT = "build_export"


def enqueue(conn: psycopg.Connection, org_id: UUID, kind: str, payload: dict) -> int:
    row = conn.execute(
        "INSERT INTO jobs (org_id, kind, payload) VALUES (%s, %s, %s) RETURNING id",
        (org_id, kind, Jsonb(payload)),
    ).fetchone()
    return row["id"]


def claim(worker_id: str) -> dict | None:
    with db.system() as conn:
        return conn.execute("SELECT * FROM claim_job(%s)", (worker_id,)).fetchone()


def complete(job: dict) -> None:
    with db.tenant(job["org_id"]) as conn:
        conn.execute(
            "UPDATE jobs SET status = 'done', locked_by = NULL, updated_at = now() WHERE id = %s",
            (job["id"],),
        )


def retry_or_fail(job: dict, error_code: str) -> bool:
    """Schedule a retry with backoff. Returns False when attempts are used up."""
    final = job["attempts"] >= job["max_attempts"]
    delay_seconds = 15 * (4 ** (job["attempts"] - 1))  # 15 s, 60 s, 240 s
    with db.tenant(job["org_id"]) as conn:
        conn.execute(
            """UPDATE jobs
                  SET status = %s, last_error = %s, locked_by = NULL, locked_at = NULL,
                      run_after = now() + make_interval(secs => %s), updated_at = now()
                WHERE id = %s""",
            ("failed" if final else "queued", error_code, delay_seconds, job["id"]),
        )
    return not final


def requeue_stale(stale_seconds: int = 600) -> int:
    with db.system() as conn:
        return conn.execute("SELECT requeue_stale_jobs(%s) AS n", (stale_seconds,)).fetchone()["n"]
