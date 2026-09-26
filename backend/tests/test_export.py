"""Milestone 4: stock and value figures, standard names and the cleaned file."""

from __future__ import annotations

import csv
import io
import json

import openpyxl
import pytest

from atlas.catalogue.match import Group, Item, analyse
from atlas.catalogue.normalize import normalise_row, normalise_table
from atlas.catalogue.value import currencies, figures, headline, standard_name
from atlas.export import ADDED, added_columns, csv_safe, write_file
from atlas.ingest import ingest

MAP = {"item_name": "n", "stock": "s", "unit_cost": "c", "unit": "u"}


def item(row: int, name: str, stock: str = "", cost: str = "", unit: str = "") -> Item:
    return Item(row, normalise_row({"n": name, "s": stock, "c": cost, "u": unit}, MAP))


# ---------- Figures ----------


def test_group_figures_by_hand():
    items = {2: item(2, "SKF 6205-2RS", "12", "£4.20"), 3: item(3, "6205 2RS SKF", "18", "£4.35"), 4: item(4, "Bearing 6205-2RS", "12", "£3.95")}
    f = figures(Group([2, 3, 4], master=3, confidence="high", reasons=[]), items, {}, money_ok=True)
    assert (f.stock_total, f.stock_on_duplicates) == (42, 24)
    assert f.value_on_duplicates == pytest.approx(12 * 4.20 + 12 * 3.95)  # 97.80
    assert (f.cost_low, f.cost_high) == (3.95, 4.35)


def test_pack_sizes_and_units():
    items = {2: item(2, "Nut M8 box of 100", "3", "12.00", "box"), 3: item(3, "Nut M8", "250", "0.15", "each")}
    f = figures(Group([2, 3], master=3, confidence="medium", reasons=[]), items, {2: "box", 3: "each"}, money_ok=True)
    assert (f.stock_total, f.stock_on_duplicates, f.value_on_duplicates) == (550, 300, 36.0)
    assert (f.cost_low, f.cost_high) == (0.12, 0.15)  # per single nut

    unknown = {2: item(2, "Cable 3 core", "2", "40", "drum"), 3: item(3, "Cable 3 core", "150", "0.3", "metre")}
    g = figures(Group([2, 3], master=3, confidence="medium", reasons=[]), unknown, {2: "drum", 3: "metre"}, money_ok=True)
    assert g.stock_total is None and g.units_differ  # a drum and a metre can't be added up
    assert g.value_on_duplicates == 80.0  # value still works: line stock x line cost


def test_no_money_when_currencies_mix_or_columns_missing():
    items = {2: item(2, "A 6205", "4", "$3"), 3: item(3, "A 6205", "5", "£3")}
    assert currencies(items.values(), "GBP") == {"USD", "GBP"}
    f = figures(Group([2, 3], master=3, confidence="high", reasons=[]), items, {}, money_ok=False)
    assert f.value_on_duplicates is None and f.cost_low is None and f.stock_total == 9

    bare = {2: item(2, "A 6205"), 3: item(3, "A 6205")}
    f = figures(Group([2, 3], master=2, confidence="high", reasons=[]), bare, {}, money_ok=True)
    assert (f.stock_total, f.value_on_duplicates) == (None, None)


def test_negative_stock_counts_as_zero():
    items = {2: item(2, "A 6205", "-4", "1"), 3: item(3, "A 6205", "5", "1")}
    f = figures(Group([2, 3], master=3, confidence="high", reasons=[]), items, {}, money_ok=True)
    assert (f.stock_total, f.value_on_duplicates) == (5, 0)


