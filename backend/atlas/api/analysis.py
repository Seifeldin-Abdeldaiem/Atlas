"""Analysis endpoints: start a run, follow its progress, read duplicate
groups, look-alikes and pairs to review. Every handler works inside
`db.tenant(identity.org_id)`, so row-level security scopes every query."""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from .. import analysis, datasets, db, export, review
from ..auth import Identity, current_identity
from ..config import get_settings
from ..errors import AtlasError

router = APIRouter(prefix="/v1", tags=["analysis"])


def _item(row: dict, mapping: dict) -> dict:
    """What people see for one catalogue line: their own values plus what
    Atlas read from them."""
    values, norm = row["original"] or {}, row["norm"] or {}

    def col(field: str) -> str | None:
        column = mapping.get(field)
        return values.get(column) if column else None

    part = (norm.get("part_base") or "").upper()
    if part and norm.get("variants"):
        part += "-" + "/".join(v.upper() for v in norm["variants"])
    return {
        "row_number": row["row_number"],
        "item_code": col("item_code"),
        "name": col("item_name"),
        "brand": (norm.get("brand") or "").upper() or None,
        "part_number": part or None,
        "stock": norm.get("stock"),
        "unit_cost": norm.get("unit_cost"),
        "currency": norm.get("currency"),
    }


def _items(conn, dataset: dict, rows: set[int]) -> dict[int, dict]:
    if not rows:
        return {}
    found = conn.execute(
        "SELECT row_number, original, norm FROM tasks WHERE dataset_id = %s AND row_number = ANY(%s)",
        (dataset["id"], sorted(rows)),
    ).fetchall()
    return {r["row_number"]: _item(r, dataset["mapping"]) for r in found}


def _analysed(conn, dataset_id: UUID) -> dict:
    dataset = datasets.get_dataset(conn, dataset_id)
    if dataset["status"] != "analysed":
        raise AtlasError("not_ready", status_code=409)
    return dataset


@router.post("/datasets/{dataset_id}/analysis", status_code=202)
def start_analysis(dataset_id: UUID, identity: Identity = Depends(current_identity)) -> dict:
    settings = get_settings()
    with db.tenant(identity.org_id) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        running = conn.execute("SELECT count(*) AS n FROM datasets WHERE status = 'analysing'").fetchone()["n"]
        if running >= settings.max_active_parses_per_org:
            raise AtlasError("too_many_active_uploads", status_code=429, limit=settings.max_active_parses_per_org)
        analysis.start(conn, identity.org_id, dataset)
        datasets.audit(conn, identity.org_id, identity.user_id, "dataset.analysis_started", dataset_id)
        row = datasets.get_dataset(conn, dataset_id)
    return {"id": str(dataset_id), "status": row["status"], "analysis": datasets.to_api(row)["analysis"]}


