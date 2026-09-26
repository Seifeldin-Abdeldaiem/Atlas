"""Helpers for building test files in memory."""

from __future__ import annotations

import contextlib
import io
import zipfile

from atlas.errors import AtlasError


@contextlib.contextmanager
def expect_error(code: str):
    """Assert that the block raises an AtlasError with this code."""
    try:
        yield
    except AtlasError as error:
        assert error.code == code, f"expected {code!r}, got {error.code!r}"
        assert error.message, "every error needs a user-facing message"
        return
    raise AssertionError(f"expected AtlasError {code!r}, nothing was raised")


def xlsx_bytes(sheets: dict[str, list[list[object]]], hidden: tuple[str, ...] = ()) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        ws = workbook.create_sheet(name)
        for row in rows:
            ws.append(row)
        if name in hidden:
            ws.sheet_state = "hidden"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def zip_bytes(files: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
