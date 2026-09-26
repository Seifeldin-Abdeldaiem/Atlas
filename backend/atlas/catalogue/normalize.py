"""Turn one catalogue row into a comparable form plus structured attributes.

Pure and deterministic: no AI, no database, no settings. The original row is
never modified; the result is stored beside it (tasks.norm) and is what
matching reads. Text is capped before any pattern runs, and every pattern is
linear, so a hostile cell can't make this slow.

Example, "SKF 6205-2RS Deep Groove Ball Bearing":
    text      "skf 6205 2rs deep groove ball bearing"
    brand     "skf"          (Brand column first, else a known brand in the name)
    part_base "6205"
    variants  ["2rs"]        classes ["seal:rubber_both"]
    types     ["bearing"]

Arabic names work too: "رولمان بلي ٦٢٠٥ ٢ار اس اس كي اف" gives the same brand,
part number, variant and type, because Arabic digits are converted and brands
and suffixes spelled in Arabic letters are rewritten to Latin first.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from .rules import (
    ABBREVIATIONS,
    ARABIC_DROP,
    ARABIC_UNIFY,
    ARABIC_V_BEFORE_DIGIT,
    BRAND_ALIASES,
    BRANDS_IN_TEXT,
    COLOURS,
    CONTAINER_WORDS,
    DIGITS,
    LENGTH_TO_MM,
    LETTER_NAMES,
    MASS_TO_G,
    MATERIAL_IMPLIES,
    MATERIALS,
    PHRASES,
    PRODUCT_TYPES,
    SUFFIXES_LONGEST_FIRST,
    VARIANT_SUFFIXES,
    VOLUME_TO_ML,
)

if TYPE_CHECKING:
    from ..ingest.types import Table

# Bump when normalisation changes, so stored values are recomputed.
NORM_VERSION = 4

NAME_CAP = 500
DETAILS_CAP = 2000
FIELD_CAP = 120

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = dict.fromkeys(map(ord, "‘’‚‛′"), "'") | dict.fromkeys(map(ord, "“”„″"), '"')

def _words(options) -> str:
    return "|".join(re.escape(k) for k in sorted(options, key=len, reverse=True))


_ABBREV = re.compile(r"(?<![a-z0-9])(" + _words(ABBREVIATIONS) + r")(?![a-z0-9])")
_PHRASE = re.compile(r"(?<!\w)(" + _words(PHRASES) + r")(?!\w)")
_ARABIC_V = re.compile(re.escape(ARABIC_V_BEFORE_DIGIT) + r"(?=\d)")
_NON_WORD = re.compile(r"[^\w.]+|_")
_ARABIC_LETTER = re.compile(r"[\u0621-\u064a]")
_LATIN_LETTER = re.compile(r"[a-zA-Z]")
_LOOSE_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")
_SPLIT = re.compile(r"[\s,;:()\[\]{}/+\-]+")

_NUM = r"(\d{1,6}(?:\.\d{1,4})?)"
_NUM_ALONE = r"(?<![\w.])" + _NUM  # not glued to letters: "sha7m" is a word, not 7 m
_THREAD = re.compile(r"(?<![a-z0-9])m" + _NUM + r"(?:\s*[x×]\s*" + _NUM + r")?(?![a-z0-9.])")
_SIZES = re.compile(_NUM_ALONE + r"\s*[x×]\s*" + _NUM + r"(?:\s*[x×]\s*" + _NUM + r")?\s*(mm|cm|in)?(?![a-z0-9])")
_SINGLE = re.compile(_NUM_ALONE + r"\s*(" + _words([*LENGTH_TO_MM, *MASS_TO_G, *VOLUME_TO_ML]) + r")(?!\w)")
_POWER = re.compile(_NUM_ALONE + r"\s*(w|kw|watt|watts|وات)(?!\w)")
_VOLTAGE = re.compile(_NUM_ALONE + r"\s*(v|volt|volts|فولت)(?!\w)")
_POLES = re.compile(r"(?<!\w)(single|double|triple|four|1|2|3|4)[\s-]*(?:pole|p)(?!\w)")
_POLE_WORDS = {"single": 1, "double": 2, "triple": 3, "four": 4}
_CURRENT = re.compile(_NUM_ALONE + r"\s*(a|amp|amps|امبير)(?!\w)")
_BRAND_WORD = re.compile(r"(?<!\w)(" + _words(BRANDS_IN_TEXT) + r")(?!\w)")
_STANDALONE_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")

_PACK = (
    re.compile(r"(?<![a-z])(?:box|pack|pk|bag|tub|case|carton)\s*(?:of\s*)?(\d{1,5})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,5})\s*(?:/|per\s*)(?:box|pack|pk|bag)(?![a-z])"),
    re.compile(r"(?<!\d)(\d{1,5})\s*(?:pcs|pc|pieces|pk)(?![a-z])"),
)

_CODE_TOKEN = re.compile(r"[A-Z]{0,4}\d{3,}[A-Z0-9]*")
_DIM_TOKEN = re.compile(r"M?\d+(?:\.\d+)?(?:X\d+(?:\.\d+)?){1,2}(?:MM|CM|M|IN)?|\d+(?:\.\d+)?(?:MM|CM|M|IN|KG|KGS|G|GM|GMS|ML|L|LT|LTR|W|KW|V|A)|M\d+(?:\.\d+)?")
_QUANTITY_WORDS = {"OF", "X", "PACK", "BOX", "QTY", "PK", "BAG", "CASE"}
_UNIT_WORDS = {u.upper() for u in (*LENGTH_TO_MM, *MASS_TO_G, *VOLUME_TO_ML, "w", "kw", "watt", "watts", "v", "volt", "volts", "a", "amp", "amps", "وات", "فولت")}

_CURRENCIES = {"£": "GBP", "$": "USD", "€": "EUR", "gbp": "GBP", "usd": "USD", "eur": "EUR"}
_CURRENCY_MARK = re.compile(r"£|\$|€|\b(?:gbp|usd|eur)\b", re.IGNORECASE)
_THOUSANDS = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_PLAIN_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


# ---------------------------------------------------------------- text

def _clean(value: str | None, cap: int) -> str:
    """Unicode-normalise, convert Arabic digits and letter variants, and
    rewrite brands and suffixes spelled in Arabic letters to Latin."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value[:cap])
    value = value.translate(_DASHES).translate(_QUOTES).translate(DIGITS).translate(ARABIC_DROP).translate(ARABIC_UNIFY)
    value = " ".join(value.split())
    value = _PHRASE.sub(lambda m: PHRASES[m.group(1)], value)
    return _ARABIC_V.sub("v", value)


