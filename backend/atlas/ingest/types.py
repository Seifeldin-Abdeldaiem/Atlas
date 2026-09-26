"""Data types shared by the ingest readers.

The ingest package is pure Python with no database, network or settings
dependency, so it can be tested in isolation and run in a sandboxed process.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 25 * 1024 * 1024
    max_rows: int = 20_000
    max_columns: int = 200
    max_cell_chars: int = 100_000
    # XLSX is a zip archive; these stop "zip bombs" before parsing.
    max_uncompressed_bytes: int = 250 * 1024 * 1024
    max_compression_ratio: int = 200


DEFAULT_LIMITS = Limits()


@dataclass
class RawRow:
    """One task row exactly as read. `row_number` matches what a user sees in a
    spreadsheet: the header is row 1, the first task is row 2."""

    row_number: int
    values: dict[str, str]


@dataclass
class Table:
    columns: list[str]
    rows: list[RawRow]
    # Rows that could not be read, with a reason code. They are excluded from
    # analysis but reported to the user by row number.
    malformed: list[tuple[int, str]] = field(default_factory=list)
    meta: dict[str, object] = field(default_factory=dict)


@dataclass
class SheetInfo:
    name: str
    approx_rows: int
