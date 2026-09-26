"""Dataset operations shared by the API and the worker. Every function takes
a connection already scoped to one organization by `db.tenant()`."""

from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .catalogue.normalize import normalise_table
from .config import get_settings
from .errors import MESSAGES, AtlasError
from .ingest import IngestResult
from .ingest.mapping import KINDS, REQUIRED_FIELD, auto_map, fields_for, validate_mapping
from .ingest.types import RawRow, Table
from .ingest.validate import build_report

INSERT_BATCH = 1000


def get_dataset(conn: psycopg.Connection, dataset_id: UUID) -> dict:
    row = conn.execute(
        """SELECT d.*, f.original_filename, f.size_bytes, f.object_key, f.expires_at, f.deleted_at AS file_deleted_at
             FROM datasets d
             LEFT JOIN dataset_files f ON f.dataset_id = d.id AND f.kind = 'upload'
            WHERE d.id = %s""",
        (dataset_id,),
    ).fetchone()
    if row is None:
        # Also what another company's dataset looks like: RLS hides it.
        raise AtlasError("not_found", status_code=404)
    return row


def to_api(row: dict) -> dict:
    error = None
    if row["status"] == "failed" and row["error_code"]:
        settings = get_settings()
        message = AtlasError(row["error_code"], limit_mb=settings.max_upload_mb, limit_rows=settings.max_rows, limit_cols=settings.limits.max_columns).message
        error = {"code": row["error_code"], "message": message}
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "kind": row["kind"],
        "status": row["status"],
        "error": error,
        "created_at": row["created_at"].isoformat(),
        "file": {
            "name": row.get("original_filename"),
            "size_bytes": row.get("size_bytes"),
            "format": row["file_format"],
            "sheet": row["sheet_name"],
            "sheets": row["sheets"],
            "raw_file_deleted_at": row["file_deleted_at"].isoformat() if row.get("file_deleted_at") else None,
            "raw_file_expires_at": row["expires_at"].isoformat() if row.get("expires_at") else None,
        },
        "columns": row["columns"],
        "mapping": row["mapping"],
        "report": row["report"],
        "analysis": _public_analysis(row.get("analysis")),
        "export": _public_export(row.get("export")),
    }


def _public_export(state: dict | None) -> dict | None:
    if not state:
        return None
    out = {k: v for k, v in state.items() if k in ("state", "file")}
    if state.get("error_code"):
        out["error"] = {"code": state["error_code"], "message": AtlasError(state["error_code"]).message}
    return out


def _public_analysis(state: dict | None) -> dict | None:
    if not state:
        return None
    out = {k: v for k, v in state.items() if k in ("state", "stage", "progress", "finished_at", "seconds", "summary")}
    if state.get("error_code"):
        out["error"] = {"code": state["error_code"], "message": AtlasError(state["error_code"]).message}
    return out


def field_catalog(kind: str = "tasks") -> list[dict]:
    required = REQUIRED_FIELD[kind]
    return [{"key": f.key, "label": f.label, "use": f.use, "required": f.key == required} for f in fields_for(kind)]


def _norms(table: Table, kind: str, mapping: dict[str, str | None]) -> dict[int, dict]:
    return normalise_table(table, mapping) if kind == "catalogue" else {}


def save_parse_result(conn: psycopg.Connection, org_id: UUID, dataset_id: UUID, result: IngestResult) -> None:
    table = result.table
    norms = _norms(table, result.kind, result.mapping)
    # A new read means new rows: earlier review decisions no longer apply.
    conn.execute("DELETE FROM review_decisions WHERE dataset_id = %s", (dataset_id,))
    conn.execute("DELETE FROM tasks WHERE dataset_id = %s", (dataset_id,))
    rows: list[tuple] = [
        (org_id, dataset_id, r.row_number, Jsonb(r.values), None, Jsonb(norms[r.row_number]) if r.row_number in norms else None)
        for r in table.rows
    ]
    rows += [(org_id, dataset_id, n, Jsonb({}), reason, None) for n, reason in table.malformed]
    rows.sort(key=lambda r: r[2])
    with conn.cursor() as cur:
        # COPY is not allowed on tables with row-level security; batched INSERTs are.
        for start in range(0, len(rows), INSERT_BATCH):
            cur.executemany(
                "INSERT INTO tasks (org_id, dataset_id, row_number, original, malformed_reason, norm) VALUES (%s, %s, %s, %s, %s, %s)",
                rows[start:start + INSERT_BATCH],
            )
    status = "blocked" if result.report["blocking"] else "ready"
    conn.execute(
        """UPDATE datasets
              SET status = %s, kind = %s, file_format = %s, sheet_name = %s, sheets = %s, columns = %s,
                  mapping = %s, report = %s, rows_read = %s, error_code = NULL, updated_at = now()
            WHERE id = %s""",
        (
            status,
            result.kind,
            result.format,
            table.meta.get("sheet"),
            Jsonb([{"name": s.name, "approx_rows": s.approx_rows} for s in result.sheets]),
            Jsonb(table.columns),
            Jsonb(result.mapping),
            Jsonb(result.report),
            result.report["rows_read"],
            dataset_id,
        ),
    )