def script_of(value: str | None) -> str:
    arabic = len(_ARABIC_LETTER.findall(value or ""))
    latin = len(_LATIN_LETTER.findall(value or ""))
    if arabic and latin:
        return "arabic" if arabic > latin * 2 else "latin" if latin > arabic * 2 else "mixed"
    return "arabic" if arabic else "latin"


def normalise_text(value: str | None, cap: int = NAME_CAP) -> str:
    """Lower-case, expand abbreviations, keep letters and digits apart from
    punctuation: "SKF 6205-2RS Brg" -> "skf 6205 2rs bearing"."""
    return _tidy(_clean(value, cap).casefold())


def _tidy(text: str) -> str:
    text = _ABBREV.sub(lambda m: ABBREVIATIONS[m.group(1)], text)
    text = _NON_WORD.sub(" ", text)
    text = _LOOSE_DOT.sub(" ", text)
    return " ".join(text.split())


_CODE_WORD = re.compile(r"(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]{2,8}")


# ---------------------------------------------------------------- brand

def brand_key(value: str | None) -> str | None:
    key = re.sub(r"[^a-z0-9]", "", _clean(value, FIELD_CAP).casefold())
    if not key:
        return None
    return BRAND_ALIASES.get(key, key)


def find_brand(brand_value: str | None, text: str) -> tuple[str | None, str | None]:
    """Brand column first; otherwise a distinctive brand name in the text."""
    key = brand_key(brand_value)
    if key:
        return key, "column"
    words = text.split()
    for word in words:
        if word in BRANDS_IN_TEXT:
            return BRAND_ALIASES.get(word, word), "text"
    # Letters spelled out: "ess kay eff" -> "skf".
    for size in (4, 3, 2):
        for i in range(len(words) - size + 1):
            window = words[i:i + size]
            if all(w in LETTER_NAMES for w in window):
                joined = "".join(LETTER_NAMES[w] for w in window)
                if joined in BRANDS_IN_TEXT:
                    return BRAND_ALIASES.get(joined, joined), "text"
    return None, None


