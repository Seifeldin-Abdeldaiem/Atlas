from atlas.ingest import ingest
from atlas.ingest.detect import detect_format
from atlas.ingest.types import Limits

from .util import expect_error, xlsx_bytes, zip_bytes


def test_empty_file():
    with expect_error("empty_file"):
        detect_format(b"")


def test_whitespace_only_file():
    with expect_error("empty_file"):
        detect_format(b"  \r\n\t\n\xef\xbb\xbf")


def test_file_too_large():
    with expect_error("file_too_large"):
        detect_format(b"Title\n" + b"x" * 2000, Limits(max_bytes=1000))


def test_legacy_xls_is_refused_with_advice():
    with expect_error("legacy_excel"):
        detect_format(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600)


def test_pdf_is_refused():
    with expect_error("unsupported_format"):
        detect_format(b"%PDF-1.7\n...")


def test_binary_garbage_is_refused():
    with expect_error("unsupported_format"):
        detect_format(b"\x7fELF\x02\x01\x01\x00\x00\x00binary")


def test_word_document_is_refused():
    with expect_error("unsupported_format"):
        detect_format(zip_bytes({"word/document.xml": b"<w:document/>", "[Content_Types].xml": b"<Types/>"}))


def test_numbers_file_gets_specific_advice():
    with expect_error("numbers_file"):
        detect_format(zip_bytes({"Index/Document.iwa": b"\x00\x01", "Metadata/Properties.plist": b""}))


def test_macro_workbook_is_refused():
    with expect_error("macro_workbook"):
        detect_format(zip_bytes({"xl/workbook.xml": b"<workbook/>", "xl/vbaProject.bin": b"\x00"}))


def test_damaged_zip_is_unreadable():
    with expect_error("unreadable_file"):
        detect_format(b"PK\x03\x04" + b"\x00garbage" * 20)


def test_zip_bomb_is_refused_before_parsing():
    bomb = zip_bytes({"xl/workbook.xml": b"<workbook/>", "xl/worksheets/sheet1.xml": b"\x00" * (3 * 1024 * 1024)})
    with expect_error("archive_too_large"):
        detect_format(bomb, Limits(max_uncompressed_bytes=1024 * 1024))


def test_high_ratio_large_part_is_refused():
    bomb = zip_bytes({"xl/workbook.xml": b"<workbook/>", "xl/worksheets/sheet1.xml": b"A" * (12 * 1024 * 1024)})
    with expect_error("archive_too_large"):
        detect_format(bomb)


def test_detects_json_csv_and_xlsx():
    assert detect_format(b'  [{"title": "a"}]') == "json"
    assert detect_format(b'\xef\xbb\xbf{"issues": []}') == "json"
    assert detect_format(b"Title,Description\nA,B\n") == "csv"
    assert detect_format("Title\nA\n".encode("utf-16")) == "csv"
    assert detect_format(xlsx_bytes({"Tasks": [["Title"], ["A"]]})) == "xlsx"


def test_extension_is_ignored_content_decides():
    # A CSV renamed to .xlsx is still read as CSV: detection never looks at the name.
    result = ingest(b"Summary\nCreate login page\n")
    assert result.format == "csv"
    assert result.report["rows_ready"] == 1
