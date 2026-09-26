"""Stock and money figures for duplicate groups, and a standard name for each
group (milestone 4).

Wording stays factual: "stock on duplicate lines", never "wasted", because
some duplicates are deliberate (different stores or locations).

    stock_total          all lines of the group, in single units (pack sizes applied)
    stock_on_duplicates  the same, without the master line
    value_on_duplicates  each non-master line's stock x its own unit cost
    cost_low / cost_high cost per single unit across the group

Totals are only given when they are meaningful: no stock or cost column,
mixed currencies, or units that can't be converted give None, never a guess.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .match import Group, Item
from .rules import COLOURS, CONTAINER_WORDS, MATERIALS, PRODUCT_TYPES

COST_GAP = 0.20  # groups whose unit costs differ by more than 20% are counted
_SINGLE_UNITS = {"", "each", "ea", "pc", "pcs", "piece", "pieces", "unit", "units", "no", "nr", "حبه", "قطعه"}


@dataclass
class GroupFigures:
    stock_total: float | None
    stock_on_duplicates: float | None
    value_on_duplicates: float | None
    cost_low: float | None
    cost_high: float | None
    units_differ: bool = False


def _unit_key(item: Item, unit_value: str | None) -> str:
    if item.norm.get("pack"):
        return "each"  # converted to single units via the pack size
    unit = re.sub(r"[^\w]", "", (unit_value or "").casefold())
    return "each" if unit in _SINGLE_UNITS else unit


def figures(group: Group, items: dict[int, Item], units: dict[int, str | None], money_ok: bool) -> GroupFigures:
    members = [items[r] for r in group.rows]
    has_stock = any(i.norm.get("stock") is not None for i in members)
    has_cost = any(i.norm.get("unit_cost") is not None for i in members)
    comparable = len({_unit_key(i, units.get(i.row)) for i in members}) == 1

    def singles(i: Item) -> float:
        return (i.norm.get("stock") or 0.0) * (i.norm.get("pack") or 1)

    stock_total = stock_dup = value_dup = None
    if has_stock and comparable:
        stock_total = round(sum(max(singles(i), 0.0) for i in members), 3)
        stock_dup = round(sum(max(singles(i), 0.0) for i in members if i.row != group.master), 3)
    if has_stock and has_cost and money_ok:
        # Line stock x line cost: both are in the line's own unit, so pack
        # sizes cancel out and units need not match.
        value_dup = round(
            sum(max(i.norm.get("stock") or 0.0, 0.0) * (i.norm.get("unit_cost") or 0.0) for i in members if i.row != group.master), 2
        )
    per_unit = [i.norm["unit_cost"] / (i.norm.get("pack") or 1) for i in members if i.norm.get("unit_cost") is not None]
    low = round(min(per_unit), 4) if per_unit and money_ok else None
    high = round(max(per_unit), 4) if per_unit and money_ok else None
    return GroupFigures(stock_total, stock_dup, value_dup, low, high, units_differ=has_stock and not comparable)


def currencies(items: Iterable[Item], default: str) -> set[str]:
    return {i.norm.get("currency") or default for i in items if i.norm.get("unit_cost") is not None}


def headline(all_figures: list[GroupFigures], currency: str | None, has_stock: bool, has_cost: bool, mixed: set[str]) -> dict:
    stock = [f.stock_on_duplicates for f in all_figures if f.stock_on_duplicates is not None]
    value = [f.value_on_duplicates for f in all_figures if f.value_on_duplicates is not None]
    gaps = sum(1 for f in all_figures if f.cost_low and f.cost_high and (f.cost_high - f.cost_low) / f.cost_low > COST_GAP)
    return {
        "has_stock": has_stock,
        "has_cost": has_cost,
        "currency": currency if len(mixed) <= 1 else None,
        "mixed_currencies": sorted(mixed) if len(mixed) > 1 else [],
        "units_on_duplicates": round(sum(stock), 3) if stock else None,
        "value_on_duplicates": round(sum(value), 2) if value else None,
        "groups_with_cost_gap": gaps,
        "groups_units_differ": sum(1 for f in all_figures if f.units_differ),
    }


# ---------------------------------------------------------------- standard names

_STOP = {"with", "and", "for", "of", "the", "a", "an", "to", "in", "on", "open", "type", "size", "sz", "eu", "new", "genuine", "original", "steel"}
_ACRONYMS = {"led", "mcb", "rcd", "rcbo", "pvc", "ptfe", "hss", "abs", "uv", "ac", "dc", "ip", "ep", "gx", "nbr", "epdm", "3m"}


def _word(w: str) -> str:
    return w.upper() if w in _ACRONYMS or re.search(r"\d", w) else w.capitalize()


def standard_name(members: list[Item], master: Item) -> str:
    """"Bearing, Deep Groove Ball, SKF 6205-2RS" or "Bolt, Hex, M8 x 25 mm,
    A2 stainless". Built from the member with the most descriptive Latin
    name, so an Arabic master still gets a readable standard name."""
    latin = [m for m in members if m.norm.get("script") != "arabic"]
    source = master if master in latin or not latin else max(latin, key=lambda m: len((m.norm.get("core") or "").split()))
    n = source.norm
    brand = (n.get("brand") or master.norm.get("brand") or "").upper()
    part = (n.get("part_base") or master.norm.get("part_base") or "").upper()
    variants = n.get("variants") or master.norm.get("variants") or []
    skip = {brand.lower(), part.lower(), *variants, *(v for v in n.get("codes", []) if v.startswith(part.lower()) and part)}

    types = n.get("types") or master.norm.get("types") or []
    head = types[0].capitalize() if types else ""
    words = []
    for w in (n.get("core") or n.get("text") or "").split():
        head_word = types and PRODUCT_TYPES.get(w) == types[0] and w.rstrip("s") == types[0]
        if w in skip or w in _STOP or w in CONTAINER_WORDS or w in COLOURS or w in MATERIALS or head_word or len(w) == 1:
            continue
        if not re.search(r"[a-z0-9]", w):  # leave Arabic words out of the English name
            continue
        if w not in words:
            words.append(w)
    ident = " ".join(x for x in (brand, f"{part}-{'/'.join(v.upper() for v in variants)}" if part and variants else part) if x)

    dims = n.get("dims") or {}
    specs = []
    if dims.get("thread"):
        length = dims.get("length_mm", [None])[0]
        specs.append(f"{dims['thread'].upper()} x {length:g} mm" if length else dims["thread"].upper())
    elif dims.get("length_mm"):
        specs.append(f"{dims['length_mm'][0]:g} mm")
    if dims.get("sizes_mm"):
        specs.append(" x ".join(f"{v:g}" for v in dims["sizes_mm"]) + " mm")
    for key, unit in (("power_w", "W"), ("voltage_v", "V"), ("current_a", "A")):
        if dims.get(key):
            specs.append(f"{dims[key][0]:g} {unit}")
    if dims.get("poles"):
        specs.append(f"{dims['poles']}P")
    grades = [m.split(":")[1].upper() for m in n.get("materials", []) if not m.startswith("material:")]
    base = [m.split(":")[1].capitalize() for m in n.get("materials", []) if m.startswith("material:")]
    if grades or base:
        specs.append(" ".join(grades + base))
    if n.get("colours"):
        specs.append("/".join(c.capitalize() for c in n["colours"]))

    parts = [head, " ".join(_word(w) for w in words), ident, *specs]
    return ", ".join(p for p in parts if p) or (master.name or "")[:120]
