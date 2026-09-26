"""Dataset endpoints: upload, status and preview, kind (task export or product
catalogue), column mapping, sheet choice, deletion. Every handler works inside `db.tenant(identity.org_id)`."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import unicodedata
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel, Field

from .. import datasets, db, jobs, storage
from ..auth import Identity, current_identity
from ..config import get_settings
from ..errors import AtlasError
from ..ingest.detect import detect_format

router = APIRouter(prefix="/v1", tags=["datasets"])
log = logging.getLogger("atlas.api")
READ_CHUNK = 1024 * 1024


class MappingIn(BaseModel):
    mapping: dict[str, str | None] = Field(..., description="field key -> column name, or null")


class KindIn(BaseModel):
    kind: str = Field(..., description="tasks or catalogue")


class SheetIn(BaseModel):
    sheet: str = Field(..., min_length=1, max_length=255)


def clean_filename(name: str | None) -> str:
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in unicodedata.normalize("NFC", name) if unicodedata.category(ch)[0] != "C")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:200] or "Untitled file"


def dataset_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return stem.strip() or "Untitled dataset"


@router.get("/me")
def me(identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        org = conn.execute("SELECT id, name FROM organizations WHERE id = %s", (identity.org_id,)).fetchone()
        user = conn.execute("SELECT id, name, email FROM users WHERE id = %s", (identity.user_id,)).fetchone()
    return {
        "organization": {"id": str(org["id"]), "name": org["name"]},
        "user": {"id": str(user["id"]), "name": user["name"], "email": user["email"], "role": identity.role},
    }


@router.get("/datasets")
def list_datasets(identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        rows = conn.execute(
            """SELECT d.id, d.name, d.kind, d.status, d.created_at, d.rows_read, d.report->>'rows_ready' AS rows_ready,
                      f.original_filename
                 FROM datasets d LEFT JOIN dataset_files f ON f.dataset_id = d.id AND f.kind = 'upload'
                ORDER BY d.created_at DESC LIMIT 200"""
        ).fetchall()
    return {
        "datasets": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "kind": r["kind"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
                "file_name": r["original_filename"],
                "rows_read": r["rows_read"],
                "rows_ready": int(r["rows_ready"]) if r["rows_ready"] is not None else None,
            }
            for r in rows
        ]
    }


@router.post("/datasets", status_code=201)
def upload(file: UploadFile = File(...), identity: Identity = Depends(current_identity)) -> dict:
    settings = get_settings()
    filename = clean_filename(file.filename)

    # Read at most one byte past the limit; never trust Content-Length alone.
    chunks, size = [], 0
    while chunk := file.file.read(READ_CHUNK):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise AtlasError("file_too_large", status_code=413, limit_mb=settings.max_upload_mb)
        chunks.append(chunk)
    data = b"".join(chunks)

    # Refuse unsupported files immediately, before anything is stored.
    detect_format(data, settings.limits)

    with db.tenant(identity.org_id) as conn:
        active = conn.execute("SELECT count(*) AS n FROM datasets WHERE status = 'parsing'").fetchone()["n"]
    if active >= settings.max_active_parses_per_org:
        raise AtlasError("too_many_active_uploads", status_code=429, limit=settings.max_active_parses_per_org)

    dataset_id = uuid4()
    key = storage.new_key(identity.org_id, dataset_id)
    storage.put(key, data)
    try:
        with db.tenant(identity.org_id) as conn:
            conn.execute(
                "INSERT INTO datasets (id, org_id, name, status, created_by) VALUES (%s, %s, %s, 'parsing', %s)",
                (dataset_id, identity.org_id, dataset_name(filename), identity.user_id),
            )
            conn.execute(
                """INSERT INTO dataset_files (org_id, dataset_id, object_key, original_filename, size_bytes, sha256, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    identity.org_id, dataset_id, key, filename, size, hashlib.sha256(data).hexdigest(),
                    dt.datetime.now(dt.UTC) + dt.timedelta(days=settings.raw_file_retention_days),
                ),
            )
            jobs.enqueue(conn, identity.org_id, jobs.PARSE_DATASET, {"dataset_id": str(dataset_id)})
            datasets.audit(conn, identity.org_id, identity.user_id, "dataset.uploaded", dataset_id, size_bytes=size)
    except Exception:
        try:
            storage.delete(key)
        except Exception:
            log.exception("orphaned upload could not be removed", extra={"dataset_id": str(dataset_id)})
        raise
    return {"id": str(dataset_id), "status": "parsing"}


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: UUID, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        row = datasets.get_dataset(conn, dataset_id)
    body = datasets.to_api(row)
    body["fields"] = datasets.field_catalog(row["kind"])
    return body


