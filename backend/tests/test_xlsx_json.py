import datetime as dt
import json

from atlas.ingest.json_reader import read_json
from atlas.ingest.xlsx_reader import read_xlsx

from .util import expect_error, xlsx_bytes, zip_bytes

# ---------- XLSX ----------


def test_xlsx_basic_and_value_conversion():
    data = xlsx_bytes({"Backlog": [
        ["Issue key", "Summary", "Estimate", "Ratio", "Due", "Created", "Done"],
        ["ENG-1", "Create login page", 3, 0.25, dt.datetime(2026, 9, 1), dt.datetime(2026, 6, 14, 9, 30), True],
    ]})
    table, sheets = read_xlsx(data)
    row = table.rows[0].values
    assert row["Summary"] == "Create login page"
    assert row["Estimate"] == "3"
    assert row["Ratio"] == "0.25"
    assert row["Due"] == "2026-09-01"
    assert row["Created"] == "2026-06-14 09:30:00"
    assert row["Done"] == "TRUE"
    assert [s.name for s in sheets] == ["Backlog"]
    assert table.meta["sheet"] == "Backlog"


def test_xlsx_formulas_are_never_evaluated():
    data = xlsx_bytes({"Tasks": [["Title", "Calc"], ["A", "=1+1"]]})
    table, _ = read_xlsx(data)
    # Only cached values are read; a formula without one reads as empty.
    assert table.rows[0].values["Calc"] == ""


def test_xlsx_skips_empty_first_sheet_and_hides_hidden_sheets():
    data = xlsx_bytes({"Cover": [], "Secret": [["Title"], ["hidden"]], "Backlog": [["Title"], ["A"], ["B"]]}, hidden=("Secret",))
    table, sheets = read_xlsx(data)
    assert table.meta["sheet"] == "Backlog"
    assert [s.name for s in sheets] == ["Cover", "Backlog"]


def test_xlsx_explicit_sheet_choice():
    data = xlsx_bytes({"Backlog": [["Title"], ["A"]], "Archive": [["Title"], ["Old 1"], ["Old 2"]]})
    table, _ = read_xlsx(data, sheet="Archive")
    assert [r.values["Title"] for r in table.rows] == ["Old 1", "Old 2"]


def test_xlsx_unknown_sheet():
    data = xlsx_bytes({"Backlog": [["Title"], ["A"]]})
    with expect_error("sheet_not_found"):
        read_xlsx(data, sheet="Nope")


def test_xlsx_hidden_sheet_cannot_be_chosen():
    data = xlsx_bytes({"Backlog": [["Title"], ["A"]], "Secret": [["Title"], ["x"]]}, hidden=("Secret",))
    with expect_error("sheet_not_found"):
        read_xlsx(data, sheet="Secret")


def test_xlsx_all_sheets_empty():
    with expect_error("no_rows"):
        read_xlsx(xlsx_bytes({"One": [], "Two": [["Title"]]}))


def test_xlsx_damaged_parts_are_unreadable():
    data = zip_bytes({"xl/workbook.xml": b"<not really xml", "[Content_Types].xml": b"<Types/>"})
    with expect_error("unreadable_file"):
        read_xlsx(data)


# ---------- JSON ----------


def test_json_list_of_objects():
    table = read_json(json.dumps([{"id": 1, "title": "A"}, {"id": 2, "title": "B", "team": "Ops"}]).encode())
    assert table.columns == ["id", "title", "team"]
    assert table.rows[0].values["team"] == ""
    assert [r.row_number for r in table.rows] == [1, 2]
    assert table.meta["row_label"] == "item"


def test_json_wrapper_object_and_nested_fields():
    doc = {"total": 1, "issues": [{"key": "ENG-1", "fields": {"summary": "Login", "labels": ["auth", "web"], "status": {"name": "To Do"}}}]}
    table = read_json(json.dumps(doc).encode())
    row = table.rows[0].values
    assert row["key"] == "ENG-1"
    assert row["fields.summary"] == "Login"
    assert row["fields.labels"] == "auth; web"
    assert json.loads(row["fields.status"]) == {"name": "To Do"}


def test_json_non_objects_are_malformed():
    table = read_json(b'[{"title": "A"}, "stray", 7, {"title": "B"}]')
    assert [r.values["title"] for r in table.rows] == ["A", "B"]
    assert table.malformed == [(2, "not_an_object"), (3, "not_an_object")]


def test_json_invalid():
    with expect_error("invalid_json"):
        read_json(b'[{"title": "A",]')


def test_json_wrong_shape():
    with expect_error("json_shape"):
        read_json(b'{"a": [{"t": 1}], "b": [{"t": 2}]}')
    with expect_error("json_shape"):
        read_json(b'"just a string"')


def test_json_empty_list():
    with expect_error("no_rows"):
        read_json(b"[]")


def test_json_deep_nesting_does_not_crash():
    deep = "[" * 100_000 + "]" * 100_000
    with expect_error("invalid_json"):
        read_json(deep.encode())
