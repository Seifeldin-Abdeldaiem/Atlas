"""Read JSON exports: a list of task objects, or an object holding exactly one
such list (for example {"issues": [...]}). Nested objects are flattened one
level ("fields.summary"); anything deeper is kept as compact JSON text."""

from __future__ import annotations

import json

from ..errors import IngestError
from .csv_reader import decode_text
from .types import DEFAULT_LIMITS, Limits, RawRow, Table


def _scalar(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value):
        return "; ".join(_scalar(v) for v in value if v is not None)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def flatten(item: dict) -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in item.items():
        key = str(key)
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat[f"{key}.{sub_key}"] = _scalar(sub_value)
        else:
            flat[key] = _scalar(value)
    return flat


def _find_task_list(document: object) -> list:
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        lists = [v for v in document.values() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:50])]
        if len(lists) == 1:
            return lists[0]
    raise IngestError("json_shape")


def read_json(data: bytes, limits: Limits = DEFAULT_LIMITS) -> Table:
    text, encoding = decode_text(data)
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        raise IngestError("invalid_json") from None

    items = _find_task_list(document)
    if not items:
        raise IngestError("no_rows")
    if len(items) > limits.max_rows:
        raise IngestError("too_many_rows", limit_rows=limits.max_rows)

    columns: list[str] = []
    known: set[str] = set()
    rows: list[RawRow] = []
    malformed: list[tuple[int, str]] = []

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            malformed.append((index, "not_an_object"))
            continue
        flat = flatten(item)
        if any(len(v) > limits.max_cell_chars for v in flat.values()):
            malformed.append((index, "cell_too_long"))
            continue
        for key in flat:
            if key not in known:
                known.add(key)
                columns.append(key)
                if len(columns) > limits.max_columns:
                    raise IngestError("too_many_columns", limit_cols=limits.max_columns)
        rows.append(RawRow(row_number=index, values=flat))

    if not rows and not malformed:
        raise IngestError("no_rows")
    # Every row carries every column so the preview and export line up.
    for row in rows:
        for column in columns:
            row.values.setdefault(column, "")
    return Table(columns=columns, rows=rows, malformed=malformed, meta={"encoding": encoding, "row_label": "item"})