# ---------------------------------------------------------------- part numbers

def _split_suffixes(token: str) -> list[str] | None:
    """"2RSC3" -> ["2RS", "C3"]; None if the token isn't made only of suffixes."""
    out, rest = [], token
    while rest:
        for suffix in SUFFIXES_LONGEST_FIRST:
            if rest.startswith(suffix):
                out.append(suffix)
                rest = rest[len(suffix):]
                break
        else:
            return None
    return out


def _is_base(value: str) -> bool:
    return bool(value) and value[-1].isdigit() and sum(ch.isdigit() for ch in value) >= 3


def _peel(token: str, depth: int = 0) -> tuple[str, list[str]]:
    """Peel suffixes written onto the base: "62052RSC3" -> ("6205", ["2RS", "C3"]).
    What is left must end in a digit and keep at least three digits. Written
    without separators some codes are ambiguous ("6202Z" could be 620 + 2Z);
    the longest suffix wins, and Milestone 3's AI review covers the rest."""
    if depth < 4:
        for suffix in SUFFIXES_LONGEST_FIRST:
            if token.endswith(suffix) and len(token) > len(suffix):
                rest = token[: -len(suffix)]
                if _is_base(rest):
                    return rest, [suffix]
                base, inner = _peel(rest, depth + 1)
                if inner:
                    return base, inner + [suffix]
    return token, []


def _is_code(token: str, previous: str | None, following: str | None = None) -> bool:
    if not _CODE_TOKEN.fullmatch(token) or _DIM_TOKEN.fullmatch(token):
        return False
    # "Box of 1000" is a quantity and "209 L" a size, not part numbers.
    return not (token.isdigit() and (previous in _QUANTITY_WORDS or following in _UNIT_WORDS))


def _tokens(value: str) -> list[str]:
    return [t for t in _SPLIT.split(_clean(value, NAME_CAP).upper()) if t]


def _variants_after(tokens: list[str], start: int) -> list[str]:
    found: list[str] = []
    for token in tokens[start:]:
        parts = _split_suffixes(token)
        if parts is None:
            break
        found.extend(parts)
    return found


def parse_part(part_value: str | None, name: str | None) -> dict:
    """Base part number and variant suffixes, from the Part number column when
    mapped, else the first code-like word in the name. When the column holds
    only the base ("6205"), variants are still read from the name."""
    base: str | None = None
    variants: list[str] = []
    extra: list[str] = []
    source = None

    column_tokens = _tokens(part_value or "")
    if column_tokens:
        source = "column"
        base, variants = _peel(column_tokens[0])
        for token in column_tokens[1:]:
            parts = _split_suffixes(token)
            if parts is None:
                extra.append(token)
            else:
                variants.extend(parts)

    name_tokens = _tokens(name or "")
    if base is None:
        previous = None
        for i, token in enumerate(name_tokens):
            if _is_code(token, previous, name_tokens[i + 1] if i + 1 < len(name_tokens) else None):
                base, variants = _peel(token)
                variants += _variants_after(name_tokens, i + 1)
                source = "text"
                break
            previous = token
    else:
        for i, token in enumerate(name_tokens):
            token_base, attached = _peel(token)
            if token_base == base:
                variants += attached + _variants_after(name_tokens, i + 1)
                break

    unique = list(dict.fromkeys(variants))
    classes = sorted({c for v in unique for c in VARIANT_SUFFIXES[v]})
    return {
        "part_base": base.lower() if base else None,
        "part_source": source,
        "variants": [v.lower() for v in unique],
        "variant_classes": classes,
        "part_extra": [t.lower() for t in extra],
    }