@router.get("/datasets/{dataset_id}/rows")
def get_rows(
    dataset_id: UUID,
    identity: Identity = Depends(current_identity),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    only: str | None = Query(None, description="a warning code: show only the rows it lists"),
) -> dict:
    with db.tenant(identity.org_id) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        if dataset["status"] == "parsing":
            raise AtlasError("not_ready", status_code=409)
        if only:
            warning = next((w for w in (dataset["report"] or {}).get("warnings", []) if w["code"] == only), None)
            numbers = (warning or {}).get("rows", [])[offset:offset + limit]
            rows = conn.execute(
                "SELECT row_number, original, malformed_reason FROM tasks WHERE dataset_id = %s AND row_number = ANY(%s) ORDER BY row_number",
                (dataset_id, numbers),
            ).fetchall()
            total = len((warning or {}).get("rows", []))
        else:
            rows = conn.execute(
                "SELECT row_number, original, malformed_reason FROM tasks WHERE dataset_id = %s ORDER BY row_number LIMIT %s OFFSET %s",
                (dataset_id, limit, offset),
            ).fetchall()
            total = conn.execute("SELECT count(*) AS n FROM tasks WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"]
    return {
        "columns": dataset["columns"],
        "total": total,
        "rows": [{"row_number": r["row_number"], "values": r["original"], "malformed": r["malformed_reason"]} for r in rows],
    }


@router.put("/datasets/{dataset_id}/mapping")
def put_mapping(dataset_id: UUID, body: MappingIn, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        datasets.apply_mapping(conn, dataset, body.mapping)
        datasets.audit(conn, identity.org_id, identity.user_id, "dataset.mapping_changed", dataset_id)
        row = datasets.get_dataset(conn, dataset_id)
    result = datasets.to_api(row)
    result["fields"] = datasets.field_catalog(row["kind"])
    return result


@router.put("/datasets/{dataset_id}/kind")
def put_kind(dataset_id: UUID, body: KindIn, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        datasets.set_kind(conn, dataset, body.kind)
        datasets.audit(conn, identity.org_id, identity.user_id, "dataset.kind_changed", dataset_id, kind=body.kind)
        row = datasets.get_dataset(conn, dataset_id)
    result = datasets.to_api(row)
    result["fields"] = datasets.field_catalog(row["kind"])
    return result


@router.post("/datasets/{dataset_id}/sheet", status_code=202)
def choose_sheet(dataset_id: UUID, body: SheetIn, identity: Identity = Depends(current_identity)) -> dict:
    with db.tenant(identity.org_id) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        if dataset["file_format"] != "xlsx":
            raise AtlasError("sheet_not_found", status_code=400)
        if body.sheet not in {s["name"] for s in dataset["sheets"]}:
            raise AtlasError("sheet_not_found", status_code=400)
        if dataset["file_deleted_at"] is not None:
            raise AtlasError("not_found", status_code=410)
        conn.execute("UPDATE datasets SET status = 'parsing', updated_at = now() WHERE id = %s", (dataset_id,))
        jobs.enqueue(conn, identity.org_id, jobs.PARSE_DATASET, {"dataset_id": str(dataset_id), "sheet": body.sheet})
    return {"id": str(dataset_id), "status": "parsing"}


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: UUID, identity: Identity = Depends(current_identity)) -> Response:
    with db.tenant(identity.org_id) as conn:
        datasets.get_dataset(conn, dataset_id)  # not_found for anything this company can't see
        # The upload and any export file.
        for f in conn.execute("SELECT object_key FROM dataset_files WHERE dataset_id = %s AND deleted_at IS NULL", (dataset_id,)).fetchall():
            storage.delete(f["object_key"])
        conn.execute("DELETE FROM jobs WHERE status = 'queued' AND payload->>'dataset_id' = %s", (str(dataset_id),))
        conn.execute("DELETE FROM datasets WHERE id = %s", (dataset_id,))  # cascades to files and tasks
        datasets.audit(conn, identity.org_id, identity.user_id, "dataset.deleted", dataset_id)
    return Response(status_code=204)