def test_headline():
    items = {2: item(2, "SKF 6205-2RS", "12", "4.20"), 3: item(3, "6205 2RS SKF", "18", "4.35")}
    one = figures(Group([2, 3], master=3, confidence="high", reasons=[]), items, {}, True)
    h = headline([one], "GBP", True, True, {"GBP"})
    assert h == {
        "has_stock": True, "has_cost": True, "currency": "GBP", "mixed_currencies": [],
        "units_on_duplicates": 12, "value_on_duplicates": 50.4, "groups_with_cost_gap": 0, "groups_units_differ": 0,
    }
    assert headline([one], "GBP", True, True, {"GBP", "USD"})["currency"] is None


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["SKF 6205-2RS Deep Groove Ball Bearing", "رولمان بلي ٦٢٠٥ ٢ار اس اس كي اف"], "Bearing, Deep Groove Ball, SKF 6205-2RS"),
        (["رولمان بلي ٦٢٠٥ ٢ار اس اس كي اف", "SKF 6205-2RS Deep Groove Ball Bearing"], "Bearing, Deep Groove Ball, SKF 6205-2RS"),
        (["Hex bolt M8x25 A2 SS"], "Bolt, Hex, M8 x 25 mm, A2 Stainless"),
        (["MCB 16A single pole"], "Breaker, MCB, 16 A, 1P"),
        (["LED flood light 100W IP65"], "Light, LED Flood IP65, 100 W"),
    ],
)
def test_standard_names(names, expected):
    items = [item(i + 2, n) for i, n in enumerate(names)]
    assert standard_name(items, items[0]) == expected


# ---------- The cleaned file ----------

ROWS = [
    {"row_number": 2, "original": {"Code": "BRG-1", "Name": "SKF 6205-2RS", "Note": "=HYPERLINK(\"http://evil\")"}, "norm": {"brand": "skf", "part_base": "6205", "variants": ["2rs"]}, "malformed": None},
    {"row_number": 3, "original": {"Code": "BRG-2", "Name": "رولمان بلي ٦٢٠٥", "Note": "-5"}, "norm": {"brand": "skf", "part_base": "6205", "variants": ["2rs"]}, "malformed": None},
    {"row_number": 4, "original": {"Code": "BRG-3", "Name": "SKF 6205-ZZ", "Note": "0012"}, "norm": {"brand": "skf", "part_base": "6205", "variants": ["zz"]}, "malformed": None},
    {"row_number": 5, "original": {"Code": "BRG-4", "Name": "SKF 6205", "Note": "@SUM(A1)"}, "norm": {"brand": "skf", "part_base": "6205"}, "malformed": None},
    {"row_number": 6, "original": {}, "norm": None, "malformed": "extra_values"},
]
GROUPS = [{
    "label": "G-0001", "confidence": "high", "master_row": 2, "reasons": ["Same brand (SKF), same part number and variant (6205-2RS)."],
    "name_standard": "Bearing, SKF 6205-2RS", "stock_total": 30.0, "stock_on_duplicates": 18.0, "value_on_duplicates": 75.6,
    "members": [{"row_number": 2, "role": "master"}, {"row_number": 3, "role": "duplicate"}],
}]
SUMMARY = {"items": 4, "groups": 1, "duplicate_lines": 1, "lookalikes": 1, "needs_review": 1, "stock": {"currency": "GBP", "units_on_duplicates": 18.0, "value_on_duplicates": 75.6}}


def added():
    return added_columns(ROWS, {"item_code": "Code", "item_name": "Name"}, GROUPS, lookalikes=[(2, 4)], review_rows={4, 5})


def test_added_columns():
    a = added()
    assert (a[2]["atlas_role"], a[3]["atlas_role"], a[4]["atlas_role"], a[5]["atlas_role"], a[6]["atlas_role"]) == ("master", "duplicate", "needs_review", "needs_review", "not_analysed")
    assert a[3]["atlas_master_code"] == "BRG-1" and a[3]["atlas_group"] == "G-0001"
    assert a[2]["atlas_lookalike_of"] == "BRG-3" and a[4]["atlas_lookalike_of"] == "BRG-1"
    assert (a[2]["atlas_group_stock"], a[2]["atlas_group_value"]) == (30.0, 75.6)
    assert a[3]["atlas_group_stock"] == ""  # totals only on the master line
    assert (a[4]["atlas_part_number"], a[4]["atlas_variant"]) == ("6205", "ZZ")


def test_csv_safe():
    assert csv_safe("=1+1") == "'=1+1" and csv_safe("@x") == "'@x" and csv_safe("+44 20") == "'+44 20" and csv_safe("\tx") == "'\tx"
    assert csv_safe("-5") == "-5" and csv_safe("4.20") == "4.20" and csv_safe("SKF") == "SKF"


