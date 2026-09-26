import time

import pytest

from atlas.catalogue.normalize import normalise_row, normalise_table, normalise_text, parse_measures, parse_number, parse_pack, parse_part
from atlas.ingest import ingest
from atlas.ingest.mapping import auto_map, detect_kind, validate_mapping
from atlas.ingest.types import RawRow, Table
from atlas.ingest.validate import build_report

from .util import expect_error, xlsx_bytes

# A labelled bearings file has these headers; "group" and "true_product_id"
# are the answer key and must never be used for matching.
BEARING_HEADERS = ["group", "group_size", "item_code", "description", "tidied", "part_number", "brand", "true_product_id"]


# ---------- Kind detection and mapping ----------


def test_bearings_file_is_a_catalogue_and_maps_itself():
    assert detect_kind(BEARING_HEADERS) == "catalogue"
    m = auto_map(BEARING_HEADERS, "catalogue")
    assert m["item_name"] == "description"
    assert m["part_number"] == "part_number"
    assert m["brand"] == "brand"
    assert m["item_code"] == "item_code"
    assert "group" not in m.values()
    assert "true_product_id" not in m.values()


def test_task_exports_stay_tasks():
    assert detect_kind(["Issue key", "Summary", "Description", "Status", "Assignee", "Project name"]) == "tasks"
    assert detect_kind(["Title", "Team"]) == "tasks"
    assert detect_kind(["Owner", "Estimate"]) == "tasks"


def test_stock_system_export():
    headers = ["SKU", "Product Name", "Manufacturer", "MPN", "Qty On Hand", "Cost Price", "UOM", "Bin Location", "Supplier"]
    assert detect_kind(headers) == "catalogue"
    m = auto_map(headers, "catalogue")
    assert (m["item_code"], m["item_name"], m["brand"], m["part_number"]) == ("SKU", "Product Name", "Manufacturer", "MPN")
    assert (m["stock"], m["unit_cost"], m["unit"], m["location"], m["supplier"]) == ("Qty On Hand", "Cost Price", "UOM", "Bin Location", "Supplier")


def test_item_name_beats_description_and_description_becomes_details():
    m = auto_map(["Item Name", "Description"], "catalogue")
    assert (m["item_name"], m["details"]) == ("Item Name", "Description")


def test_name_fallback_on_suffix():
    assert auto_map(["Stock line description", "Qty"], "catalogue")["item_name"] == "Stock line description"


def test_catalogue_mapping_validation():
    clean = validate_mapping({"item_name": "description"}, BEARING_HEADERS, "catalogue")
    assert clean["item_name"] == "description" and clean["brand"] is None
    with expect_error("invalid_mapping"):
        validate_mapping({"title": "description"}, BEARING_HEADERS, "catalogue")
    with expect_error("invalid_kind"):
        validate_mapping({}, BEARING_HEADERS, "products")


# ---------- Normalisation ----------


def test_text():
    assert normalise_text("SKF 6205-2RS Brg") == "skf 6205 2rs bearing"
    assert normalise_text("Hex HD bolt, S/S") == "hex head bolt stainless steel"
    assert normalise_text("2.5 mm drill.") == "2.5 mm drill"


@pytest.mark.parametrize(
    ("name", "base", "variants"),
    [
        ("SKF 6205-2RS Deep Groove Ball Bearing", "6205", ["2rs"]),
        ("6205 2RS SKF bearing", "6205", ["2rs"]),
        ("Bearing 6205-2RS (SKF)", "6205", ["2rs"]),
        ("SKF 6205-ZZ Deep Groove Ball Bearing", "6205", ["zz"]),
        ("SKF 6205-2RS/C3", "6205", ["2rs", "c3"]),
        ("62052RSC3 brg", "6205", ["2rs", "c3"]),
        ("NSK 6205DDU", "6205", ["ddu"]),
        ("6205 N bearing", "6205", ["n"]),
        ("Loctite 243 threadlocker 50ml", "243", []),
        ("Hex bolt M8x25 A2 SS", None, []),
        ("Box of 1000 screws", None, []),
    ],
)
def test_part_from_name(name, base, variants):
    part = parse_part(None, name)
    assert part["part_base"] == base
    assert part["variants"] == variants


def test_variant_classes_separate_look_alikes_and_join_brand_equivalents():
    rubber = parse_part(None, "SKF 6205-2RSH")["variant_classes"]
    shields = parse_part(None, "SKF 6205-2Z")["variant_classes"]
    nsk = parse_part(None, "NSK 6205DDU")["variant_classes"]
    assert rubber == nsk == ["seal:rubber_both"]
    assert shields == ["seal:metal_both"]


def test_part_column_wins_and_variants_still_come_from_the_name():
    part = parse_part("6205", "SKF 6205-2RS Deep Groove Ball Bearing")
    assert (part["part_base"], part["part_source"], part["variants"]) == ("6205", "column", ["2rs"])
    assert parse_part("6205-2RS/C3", "bearing")["variants"] == ["2rs", "c3"]
    assert parse_part("6205 XYZ", "bearing")["part_extra"] == ["xyz"]


def test_measures():
    assert parse_measures("Hex bolt M8x25 A2") == {"thread": "m8", "length_mm": [25.0]}
    assert parse_measures("M8 X 25MM hex bolt") == {"thread": "m8", "length_mm": [25.0]}
    assert parse_measures("Bearing 25x52x15 mm") == {"sizes_mm": [25.0, 52.0, 15.0]}
    assert parse_measures("Loctite 243 50ml") == {"volume_ml": [50.0]}
    assert parse_measures("Grease 1 kg tub") == {"mass_g": [1000.0]}
    assert parse_measures("Hose 2.5 m") == {"length_mm": [2500.0]}
    assert parse_measures("Cable 10 metres") == {}


