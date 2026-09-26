"""Detect a file's real format from its bytes, not its extension."""

from __future__ import annotations

import io
import zipfile

from ..errors import IngestError
from .types import DEFAULT_LIMITS, Limits

ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # legacy .xls / .doc
PDF_MAGIC = b"%PDF"
BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")


def detect_format(data: bytes, limits: Limits = DEFAULT_LIMITS) -> str:
    """Return "csv", "xlsx" or "json", or raise IngestError."""
    if not data or not data.strip(b" \t\r\n\x00\xef\xbb\xbf"):
        raise IngestError("empty_file")
    if len(data) > limits.max_bytes:
        raise IngestError("file_too_large", limit_mb=limits.max_bytes // (1024 * 1024))

    if data.startswith(ZIP_MAGIC):
        return _detect_zip(data, limits)
    if data.startswith(OLE_MAGIC):
        raise IngestError("legacy_excel")
    if data.startswith(PDF_MAGIC):
        raise IngestError("unsupported_format")

    head = data[:4096]
    is_utf16 = head.startswith((b"\xff\xfe", b"\xfe\xff"))
    if not is_utf16 and b"\x00" in head:
        raise IngestError("unsupported_format")

    first = _first_meaningful_char(head, is_utf16)
    if first in ("[", "{"):
        return "json"
    return "csv"


def _first_meaningful_char(head: bytes, is_utf16: bool) -> str:
    if is_utf16:
        encoding = "utf-16"
    else:
        encoding = "utf-8"
        if head.startswith(BOMS[0]):
            head = head[3:]
    text = head.decode(encoding, errors="ignore").lstrip()
    return text[:1]


def _detect_zip(data: bytes, limits: Limits) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        infos = archive.infolist()
    except (zipfile.BadZipFile, ValueError):
        raise IngestError("unreadable_file") from None

    if "xl/workbook.xml" in names or "xl/workbook.bin" in names:
        if "xl/vbaProject.bin" in names:
            raise IngestError("macro_workbook")
        if "xl/workbook.bin" in names:  # .xlsb binary workbook
            raise IngestError("unsupported_format")
        check_zip_safety(infos, limits)
        return "xlsx"
    if any(name.startswith("Index/") and name.endswith(".iwa") for name in names) or "Index.zip" in names:
        raise IngestError("numbers_file")
    raise IngestError("unsupported_format")


def check_zip_safety(infos: list[zipfile.ZipInfo], limits: Limits) -> None:
    """Refuse archives that would expand to far more data than they occupy."""
    total = 0
    for info in infos:
        total += info.file_size
        if total > limits.max_uncompressed_bytes:
            raise IngestError("archive_too_large")
        if info.compress_size > 0 and info.file_size / info.compress_size > limits.max_compression_ratio:
            # Tiny highly-repetitive parts are normal; only large ones are suspicious.
            if info.file_size > 10 * 1024 * 1024:
                raise IngestError("archive_too_large")
