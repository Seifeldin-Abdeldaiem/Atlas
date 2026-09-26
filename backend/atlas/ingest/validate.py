"""Build the validation report shown on the Check data screen.

The report is plain JSON. It never alters rows: exclusions are recorded here
and applied when analysis starts, so changing the column mapping simply
produces a new report.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from ..catalogue.normalize import parse_number
from ..errors import MESSAGES
from .mapping import fields_by_key
from .types import RawRow, Table

MAX_LISTED_ROWS = 200
ANALYSIS_CHAR_CAP = 2000  # description chars sent to models (Architectural Assumption)

MALFORMED_REASONS = {
    "extra_values": "more values than the header has columns",
    "cell_too_long": "a value longer than 100,000 characters",
    "not_an_object": "not a task object",
}


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _plural(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def _fill_percent(filled: int, total: int) -> int:
    if total == 0:
        return 0
    if filled == total:
        return 100
    return min(99, math.floor(filled * 100 / total))


def build_report(table: Table, mapping: dict[str, str | None], kind: str = "tasks") -> dict:
    label = str(table.meta.get("row_label", "row"))
    labels = label + "s"
    rows = table.rows
    total = len(rows)
    by_key = fields_by_key(kind)

    blocking: list[dict] = []
    warnings: list[dict] = []

    # Columns: fill rate and a sample for each.
    column_field = {column: field for field, column in mapping.items() if column}
    columns_out = []
    for column in table.columns:
        filled = 0
        sample = ""
        for row in rows:
            value = row.values.get(column, "")
            if not _blank(value):
                filled += 1
                if not sample:
                    sample = " ".join(value.split())[:120]
        field = column_field.get(column)
        columns_out.append({
            "name": column,
            "field": field,
            "use": by_key[field].use if field else None,
            "fill_percent": _fill_percent(filled, total),
            "sample": sample,
        })

    # Malformed rows.
    if table.malformed:
        by_reason = Counter(reason for _, reason in table.malformed)
        reason_text = "; ".join(f"{count:,} with {MALFORMED_REASONS.get(r, r)}" for r, count in by_reason.most_common())
        n = len(table.malformed)
        warnings.append({
            "code": "malformed_rows",
            "severity": "warning",
            "title": f"{_plural(n, label, labels)} couldn't be read and will be left out",
            "detail": f"{reason_text.capitalize()}. They stay in your export, marked as not analyzed.",
            "count": n,
            "rows": [r for r, _ in table.malformed[:MAX_LISTED_ROWS]],
        })

    if kind == "catalogue":
        ready = _catalogue_checks(rows, mapping, label, labels, blocking, warnings)
    else:
        ready = _task_checks(rows, mapping, label, labels, blocking, warnings)

    order = {"warning": 0, "info": 1}
    warnings.sort(key=lambda w: order[w["severity"]])
    return {
        "kind": kind,
        "rows_read": total + len(table.malformed),
        "rows_ready": ready,
        "row_label": label,
        "blocking": blocking,
        "warnings": warnings,
        "columns": columns_out,
    }


def _rows_where(rows: list[RawRow], test) -> list[int]:
    return [row.row_number for row in rows if test(row)]


def _duplicate_values(rows: list[RawRow], column: str) -> tuple[int, list[int]]:
    positions: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        value = row.values.get(column, "")
        if not _blank(value):
            positions[value.strip()].append(row.row_number)
    repeated = {k: v for k, v in positions.items() if len(v) > 1}
    return len(repeated), sorted(r for v in repeated.values() for r in v)


def _info(code: str, title: str, detail: str) -> dict:
    return {"code": code, "severity": "info", "title": title, "detail": detail, "count": 0, "rows": []}


def _task_checks(rows: list[RawRow], mapping: dict[str, str | None], label: str, labels: str, blocking: list[dict], warnings: list[dict]) -> int:
    total = len(rows)
    title_col = mapping.get("title")
    desc_col = mapping.get("description")
    id_col = mapping.get("external_id")

    # Title.
    ready = 0
    if title_col is None:
        blocking.append({"code": "no_title_column", "message": MESSAGES["no_title_column"]})
    else:
        empty_title_rows = [row.row_number for row in rows if _blank(row.values.get(title_col))]
        ready = total - len(empty_title_rows)
        if empty_title_rows:
            n = len(empty_title_rows)
            shown = ", ".join(str(r) for r in empty_title_rows[:3])
            more = f" and {n - 3:,} more" if n > 3 else ""
            warnings.append({
                "code": "empty_titles",
                "severity": "warning",
                "title": f"{_plural(n, label, labels)} {'has' if n == 1 else 'have'} no title and will be left out",
                "detail": f"{labels.capitalize()} {shown}{more}. They stay in your export, marked as not analyzed.",
                "count": n,
                "rows": empty_title_rows[:MAX_LISTED_ROWS],
            })
        if ready == 0:
            blocking.append({"code": "no_usable_rows", "message": MESSAGES["no_usable_rows"]})

    # Duplicate IDs.
    if id_col is not None:
        positions: dict[str, list[int]] = defaultdict(list)
        for row in rows:
            value = row.values.get(id_col, "")
            if not _blank(value):
                positions[value.strip()].append(row.row_number)
        repeated = {k: v for k, v in positions.items() if len(v) > 1}
        if repeated:
            affected = sorted(r for v in repeated.values() for r in v)
            warnings.append({
                "code": "duplicate_ids",
                "severity": "warning",
                "title": f"{_plural(len(repeated), 'task ID appears', 'task IDs appear')} more than once",
                "detail": f"Every {label} is kept. Atlas tells them apart by {label} number, so findings always point to the right one.",
                "count": len(affected),
                "rows": affected[:MAX_LISTED_ROWS],
            })
    else:
        warnings.append({
            "code": "no_id_column",
            "severity": "info",
            "title": "No task ID column",
            "detail": f"Atlas will refer to tasks by {label} number. If your file has an ID column, choose it below.",
            "count": 0,
            "rows": [],
        })

    # Descriptions.
    if desc_col is None:
        warnings.append({
            "code": "no_description_column",
            "severity": "warning",
            "title": "No description column",
            "detail": "Tasks will be matched on title only, and findings are capped at medium confidence. If your file has descriptions, choose that column below.",
            "count": 0,
            "rows": [],
        })
    elif title_col is not None:
        titled = [row for row in rows if not _blank(row.values.get(title_col))]
        missing = [row.row_number for row in titled if _blank(row.values.get(desc_col))]
        if missing:
            n = len(missing)
            warnings.append({
                "code": "missing_descriptions",
                "severity": "warning" if n * 2 > len(titled) else "info",
                "title": f"{_plural(n, 'task has', 'tasks have')} no description",
                "detail": "They can still be matched on title, but findings about them are capped at medium confidence.",
                "count": n,
                "rows": missing[:MAX_LISTED_ROWS],
            })
        long_rows = [row.row_number for row in titled if len(row.values.get(desc_col) or "") > ANALYSIS_CHAR_CAP]
        if long_rows:
            n = len(long_rows)
            warnings.append({
                "code": "long_descriptions",
                "severity": "info",
                "title": f"{_plural(n, 'description is', 'descriptions are')} longer than {ANALYSIS_CHAR_CAP:,} characters",
                "detail": f"Atlas reads the first {ANALYSIS_CHAR_CAP:,} characters for analysis. The full text is kept and exported.",
                "count": n,
                "rows": long_rows[:MAX_LISTED_ROWS],
            })

    return ready


def _catalogue_checks(rows: list[RawRow], mapping: dict[str, str | None], label: str, labels: str, blocking: list[dict], warnings: list[dict]) -> int:
    name_col = mapping.get("item_name")
    code_col = mapping.get("item_code")
    part_col = mapping.get("part_number")
    stock_col = mapping.get("stock")
    cost_col = mapping.get("unit_cost")

    # Item name.
    ready = 0
    if name_col is None:
        blocking.append({"code": "no_name_column", "message": MESSAGES["no_name_column"]})
    else:
        empty = _rows_where(rows, lambda r: _blank(r.values.get(name_col)))
        ready = len(rows) - len(empty)
        if empty:
            n = len(empty)
            warnings.append({
                "code": "empty_names",
                "severity": "warning",
                "title": f"{_plural(n, label, labels)} {'has' if n == 1 else 'have'} no item name and will be left out",
                "detail": "They stay in your export, marked as not analyzed.",
                "count": n,
                "rows": empty[:MAX_LISTED_ROWS],
            })
        if ready == 0:
            blocking.append({"code": "no_usable_items", "message": MESSAGES["no_usable_items"]})

    # Item codes.
    if code_col is None:
        warnings.append(_info("no_item_code_column", "No item code column", f"Atlas will refer to items by {label} number. If your file has an SKU or item code column, choose it below."))
    else:
        groups, affected = _duplicate_values(rows, code_col)
        if groups:
            warnings.append({
                "code": "duplicate_item_codes",
                "severity": "warning",
                "title": f"{_plural(groups, 'item code appears', 'item codes appear')} more than once",
                "detail": f"Every {label} is kept. Atlas tells them apart by {label} number, so findings always point to the right one.",
                "count": len(affected),
                "rows": affected[:MAX_LISTED_ROWS],
            })

    # Part numbers and brands: optional, but they make matching much better.
    if part_col is None:
        warnings.append(_info("no_part_number_column", "No part number column", "Atlas will look for part numbers inside the item name. If your file has a part number column, choose it below."))
    elif name_col is not None:
        missing = _rows_where(rows, lambda r: not _blank(r.values.get(name_col)) and _blank(r.values.get(part_col)))
        if missing:
            n = len(missing)
            warnings.append({
                "code": "missing_part_numbers",
                "severity": "info",
                "title": f"{_plural(n, 'item has', 'items have')} no part number",
                "detail": "Atlas will look for a part number inside their item name instead.",
                "count": n,
                "rows": missing[:MAX_LISTED_ROWS],
            })
    if mapping.get("brand") is None:
        warnings.append(_info("no_brand_column", "No brand column", "Atlas will look for well-known brand names inside the item name. If your file has a brand or manufacturer column, choose it below."))

    # Stock and cost: needed only for the stock and value figures.
    if stock_col is None and cost_col is None:
        warnings.append(_info("no_stock_or_cost", "No stock or cost columns", "Duplicates are still found. Add stock and cost columns to see how much stock sits on duplicate lines."))
    elif stock_col is None:
        warnings.append(_info("no_stock_column", "No stock column", "Stock totals for duplicate groups need a stock or quantity column."))
    elif cost_col is None:
        warnings.append(_info("no_cost_column", "No cost column", "The value of stock on duplicate lines needs a unit cost column."))

    bad: list[int] = []
    currencies: set[str] = set()
    for row in rows:
        broken = False
        for column in (stock_col, cost_col):
            if column:
                _, currency, ok = parse_number(row.values.get(column))
                broken = broken or not ok
                if currency and column == cost_col:
                    currencies.add(currency)
        if broken:
            bad.append(row.row_number)
    if bad:
        n = len(bad)
        warnings.append({
            "code": "not_a_number",
            "severity": "warning",
            "title": f"{_plural(n, label, labels)} {'has' if n == 1 else 'have'} a stock or cost value that isn't a number",
            "detail": "Those values count as blank in stock and value totals. The items are still checked for duplicates.",
            "count": n,
            "rows": bad[:MAX_LISTED_ROWS],
        })
    if len(currencies) > 1:
        warnings.append({
            "code": "mixed_currencies",
            "severity": "warning",
            "title": "Costs are in more than one currency",
            "detail": f"We found {', '.join(sorted(currencies))}. Money totals are left out until all costs use one currency.",
            "count": 0,
            "rows": [],
        })
    return ready
