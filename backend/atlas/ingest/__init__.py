"""Read an uploaded task export or product catalogue into rows, its kind, a
suggested column mapping and a validation report. Pure function: bytes in,
data out."""

from __future__ import annotations

from dataclasses import dataclass, field

from .csv_reader import read_csv
from .detect import detect_format
from .json_reader import read_json
from .mapping import auto_map, detect_kind
from .types import DEFAULT_LIMITS, Limits, SheetInfo, Table
from .validate import build_report
from .xlsx_reader import read_xlsx

__all__ = ["IngestResult", "ingest"]


@dataclass
class IngestResult:
    format: str
    kind: str
    table: Table
    mapping: dict[str, str | None]
    report: dict
    sheets: list[SheetInfo] = field(default_factory=list)


def ingest(data: bytes, sheet: str | None = None, limits: Limits = DEFAULT_LIMITS) -> IngestResult:
    fmt = detect_format(data, limits)
    sheets: list[SheetInfo] = []
    if fmt == "xlsx":
        table, sheets = read_xlsx(data, sheet=sheet, limits=limits)
    elif fmt == "json":
        table = read_json(data, limits)
    else:
        table = read_csv(data, limits)
    kind = detect_kind(table.columns)
    mapping = auto_map(table.columns, kind)
    report = build_report(table, mapping, kind)
    return IngestResult(format=fmt, kind=kind, table=table, mapping=mapping, report=report, sheets=sheets)