@router.get("/datasets/{dataset_id}/analysis")
def get_analysis(dataset_id: UUID, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        row = datasets.get_dataset(conn, dataset_id)
    return {"id": str(dataset_id), "status": row["status"], "analysis": datasets.to_api(row)["analysis"]}


@router.get("/datasets/{dataset_id}/groups")
def list_groups(
    dataset_id: UUID,
    identity: Identity = Depends(current_identity),
    confidence: str | None = Query(None, pattern="^(high|medium|reviewed)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    with db.tenant(identity.org_id) as conn:
        dataset = _analysed(conn, dataset_id)
        where = "dataset_id = %s AND (%s::text IS NULL OR confidence = %s)"
        params = (dataset_id, confidence, confidence)
        total = conn.execute("SELECT count(*) AS n FROM match_groups WHERE " + where, params).fetchone()["n"]
        groups = conn.execute("SELECT * FROM match_groups WHERE " + where + " ORDER BY label LIMIT %s OFFSET %s", (*params, limit, offset)).fetchall()
        members = conn.execute(
            "SELECT group_id, row_number, role FROM match_members WHERE group_id = ANY(%s) ORDER BY row_number",
            ([g["id"] for g in groups],),
        ).fetchall()
        items = _items(conn, dataset, {m["row_number"] for m in members})
    by_group: dict = {}
    for m in members:
        by_group.setdefault(m["group_id"], []).append({**items.get(m["row_number"], {"row_number": m["row_number"]}), "role": m["role"]})
    return {
        "total": total,
        "groups": [
            {
                "id": g["label"],
                "confidence": g["confidence"],
                "reasons": g["reasons"],
                "name_standard": g["name_standard"],
                "master_row": g["master_row"],
                "stock_total": _num(g["stock_total"]),
                "stock_on_duplicates": _num(g["stock_on_duplicates"]),
                "value_on_duplicates": _num(g["value_on_duplicates"]),
                "cost_low": _num(g["cost_low"]),
                "cost_high": _num(g["cost_high"]),
                "members": by_group.get(g["id"], []),
            }
            for g in groups
        ],
    }


@router.get("/datasets/{dataset_id}/pairs")
def list_pairs(
    dataset_id: UUID,
    identity: Identity = Depends(current_identity),
    kind: str = Query(..., pattern="^(lookalike|review)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    with db.tenant(identity.org_id) as conn:
        dataset = _analysed(conn, dataset_id)
        total = conn.execute("SELECT count(*) AS n FROM match_pairs WHERE dataset_id = %s AND kind = %s", (dataset_id, kind)).fetchone()["n"]
        pairs = conn.execute(
            "SELECT * FROM match_pairs WHERE dataset_id = %s AND kind = %s ORDER BY score DESC, row_a, row_b LIMIT %s OFFSET %s",
            (dataset_id, kind, limit, offset),
        ).fetchall()
        items = _items(conn, dataset, {r for p in pairs for r in (p["row_a"], p["row_b"])})
    return {
        "total": total,
        "pairs": [
            {
                "a": items.get(p["row_a"], {"row_number": p["row_a"]}),
                "b": items.get(p["row_b"], {"row_number": p["row_b"]}),
                "reason": p["reason_code"],
                "detail": p["detail"],
                "similarity": round(p["score"], 2),
                "source": p["source"],
            }
            for p in pairs
        ],
    }


def _num(value: object) -> float | None:
    return None if value is None else float(value)


class SettingsIn(BaseModel):
    ai_review: bool | None = None
    currency: str | None = Field(None, pattern="^[A-Z]{3}$")


@router.get("/settings")
def get_workspace_settings(identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        enabled = analysis.ai_review_enabled(conn)
        currency = analysis.workspace_currency(conn)
    return {
        "ai_review": enabled,
        "ai_available": bool(get_settings().anthropic_api_key),
        "ai_model": get_settings().ai_review_model,
        "currency": currency,
        "can_edit": identity.role == "admin",
    }


@router.put("/settings")
def put_workspace_settings(body: SettingsIn, identity: Identity = Depends(current_identity)) -> dict:
    """Workspace admins only. Turning AI review off keeps undecided pairs under
    "needs review" instead of sending them to the AI provider."""
    if identity.role != "admin":
        raise AtlasError("admin_only", status_code=403)
    with db.tenant(identity.org_id) as conn:
        current_ai, current_currency = analysis.ai_review_enabled(conn), analysis.workspace_currency(conn)
        ai = current_ai if body.ai_review is None else body.ai_review
        currency = body.currency or current_currency
        conn.execute(
            """INSERT INTO workspace_settings (org_id, ai_review, currency, updated_by) VALUES (%s, %s, %s, %s)
               ON CONFLICT (org_id) DO UPDATE SET ai_review = EXCLUDED.ai_review, currency = EXCLUDED.currency,
                                                  updated_by = EXCLUDED.updated_by, updated_at = now()""",
            (identity.org_id, ai, currency, identity.user_id),
        )
        conn.execute(
            "INSERT INTO audit_events (org_id, actor_user_id, action, target_type, target_id, meta) VALUES (%s, %s, 'settings.changed', 'workspace', %s, %s)",
            (identity.org_id, identity.user_id, str(identity.org_id), Jsonb({"ai_review": ai, "currency": currency})),
        )
    return get_workspace_settings(identity)


@router.post("/datasets/{dataset_id}/export", status_code=202)
def start_export(dataset_id: UUID, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        export.start(conn, identity.org_id, dataset)
        row = datasets.get_dataset(conn, dataset_id)
    return {"id": str(dataset_id), "export": datasets.to_api(row)["export"]}


@router.get("/datasets/{dataset_id}/export")
def get_export(dataset_id: UUID, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        row = datasets.get_dataset(conn, dataset_id)
    return {"id": str(dataset_id), "export": datasets.to_api(row)["export"]}


@router.get("/datasets/{dataset_id}/export/download")
def download_export(dataset_id: UUID, identity: Identity = Depends(current_identity)) -> Response:
    with db.tenant(identity.org_id) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        content, name, content_type = export.download(conn, dataset)
        datasets.audit(conn, identity.org_id, identity.user_id, "dataset.export_downloaded", dataset_id)
    fallback = "".join(ch if ch.isascii() and (ch.isalnum() or ch in " -_.") else "_" for ch in name)
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


class GroupReviewIn(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|set_master|remove_row)$")
    row_number: int | None = None


class PairReviewIn(BaseModel):
    row_a: int
    row_b: int
    verdict: str = Field(..., pattern="^(same|different)$")


@router.post("/datasets/{dataset_id}/groups/{label}/review")
def review_group(dataset_id: UUID, label: str, body: GroupReviewIn, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        summary = review.group_action(conn, identity.org_id, identity.user_id, dataset_id, label, body.action, body.row_number)
    return {"summary": summary}


@router.post("/datasets/{dataset_id}/pairs/review")
def review_pair(dataset_id: UUID, body: PairReviewIn, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        summary = review.pair_action(conn, identity.org_id, identity.user_id, dataset_id, body.row_a, body.row_b, body.verdict)
    return {"summary": summary}
