from atlas.ingest.csv_reader import read_csv
from atlas.ingest.types import Limits

from .util import expect_error


def titles(table, column="Title"):
    return [row.values[column] for row in table.rows]


def test_comma_semicolon_tab_and_pipe_delimiters():
    for delimiter in [",", ";", "\t", "|"]:
        data = f"Title{delimiter}Team\nCreate login page{delimiter}Identity\nFix invoices{delimiter}Billing\n".encode()
        table = read_csv(data)
        assert table.meta["delimiter"] == delimiter
        assert titles(table) == ["Create login page", "Fix invoices"]
        assert table.rows[0].values["Team"] == "Identity"


def test_utf8_bom():
    table = read_csv("\ufeffTitle,Team\nRésumé export,Ops\n".encode("utf-8"))
    assert table.columns == ["Title", "Team"]
    assert titles(table) == ["Résumé export"]


def test_utf16_with_bom():
    table = read_csv("Title\tTeam\nCafé menu\tOps\n".encode("utf-16"))
    assert titles(table) == ["Café menu"]


def test_windows_1252():
    data = "Title,Description\nCustomer’s login page,Café – résumé\n".encode("cp1252")
    table = read_csv(data)
    assert titles(table) == ["Customer’s login page"]
    assert table.rows[0].values["Description"] == "Café – résumé"


def test_quoted_commas_and_multiline_cells_keep_row_numbers():
    data = (
        'Title,Description\n'
        '"Login, customers","Line one\nLine two"\n'
        'Second task,Plain\n'
    ).encode()
    table = read_csv(data)
    assert titles(table) == ["Login, customers", "Second task"]
    assert table.rows[0].values["Description"] == "Line one\nLine two"
    # Row numbers count records, as a spreadsheet does: header = 1.
    assert [r.row_number for r in table.rows] == [2, 3]


def test_blank_rows_are_skipped_but_row_numbers_stay_true():
    table = read_csv(b"Title\n\nFirst\n,\nSecond\n")
    assert titles(table) == ["First", "Second"]
    assert [r.row_number for r in table.rows] == [3, 5]


def test_short_rows_are_padded_and_extra_values_are_malformed():
    table = read_csv(b"Title,Team,Status\nA,Ops\nB,Ops,Done,unexpected\nC,Ops,Done\n")
    assert titles(table) == ["A", "C"]
    assert table.rows[0].values["Status"] == ""
    assert table.malformed == [(3, "extra_values")]


def test_trailing_empty_columns_are_not_malformed():
    table = read_csv(b"Title,Team\nA,Ops,,,\n")
    assert table.malformed == []


def test_duplicate_and_blank_headers_get_unique_names():
    table = read_csv(b"Summary,,Summary,Team\na,b,c,d\n")
    assert table.columns == ["Summary", "Column 2", "Summary (2)", "Team"]


def test_values_are_kept_exactly_as_written():
    table = read_csv(b'Title,Description\n"  Create  login ","=HYPERLINK(""x"")"\n')
    assert table.rows[0].values["Title"] == "  Create  login "
    assert table.rows[0].values["Description"] == '=HYPERLINK("x")'


def test_header_only_file_has_no_rows():
    with expect_error("no_rows"):
        read_csv(b"Title,Description\n")


def test_too_many_rows():
    data = "Title\n" + "".join(f"Task {i}\n" for i in range(11))
    with expect_error("too_many_rows"):
        read_csv(data.encode(), Limits(max_rows=10))


def test_too_many_columns():
    header = ",".join(f"c{i}" for i in range(6))
    with expect_error("too_many_columns"):
        read_csv(f"{header}\n1,2,3,4,5,6\n".encode(), Limits(max_columns=5))


def test_oversized_cell_is_malformed_not_fatal():
    data = b"Title,Description\nOK,short\nBig," + b"x" * 5000 + b"\n"
    table = read_csv(data, Limits(max_cell_chars=1000))
    assert titles(table) == ["OK"]
    assert table.malformed == [(3, "cell_too_long")]


def test_nul_bytes_after_header_are_removed():
    table = read_csv(b"Title\nA" + b"\x00" + b"B\n")
    assert titles(table) == ["AB"]


def test_five_thousand_rows_parse_quickly():
    import time

    rows = "".join(f"TASK-{i},Task number {i},Description {i} with some words\n" for i in range(5000))
    data = ("Key,Summary,Description\n" + rows).encode()
    start = time.perf_counter()
    table = read_csv(data)
    elapsed = time.perf_counter() - start
    assert len(table.rows) == 5000
    assert elapsed < 3.0
