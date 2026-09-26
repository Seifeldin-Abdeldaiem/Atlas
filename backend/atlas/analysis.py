"""Run a catalogue analysis and store its results. The worker calls run();
the API only queues it and reads the stored results.

The slow part (matching, and AI review in milestone 3) runs outside any
database transaction. Results are saved only if the dataset is still waiting
for this run: if someone changed the column mapping meanwhile, the run is
dropped rather than saving results for columns that no longer apply.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from . import datasets, db, jobs
from .catalogue.ai_review import ClaudeReviewer
from .catalogue.match import Analysis, Item, Reviewer, analyse
from .catalogue.normalize import normalise_table
from .catalogue.value import currencies, figures, headline, standard_name
from .config import get_settings
from .errors import AtlasError

log = logging.getLogger("atlas.analysis")
INSERT_BATCH = 1000


def start(conn: psycopg.Connection, org_id: UUID, dataset: dict) -> dict:
    """Queue an analysis. Called by the API inside the tenant transaction."""
    if dataset["kind"] != "catalogue":
        raise AtlasError("analysis_not_available", status_code=409)
    if dataset["status"] not in ("ready", "analysed"):
        raise AtlasError("not_ready", status_code=409)
    run_id = str(uuid4())
    state = {"state": "queued", "run_id": run_id, "progress": 0.0, "queued_at": dt.datetime.now(dt.UTC).isoformat()}
    conn.execute("UPDATE datasets SET status = 'analysing', analysis = %s, updated_at = now() WHERE id = %s", (Jsonb(state), dataset["id"]))
    jobs.enqueue(conn, org_id, jobs.ANALYSE_DATASET, {"dataset_id": str(dataset["id"]), "run_id": run_id})
    return state


def clear(conn: psycopg.Connection, dataset_id: UUID) -> None:
    """Forget previous results (the mapping or kind changed)."""
    conn.execute("DELETE FROM match_groups WHERE dataset_id = %s", (dataset_id,))
    conn.execute("DELETE FROM match_pairs WHERE dataset_id = %s", (dataset_id,))
    conn.execute("UPDATE datasets SET analysis = NULL WHERE id = %s", (dataset_id,))


def _progress(org_id: UUID, dataset_id: UUID, run_id: str, job_id: int | None, stage: str, progress: float) -> bool:
    """Record progress and keep the job's lock fresh. False if the run was cancelled."""
    with db.tenant(org_id) as conn:
        row = conn.execute(
            """UPDATE datasets SET analysis = analysis || %s, updated_at = now()
                WHERE id = %s AND status = 'analysing' AND analysis->>'run_id' = %s RETURNING id""",
            (Jsonb({"state": "running", "stage": stage, "progress": round(progress, 2)}), dataset_id, run_id),
        ).fetchone()
        if job_id is not None:
            conn.execute("UPDATE jobs SET locked_at = now() WHERE id = %s", (job_id,))
    return row is not None


def load_items(conn: psycopg.Connection, dataset: dict) -> tuple[list[Item], dict[int, dict]]:
    """Items to match, with values normalised by today's rules (stored values
    from older rule versions are refreshed)."""
    mapping = dataset["mapping"]
    table = datasets.load_table(conn, dataset)
    norms = normalise_table(table, mapping)
    datasets.write_norms(conn, dataset["id"], norms)
    originals = {r.row_number: r.values for r in table.rows}
    code_col, name_col = mapping.get("item_code"), mapping.get("item_name")
    items = [
        Item(row, norm, code=(originals[row].get(code_col) or None) if code_col else None, name=originals[row].get(name_col) or "")
        for row, norm in sorted(norms.items())
    ]
    return items, originals