# ---------------------------------------------------------------- sizes, packs

def _num(value: str) -> float:
    return round(float(value), 3)


def parse_measures(value: str | None) -> dict:
    """Threads, box sizes, single measures (mm, g, ml), power and voltage."""
    return _measures(_clean(value, NAME_CAP).casefold())[0]


def _measures(text: str) -> tuple[dict, str]:
    """Measures found in cleaned, lower-case text, and the text without them."""
    out: dict[str, object] = {}
    text = _BRAND_WORD.sub(" ", text)  # "3m" is a brand, not 3 metres

    thread = _THREAD.search(text)
    if thread:
        out["thread"] = f"m{thread.group(1)}"
        if thread.group(2):
            out["length_mm"] = [_num(thread.group(2))]
        text = text[: thread.start()] + " " + text[thread.end():]

    sizes = _SIZES.search(text)
    if sizes:
        factor = LENGTH_TO_MM.get(sizes.group(4) or "mm", 1.0)
        out["sizes_mm"] = [_num(str(float(g) * factor)) for g in sizes.groups()[:3] if g]
        text = text[: sizes.start()] + " " + text[sizes.end():]

    for number, unit in _SINGLE.findall(text):
        if unit in LENGTH_TO_MM:
            out.setdefault("length_mm", []).append(_num(str(float(number) * LENGTH_TO_MM[unit])))
        elif unit in MASS_TO_G:
            out.setdefault("mass_g", []).append(_num(str(float(number) * MASS_TO_G[unit])))
        elif unit in VOLUME_TO_ML:
            out.setdefault("volume_ml", []).append(_num(str(float(number) * VOLUME_TO_ML[unit])))
    text = _SINGLE.sub(" ", text)
    for number, unit in _POWER.findall(text):
        out.setdefault("power_w", []).append(_num(str(float(number) * (1000 if unit == "kw" else 1))))
    text = _POWER.sub(" ", text)
    for number, _unit in _VOLTAGE.findall(text):
        out.setdefault("voltage_v", []).append(_num(number))
    text = _VOLTAGE.sub(" ", text)
    poles = _POLES.search(text)
    if poles:
        out["poles"] = _POLE_WORDS.get(poles.group(1)) or int(poles.group(1))
        text = _POLES.sub(" ", text)
    for number, _unit in _CURRENT.findall(text):
        out.setdefault("current_a", []).append(_num(number))
    return out, _CURRENT.sub(" ", text)


def parse_pack(*values: str | None) -> int | None:
    """Units per line: "Box of 10", "10/pk", "25 pcs". None means single units."""
    for value in values:
        text = _clean(value, NAME_CAP).casefold()
        for pattern in _PACK:
            match = pattern.search(text)
            if match and int(match.group(1)) > 1:
                return int(match.group(1))
    return None


# ---------------------------------------------------------------- numbers

