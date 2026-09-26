"""Turn a stream of raw rows into a Table: find the header, name columns
uniquely, skip blank rows and flag malformed ones. Shared by CSV and XLSX."""

from __future__ import annotations

from collections.abc import Iterable

from ..errors import IngestError
from .types import Limits, RawRow, Table


def unique_column_names(raw: list[str]) -> list[str]:
    """Blank headers become "Column 3"; repeated headers become "Summary (2)"."""
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(raw, start=1):
        base = " ".join(value.split()) or f"Column {index}"
        count = seen.get(base.casefold(), 0) + 1
        seen[base.casefold()] = count
        names.append(base if count == 1 else f"{base} ({count})")
    return names


def build_table(rows: Iterable[tuple[int, list[str]]], limits: Limits, meta: dict[str, object] | None = None) -> Table:
    header: list[str] | None = None
    header_width = 0
    out: list[RawRow] = []
    malformed: list[tuple[int, str]] = []

    for row_number, cells in rows:
        # Trailing empty cells are common in exports and carry no meaning.
        while cells and not cells[-1].strip():
            cells.pop()
        if not cells or not any(c.strip() for c in cells):
            continue  # blank row

        if header is None:
            if len(cells) > limits.max_columns:
                raise IngestError("too_many_columns", limit_cols=limits.max_columns)
            header = unique_column_names(cells)
            header_width = len(header)
            continue

        if len(out) + len(malformed) >= limits.max_rows:
            raise IngestError("too_many_rows", limit_rows=limits.max_rows)

        if len(cells) > header_width:
            malformed.append((row_number, "extra_values"))
            continue
        if any(len(c) > limits.max_cell_chars for c in cells):
            malformed.append((row_number, "cell_too_long"))
            continue

        values = {name: (cells[i] if i < len(cells) else "") for i, name in enumerate(header)}
        out.append(RawRow(row_number=row_number, values=values))

    if header is None:
        raise IngestError("no_rows")
    if not out and not malformed:
        raise IngestError("no_rows")
    return Table(columns=header, rows=out, malformed=malformed, meta=meta or {})