def load_table(conn: psycopg.Connection, dataset: dict) -> Table:
    rows, malformed = [], []
    for r in conn.execute(
        "SELECT row_number, original, malformed_reason FROM tasks WHERE dataset_id = %s ORDER BY row_number",
        (dataset["id"],),
    ):
        if r["malformed_reason"]:
            malformed.append((r["row_number"], r["malformed_reason"]))
        else:
            rows.append(RawRow(r["row_number"], r["original"]))
    label = (dataset["report"] or {}).get("row_label", "row")
    return Table(columns=list(dataset["columns"]), rows=rows, malformed=malformed, meta={"row_label": label})


def write_norms(conn: psycopg.Connection, dataset_id: UUID, norms: dict[int, dict]) -> None:
    """Replace every row's normalised values in one pass per batch."""
    conn.execute("UPDATE tasks SET norm = NULL WHERE dataset_id = %s AND norm IS NOT NULL", (dataset_id,))
    items = [{"row_number": n, "norm": v} for n, v in norms.items()]
    for start in range(0, len(items), INSERT_BATCH):
        conn.execute(
            """UPDATE tasks t SET norm = v.norm
                 FROM jsonb_to_recordset(%s) AS v(row_number integer, norm jsonb)
                WHERE t.dataset_id = %s AND t.row_number = v.row_number""",
            (Jsonb(items[start:start + INSERT_BATCH]), dataset_id),
        )


EDITABLE = ("ready", "blocked", "analysing", "analysed")


def _save_mapping(conn: psycopg.Connection, dataset: dict, kind: str, mapping: dict[str, str | None]) -> None:
    """Save columns and re-check the file. Results of an earlier (or running)
    analysis no longer apply, so they are removed; a running analysis sees
    the status change and drops its results."""
    table = load_table(conn, dataset)
    report = build_report(table, mapping, kind)
    status = "blocked" if report["blocking"] else "ready"
    from .export import discard

    conn.execute("DELETE FROM match_groups WHERE dataset_id = %s", (dataset["id"],))
    conn.execute("DELETE FROM match_pairs WHERE dataset_id = %s", (dataset["id"],))
    discard(conn, dataset["id"])
    conn.execute(
        "UPDATE datasets SET kind = %s, mapping = %s, report = %s, status = %s, analysis = NULL, updated_at = now() WHERE id = %s",
        (kind, Jsonb(mapping), Jsonb(report), status, dataset["id"]),
    )
    write_norms(conn, dataset["id"], _norms(table, kind, mapping))


def apply_mapping(conn: psycopg.Connection, dataset: dict, mapping: dict) -> None:
    if dataset["status"] not in EDITABLE:
        raise AtlasError("not_ready", status_code=409)
    clean = validate_mapping(mapping, list(dataset["columns"]), dataset["kind"])
    _save_mapping(conn, dataset, dataset["kind"], clean)


def set_kind(conn: psycopg.Connection, dataset: dict, kind: str) -> None:
    """Switch between task export and product catalogue. The columns are
    matched again from scratch for the new kind."""
    if kind not in KINDS:
        raise AtlasError("invalid_kind", status_code=400)
    if dataset["status"] not in EDITABLE:
        raise AtlasError("not_ready", status_code=409)
    _save_mapping(conn, dataset, kind, auto_map(list(dataset["columns"]), kind))


def mark_failed(conn: psycopg.Connection, dataset_id: UUID, code: str) -> None:
    if code not in MESSAGES:
        code = "internal_error"
    conn.execute(
        "UPDATE datasets SET status = 'failed', error_code = %s, updated_at = now() WHERE id = %s",
        (code, dataset_id),
    )


def audit(conn: psycopg.Connection, org_id: UUID, actor: UUID | None, action: str, target_id: UUID | str, **meta: object) -> None:
    conn.execute(
        "INSERT INTO audit_events (org_id, actor_user_id, action, target_type, target_id, meta) VALUES (%s, %s, %s, 'dataset', %s, %s)",
        (org_id, actor, action, str(target_id), Jsonb(meta)),
    )