def parse_number(value: str | None) -> tuple[float | None, str | None, bool]:
    """(number, currency, ok). Blank is ok with no number; "n/a" is not ok.
    Handles "£4.20", "1,250", "4,20", "(12.50)" and "12 GBP"."""
    text = _clean(value, FIELD_CAP)
    if not text:
        return None, None, True
    currency = None
    mark = _CURRENCY_MARK.search(text)
    if mark:
        currency = _CURRENCIES[mark.group(0).casefold() if mark.group(0).isalpha() else mark.group(0)]
        text = (text[: mark.start()] + text[mark.end():]).strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(" ", "")
    if _THOUSANDS.fullmatch(text):
        text = text.replace(",", "")
    elif text.count(",") == 1 and "." not in text and re.fullmatch(r"-?\d+,\d{1,2}", text):
        text = text.replace(",", ".")
    if not _PLAIN_NUMBER.fullmatch(text):
        return None, currency, False
    number = float(text)
    return (-number if negative else number), currency, True


# ---------------------------------------------------------------- rows

def _numbers(residual: str, part_base: str | None) -> list[str]:
    """Numbers standing on their own once sizes, packs and the part number are
    gone: grades, series, ratings ("Gadus S2 V220 2" -> ["2"])."""
    for pattern in _PACK:
        residual = pattern.sub(" ", residual)
    base = part_base or ""
    found = {n for n in _STANDALONE_NUMBER.findall(residual) if not (n == base or (len(n) >= 3 and (base.startswith(n) or base.endswith(n))))}
    return sorted(found)


def _materials(words: list[str]) -> list[str]:
    found = {MATERIALS[w] for w in words if w in MATERIALS}
    found |= {MATERIAL_IMPLIES[m] for m in found if m in MATERIAL_IMPLIES}
    return sorted(found)


def _core(residual: str) -> tuple[str, list[str]]:
    """The name without sizes, packs and container words, for comparing names;
    and the short letter-and-digit codes in it (S2, S3, IP65, H700)."""
    for pattern in _PACK:
        residual = pattern.sub(" ", residual)
    words = [w for w in _tidy(residual).split() if w not in CONTAINER_WORDS]
    codes = sorted({w for w in words if _CODE_WORD.fullmatch(w) and w not in MATERIALS})
    return " ".join(words), codes


def normalise_row(values: dict[str, str], mapping: dict[str, str | None]) -> dict:
    def get(field: str) -> str | None:
        column = mapping.get(field)
        return values.get(column) if column else None

    name = get("item_name") or ""
    text = normalise_text(name)
    words = text.split()
    brand, brand_source = find_brand(get("brand"), text)
    stock, _, stock_ok = parse_number(get("stock"))
    cost, currency, cost_ok = parse_number(get("unit_cost"))
    part = parse_part(get("part_number"), name)
    dims, residual = _measures(_clean(name, NAME_CAP).casefold())
    core, codes = _core(residual)
    skip = {part["part_base"], *part["variants"], *(v + "".join(part["variants"]) for v in [part["part_base"] or ""])}

    out: dict[str, object] = {
        "v": NORM_VERSION,
        "text": text,
        "core": core,
        "codes": [c for c in codes if c not in skip],
        "script": script_of(name),
        "brand": brand,
        "brand_source": brand_source,
        **part,
        "types": sorted({PRODUCT_TYPES[w] for w in words if w in PRODUCT_TYPES}),
        "colours": sorted({COLOURS[w] for w in words if w in COLOURS}),
        "materials": _materials(words),
        "numbers": _numbers(residual, part["part_base"]),
        "dims": dims,
        "pack": parse_pack(get("unit"), name),
        "stock": stock,
        "unit_cost": cost,
        "currency": currency,
    }
    details = get("details")
    if details:
        out["details_text"] = normalise_text(details, DETAILS_CAP)
    problems = [code for code, ok in (("stock_not_number", stock_ok), ("cost_not_number", cost_ok)) if not ok]
    if problems:
        out["problems"] = problems
    return out


def normalise_table(table: Table, mapping: dict[str, str | None]) -> dict[int, dict]:
    """Normalised values for every readable row that has an item name."""
    name_column = mapping.get("item_name")
    if not name_column:
        return {}
    return {
        row.row_number: normalise_row(row.values, mapping)
        for row in table.rows
        if (row.values.get(name_column) or "").strip()
    }