def test_pack_sizes():
    assert parse_pack("Box of 10") == 10
    assert parse_pack(None, "Nyloc nut M8 10/pk") == 10
    assert parse_pack("EA", "Washer 25 pcs") == 25
    assert parse_pack("Each", "Bearing 6205") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("£4.20", (4.2, "GBP", True)),
        ("1,250", (1250.0, None, True)),
        ("4,20", (4.2, None, True)),
        ("(12.50)", (-12.5, None, True)),
        ("12 GBP", (12.0, "GBP", True)),
        ("€3", (3.0, "EUR", True)),
        ("", (None, None, True)),
        ("n/a", (None, None, False)),
    ],
)
def test_numbers(value, expected):
    assert parse_number(value) == expected


def test_row_uses_brand_column_first():
    mapping = {"item_name": "n", "brand": "b", "stock": "s", "unit_cost": "c"}
    row = normalise_row({"n": "6205-2RS bearing", "b": "S.K.F.", "s": "12", "c": "£4.20"}, mapping)
    assert (row["brand"], row["brand_source"]) == ("skf", "column")
    assert (row["stock"], row["unit_cost"], row["currency"]) == (12.0, 4.2, "GBP")
    assert "problems" not in row
    guessed = normalise_row({"n": "SKF 6205-2RS", "b": "", "s": "lots", "c": ""}, mapping)
    assert (guessed["brand"], guessed["brand_source"]) == ("skf", "text")
    assert guessed["problems"] == ["stock_not_number"]


def test_normalise_table_skips_rows_without_a_name():
    table = Table(columns=["n"], rows=[RawRow(2, {"n": "SKF 6205"}), RawRow(3, {"n": "  "})])
    assert list(normalise_table(table, {"item_name": "n"})) == [2]
    assert normalise_table(table, {"item_name": None}) == {}


def test_hostile_cells_stay_fast():
    nasty = ("6" * 50 + "x" + "9" * 50 + " m8x" + "1" * 30) * 2000
    started = time.monotonic()
    normalise_row({"n": nasty, "s": nasty, "c": nasty, "u": nasty}, {"item_name": "n", "stock": "s", "unit_cost": "c", "unit": "u"})
    assert time.monotonic() - started < 0.5


# ---------- Catalogue validation ----------


def catalogue(rows: list[dict[str, str]]) -> Table:
    columns = list(rows[0])
    return Table(columns=columns, rows=[RawRow(i + 2, r) for i, r in enumerate(rows)])


def by_code(report: dict) -> dict:
    return {w["code"]: w for w in report["warnings"]}


def test_catalogue_needs_an_item_name():
    table = catalogue([{"Qty": "1", "Cost": "2"}])
    report = build_report(table, auto_map(table.columns, "catalogue"), "catalogue")
    assert [b["code"] for b in report["blocking"]] == ["no_name_column"]
    assert report["kind"] == "catalogue"


def test_catalogue_warnings():
    table = catalogue([
        {"SKU": "A1", "Name": "SKF 6205-2RS", "Part No": "6205", "Qty": "12", "Cost": "£4.20"},
        {"SKU": "A1", "Name": "", "Part No": "", "Qty": "lots", "Cost": "$4.10"},
        {"SKU": "A3", "Name": "Hex bolt M8x25", "Part No": "", "Qty": "400", "Cost": "0.18"},
    ])
    report = build_report(table, auto_map(table.columns, "catalogue"), "catalogue")
    w = by_code(report)
    assert report["blocking"] == []
    assert report["rows_ready"] == 2
    assert w["empty_names"]["rows"] == [3]
    assert w["duplicate_item_codes"]["rows"] == [2, 3]
    assert w["missing_part_numbers"]["rows"] == [4]
    assert w["not_a_number"]["rows"] == [3]
    assert "mixed_currencies" in w
    assert "no_brand_column" in w
    assert "no_stock_or_cost" not in w
    assert [x["severity"] for x in report["warnings"]] == sorted((x["severity"] for x in report["warnings"]), key=lambda s: s != "warning")


def test_catalogue_without_stock_or_cost_is_still_ready():
    table = catalogue([{"Product": "SKF 6205-2RS", "Brand": "SKF"}])
    report = build_report(table, auto_map(table.columns, "catalogue"), "catalogue")
    assert report["blocking"] == []
    assert "no_stock_or_cost" in by_code(report)


# ---------- End to end ----------


def test_ingest_detects_a_catalogue_workbook():
    data = xlsx_bytes({"Stock": [
        BEARING_HEADERS,
        ["G1", 3, "BRG-0142", "SKF 6205-2RS Deep Groove Ball Bearing", "skf 6205 2rs", "6205", "SKF", "P001"],
        ["G1", 3, "BRG-0388", "6205 2RS SKF bearing", "6205 2rs skf", "6205", "skf", "P001"],
        ["G2", 1, "BRG-0143", "SKF 6205-ZZ Deep Groove Ball Bearing", "skf 6205 zz", "6205", "SKF", "P002"],
    ]})
    result = ingest(data)
    assert result.kind == "catalogue"
    assert result.mapping["item_name"] == "description"
    assert result.report["blocking"] == []
    assert result.report["rows_ready"] == 3
    norms = normalise_table(result.table, result.mapping)
    assert [n["variants"] for n in norms.values()] == [["2rs"], ["2rs"], ["zz"]]
    assert {n["brand"] for n in norms.values()} == {"skf"}


def test_ingest_still_reads_task_exports_as_tasks():
    result = ingest(b"Summary,Status\nCreate login page,Open\n")
    assert result.kind == "tasks"
    assert result.report["kind"] == "tasks"
