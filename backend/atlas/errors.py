"""User-facing errors.

Every error a user can see has a stable code and a plain-language message
that says what happened and what to do next. Raw exceptions and stack traces
are logged server-side under a reference id and never returned to clients.
"""

from __future__ import annotations

import secrets

MESSAGES: dict[str, str] = {
    # Upload and file type
    "empty_file": "This file is empty. Export your tasks again and upload the new file.",
    "file_too_large": "This file is larger than {limit_mb} MB. Split it into smaller files or remove columns you don't need.",
    "unsupported_format": "We can't read this file. Upload a CSV, Excel (.xlsx) or JSON file.",
    "legacy_excel": "This is an older Excel (.xls) file. Open it in Excel and save it as .xlsx or CSV, then upload it again.",
    "macro_workbook": "This Excel file contains macros, which we don't accept. Save it as a regular .xlsx or CSV and upload it again.",
    "numbers_file": "This is an Apple Numbers file. Export it as CSV or Excel, then upload it again.",
    "archive_too_large": "This Excel file expands to more data than we can safely read. Save it as CSV or remove unused sheets.",
    "unreadable_file": "We couldn't read this file. It may be damaged. Export it again from your task tool.",
    "encoding_unknown": "We couldn't work out this file's text encoding. Save it as CSV with UTF-8 encoding and upload it again.",
    "invalid_json": "This JSON file isn't valid JSON. Export it again from your task tool.",
    "json_shape": "We couldn't find a list of tasks in this JSON file. It should contain a list of objects, one per task.",
    # Content
    "no_rows": "We didn't find any tasks in this file.",
    "no_header": "We couldn't find a header row. The first row of the file should name the columns.",
    "too_many_rows": "This file has more than {limit_rows:,} tasks. Split it into smaller files.",
    "too_many_columns": "This file has more than {limit_cols} columns. Remove columns you don't need and upload it again.",
    "no_title_column": "Choose which column holds the task title. Atlas needs a title for every task.",
    "no_usable_rows": "None of the rows has a title, so there's nothing to analyze.",
    "no_name_column": "Choose which column holds the item name. Atlas needs a name for every item.",
    "no_usable_items": "None of the rows has an item name, so there's nothing to analyze.",
    "invalid_kind": "Choose either a task export or a product catalogue.",
    "analysis_not_available": "Finding duplicates works on product catalogues for now. Switch this file to a product catalogue if that's what it is.",
    "invalid_review": "That change doesn't fit these results. Reload the page and try again.",
    "admin_only": "Only workspace admins can change this setting.",
    "export_failed": "We couldn't build your download. Try again; your results are unchanged.",
    "analysis_failed": "Something went wrong while looking for duplicates. Try again; your file and column choices are unchanged.",
    "sheet_not_found": "That sheet isn't in this workbook.",
    "file_too_complex": "This file took too long or needed too much memory to read. Save it as CSV, or split it into smaller files.",
    # Platform
    "not_found": "We couldn't find that. It may have been deleted.",
    "no_workspace": "Choose or create a workspace to continue.",
    "unauthorized": "Your session has ended. Sign in again.",
    "forbidden": "You don't have permission to do that.",
    "too_many_active_uploads": "You already have {limit} files being read. Wait for one to finish, then try again.",
    "invalid_mapping": "That column mapping isn't valid: {detail}",
    "not_ready": "This dataset is still being read. Try again in a moment.",
    "internal_error": "Something went wrong on our side. Try again; if it keeps happening, contact support with reference {reference}.",
}


def new_reference() -> str:
    """Short id shown to users and written to logs, to match a report to a log line."""
    return "ATL-" + secrets.token_hex(3).upper()


class AtlasError(Exception):
    """An error with a stable code and a user-facing message."""

    status_code = 400

    def __init__(self, code: str, status_code: int | None = None, **params: object) -> None:
        self.code = code
        self.params = params
        if status_code is not None:
            self.status_code = status_code
        super().__init__(code)

    @property
    def message(self) -> str:
        template = MESSAGES.get(self.code, MESSAGES["internal_error"])
        try:
            return template.format(**self.params)
        except (KeyError, IndexError, ValueError):
            return template

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}


class IngestError(AtlasError):
    """A file could not be read. Raised by the ingest package; never contains file content."""

    status_code = 422