class DbCache:
    """AI answers remembered per workspace (row-level security applies)."""

    def __init__(self, org_id: UUID) -> None:
        self.org_id = org_id

    def get_many(self, keys: list[str]) -> dict[str, tuple[str, str]]:
        if not keys:
            return {}
        with db.tenant(self.org_id) as conn:
            rows = conn.execute("SELECT key, verdict, reason FROM ai_cache WHERE key = ANY(%s)", (keys,)).fetchall()
        return {r["key"]: (r["verdict"], r["reason"]) for r in rows}

    def put_many(self, answers: dict[str, tuple[str, str]], model: str) -> None:
        with db.tenant(self.org_id) as conn, conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO ai_cache (org_id, key, verdict, reason, model) VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (org_id, key) DO UPDATE SET verdict = EXCLUDED.verdict, reason = EXCLUDED.reason, model = EXCLUDED.model, created_at = now()""",
                [(self.org_id, k, v, r, model) for k, (v, r) in answers.items()],
            )


def ai_review_enabled(conn: psycopg.Connection) -> bool:
    row = conn.execute("SELECT ai_review FROM workspace_settings").fetchone()
    return True if row is None else bool(row["ai_review"])


def make_reviewer(org_id: UUID, dataset_id: UUID, run_id: str, job_id: int | None) -> tuple[ClaudeReviewer | None, str]:
    """A reviewer for this run, or None and the reason AI review is off."""
    settings = get_settings()
    with db.tenant(org_id) as conn:
        if not ai_review_enabled(conn):
            return None, "off"
    if not settings.anthropic_api_key:
        return None, "not_configured"
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3, timeout=120.0)

    def on_batch(done: int, total: int) -> None:
        _progress(org_id, dataset_id, run_id, job_id, "ai_review", 0.3 + 0.6 * done / max(total, 1))

    reviewer = ClaudeReviewer(client, model=settings.ai_review_model, batch_size=settings.ai_batch_size, cache=DbCache(org_id), on_batch=on_batch)
    return reviewer, "on"


def run(
    org_id: UUID,
    dataset_id: UUID,
    run_id: str,
    job_id: int | None = None,
    reviewer: Reviewer | None = None,
    max_reviews: int | None = None,
    use_ai: bool = False,
) -> Analysis | None:
    """use_ai builds the configured Claude reviewer (the worker's default);
    tests pass their own reviewer instead."""
    started = time.monotonic()
    with db.tenant(org_id) as conn:
        dataset = conn.execute("SELECT * FROM datasets WHERE id = %s", (dataset_id,)).fetchone()
        if dataset is None or dataset["status"] != "analysing" or (dataset["analysis"] or {}).get("run_id") != run_id:
            log.info("analysis no longer wanted", extra={"dataset_id": str(dataset_id)})
            return None
        items, originals = load_items(conn, dataset)
        from .review import load_decisions

        decisions = load_decisions(conn, dataset_id)
        unit_col = dataset["mapping"].get("unit")
        units = {i.row: originals[i.row].get(unit_col) for i in items} if unit_col else {}
        context = {
            "units": units,
            "currency": workspace_currency(conn),
            "has_stock": bool(dataset["mapping"].get("stock")),
            "has_cost": bool(dataset["mapping"].get("unit_cost")),
        }

    if not _progress(org_id, dataset_id, run_id, job_id, "matching", 0.2):
        return None
    ai = "tests" if reviewer is not None else "off"
    if use_ai and reviewer is None:
        reviewer, ai = make_reviewer(org_id, dataset_id, run_id, job_id)
    limit = get_settings().ai_max_pairs_per_dataset if max_reviews is None else max_reviews
    result = analyse(
        items,
        reviewer=reviewer,
        max_reviews=limit if reviewer is not None else 0,
        force_same=decisions["force_same"],
        forbid=decisions["forbid"],
    )
    from .review import reapply

    reapply(result.groups, decisions)
    result.stats["ai"] = ai
    if isinstance(reviewer, ClaudeReviewer):
        result.stats["ai_usage"] = reviewer.stats.as_dict()

    with db.tenant(org_id) as conn:
        current = conn.execute("SELECT status, analysis FROM datasets WHERE id = %s FOR UPDATE", (dataset_id,)).fetchone()
        if current is None or current["status"] != "analysing" or (current["analysis"] or {}).get("run_id") != run_id:
            log.info("analysis dropped: dataset changed while it ran", extra={"dataset_id": str(dataset_id)})
            return None
        summary = save(conn, org_id, dataset_id, items, result, context)
        state = {
            "state": "done",
            "run_id": run_id,
            "progress": 1.0,
            "finished_at": dt.datetime.now(dt.UTC).isoformat(),
            "seconds": round(time.monotonic() - started, 1),
            "summary": summary,
        }
        conn.execute("UPDATE datasets SET status = 'analysed', analysis = %s, updated_at = now() WHERE id = %s", (Jsonb(state), dataset_id))
        datasets.audit(conn, org_id, None, "dataset.analysed", dataset_id, groups=summary["groups"], duplicate_lines=summary["duplicate_lines"])
    return result


def workspace_currency(conn: psycopg.Connection) -> str:
    row = conn.execute("SELECT currency FROM workspace_settings").fetchone()
    return row["currency"] if row else "GBP"


def summarise(items: list[Item], result: Analysis) -> dict:
    return {
        "items": len(items),
        "groups": len(result.groups),
        "duplicate_lines": sum(len(g.rows) - 1 for g in result.groups),
        "lookalikes": len(result.lookalikes),
        "needs_review": len(result.unsure),
        "ai_reviewed": result.stats.get("ai_reviewed", 0),
        "ai": result.stats.get("ai", "off"),
        "ai_usage": result.stats.get("ai_usage"),
        "pairs_compared": result.stats.get("pairs_compared", 0),
    }


def save(conn: psycopg.Connection, org_id: UUID, dataset_id: UUID, items: list[Item], result: Analysis, context: dict | None = None) -> dict:
    """Replace this dataset's stored results (and drop any export built from
    older results). Returns the headline summary."""
    context = context or {}
    conn.execute("DELETE FROM match_groups WHERE dataset_id = %s", (dataset_id,))
    conn.execute("DELETE FROM match_pairs WHERE dataset_id = %s", (dataset_id,))
    drop_export(conn, dataset_id)

    by_row = {i.row: i for i in items}
    default_currency = context.get("currency", "GBP")
    found = currencies(items, default_currency)
    money_ok = len(found) <= 1
    all_figures = []

    members: list[tuple] = []
    with conn.cursor() as cur:
        for n, group in enumerate(result.groups, start=1):
            group_id = uuid4()
            f = figures(group, by_row, context.get("units", {}), money_ok)
            all_figures.append(f)
            name = standard_name([by_row[r] for r in group.rows], by_row[group.master])
            cur.execute(
                """INSERT INTO match_groups (id, org_id, dataset_id, label, confidence, master_row, reasons, name_standard,
                                             stock_total, stock_on_duplicates, value_on_duplicates, cost_low, cost_high)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (group_id, org_id, dataset_id, f"G-{n:04d}", group.confidence, group.master, Jsonb(group.reasons), name,
                 f.stock_total, f.stock_on_duplicates, f.value_on_duplicates, f.cost_low, f.cost_high),
            )
            members += [(group_id, org_id, dataset_id, r, "master" if r == group.master else "duplicate") for r in group.rows]
        for start_at in range(0, len(members), INSERT_BATCH):
            cur.executemany(
                "INSERT INTO match_members (group_id, org_id, dataset_id, row_number, role) VALUES (%s, %s, %s, %s, %s)",
                members[start_at:start_at + INSERT_BATCH],
            )
        pairs = [("lookalike", p) for p in result.lookalikes] + [("review", p) for p in result.unsure]
        rows = [(org_id, dataset_id, kind, p.a, p.b, p.reason, p.detail, p.score, p.source) for kind, p in pairs]
        for start_at in range(0, len(rows), INSERT_BATCH):
            cur.executemany(
                """INSERT INTO match_pairs (org_id, dataset_id, kind, row_a, row_b, reason_code, detail, score, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                rows[start_at:start_at + INSERT_BATCH],
            )
    summary = summarise(items, result)
    summary["stock"] = headline(
        all_figures, next(iter(found), default_currency), context.get("has_stock", False), context.get("has_cost", False), found
    )
    return summary


def drop_export(conn: psycopg.Connection, dataset_id: UUID) -> None:
    """Forget an export built from results that no longer apply. The file
    itself is deleted by the storage call in export.discard()."""
    from .export import discard

    discard(conn, dataset_id)


def fail(org_id: UUID, dataset_id: UUID, run_id: str, code: str) -> None:
    """Give the dataset back as ready, with the reason, so it can be retried."""
    with db.tenant(org_id) as conn:
        conn.execute(
            """UPDATE datasets SET status = 'ready', analysis = %s, updated_at = now()
                WHERE id = %s AND status = 'analysing' AND analysis->>'run_id' = %s""",
            (Jsonb({"state": "failed", "run_id": run_id, "error_code": code}), dataset_id, run_id),
        )