def test_csv_file():
    content = write_file("csv", ["Code", "Name", "Note", "atlas_role"], ROWS, added(), SUMMARY, GROUPS)
    assert content.startswith(b"\xef\xbb\xbf")  # Excel reads UTF-8 correctly
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    header = rows[0]
    assert header[:4] == ["Code", "Name", "Note", "atlas_role"] and "atlas_role (atlas)" in header
    assert len(rows) == 1 + len(ROWS)
    assert rows[1][2] == "'=HYPERLINK(\"http://evil\")" and rows[2][2] == "-5" and rows[4][2] == "'@SUM(A1)"
    assert rows[2][1] == "رولمان بلي ٦٢٠٥"
    assert rows[1][3] == ""  # the customer's own atlas_role column is left as it was
    assert rows[1][header.index("atlas_role (atlas)")] == "master"


def test_xlsx_file():
    content = write_file("xlsx", ["Code", "Name", "Note"], ROWS, added(), SUMMARY, GROUPS)
    book = openpyxl.load_workbook(io.BytesIO(content))
    items = book["Items"]
    header = [c.value for c in items[1]]
    assert header == ["Code", "Name", "Note", *ADDED]
    risky = items.cell(row=2, column=3)
    assert risky.value.startswith("=") and risky.data_type == "s"  # text, never a formula
    assert items.cell(row=3, column=3).value == -5 and items.cell(row=4, column=3).value == "0012"
    assert items.cell(row=3, column=2).value == "رولمان بلي ٦٢٠٥"
    summary = {r[0].value: r[1].value for r in book["Atlas summary"].iter_rows() if r and r[0].value}
    assert summary["Duplicate groups"] == 1 and summary["Stock value on duplicate lines (GBP)"] == 75.6


def test_json_file():
    records = json.loads(write_file("json", ["Code", "Name", "Note"], ROWS, added(), SUMMARY, GROUPS))
    assert len(records) == len(ROWS)
    assert records[0]["Name"] == "SKF 6205-2RS" and records[0]["atlas_role"] == "master"
    assert records[4]["atlas_role"] == "not_analysed"


def test_totals_checked_by_hand_on_a_whole_file():
    """A small stock file worked out on paper, run through the whole pipeline."""
    data = (
        "Stock Code,Item Description,Manufacturer,Qty On Hand,Cost Price,UOM\n"
        "B-1,SKF 6205-2RS Deep Groove Ball Bearing,SKF,12,£4.20,each\n"
        "B-2,6205 2RS SKF bearing,SKF,18,£4.35,each\n"
        "B-3,Bearing 6205-2RS (SKF),SKF,12,£3.95,each\n"
        "B-4,SKF 6205-ZZ Deep Groove Ball Bearing,SKF,10,£3.80,each\n"
        "N-1,Hex nut M8 A2 box of 100,,3,£12.00,box\n"
        "N-2,M8 HEX NUT STAINLESS A2,,250,£0.15,each\n"
    ).encode()
    result = ingest(data)
    assert result.kind == "catalogue"
    norms = normalise_table(result.table, result.mapping)
    rows = {r.row_number: r for r in result.table.rows}
    items = {n: Item(n, norms[n], code=rows[n].values["Stock Code"]) for n in norms}
    analysis = analyse(list(items.values()))
    groups = {tuple(g.rows): g for g in analysis.groups}
    assert set(groups) == {(2, 3, 4), (6, 7)}  # the ZZ bearing (row 5) stays apart
    units = {n: rows[n].values["UOM"] for n in norms}
    bearings = figures(groups[(2, 3, 4)], items, units, True)
    nuts = figures(groups[(6, 7)], items, units, True)
    # Bearings: master is B-2 (most stock). 12 + 18 + 12 = 42; duplicates 12 + 12 = 24;
    # value 12 x 4.20 + 12 x 3.95 = 97.80.
    assert groups[(2, 3, 4)].master == 3
    assert (bearings.stock_total, bearings.stock_on_duplicates, bearings.value_on_duplicates) == (42, 24, 97.8)
    # Nuts: 3 boxes of 100 + 250 singles = 550. The master is N-1 (300 nuts beat 250),
    # so the duplicate line holds 250 nuts worth 250 x 0.15 = 37.50.
    assert groups[(6, 7)].master == 6
    assert (nuts.stock_total, nuts.stock_on_duplicates, nuts.value_on_duplicates) == (550, 250, 37.5)
