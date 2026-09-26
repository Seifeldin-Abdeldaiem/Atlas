"""Read CSV/TSV exports. Handles BOMs, UTF-8, UTF-16, Windows-1252 and other
encodings, and comma, semicolon, tab or pipe delimiters."""

from __future__ import annotations

import csv
import io

from charset_normalizer import from_bytes

from ..errors import IngestError
from .tabular import build_table
from .types import DEFAULT_LIMITS, Limits, Table

DELIMITERS = ",;\t|"


def decode_text(data: bytes) -> tuple[str, str]:
    """Return (text, encoding name)."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            raise IngestError("encoding_unknown") from None
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    best = from_bytes(data[:512 * 1024]).best()
    if best is not None and best.encoding and best.chaos < 0.25:
        try:
            return data.decode(best.encoding), best.encoding
        except (UnicodeDecodeError, LookupError):
            pass
    try:
        return data.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        raise IngestError("encoding_unknown") from None


def sniff_delimiter(text: str) -> str:
    sample = text[: 64 * 1024]
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITERS).delimiter
    except csv.Error:
        pass
    # Fall back to the delimiter that appears most consistently in the first lines.
    lines = [line for line in sample.splitlines()[:20] if line.strip()]
    best, best_score = ",", -1.0
    for delimiter in DELIMITERS:
        counts = [line.count(delimiter) for line in lines]
        if not counts or max(counts) == 0:
            continue
        consistency = counts.count(counts[0]) / len(counts)
        score = consistency * counts[0]
        if score > best_score:
            best, best_score = delimiter, score
    return best


def read_csv(data: bytes, limits: Limits = DEFAULT_LIMITS) -> Table:
    text, encoding = decode_text(data)
    text = text.replace("\x00", "")
    delimiter = sniff_delimiter(text)

    csv.field_size_limit(max(limits.max_bytes, limits.max_cell_chars) + 1)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)

    def rows():
        row_number = 0
        try:
            for record in reader:
                row_number += 1
                # Values are kept exactly as written; whitespace cleanup happens
                # in normalization, which stores its result beside the original.
                yield row_number, list(record)
        except csv.Error:
            raise IngestError("unreadable_file") from None

    return build_table(rows(), limits, meta={"encoding": encoding, "delimiter": delimiter})
