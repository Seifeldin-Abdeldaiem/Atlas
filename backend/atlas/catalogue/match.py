"""Find duplicate lines in a normalised catalogue.

    1. Candidate pairs: only rows that could plausibly match are compared
       (same part number, or a shared rare word).
    2. Compare: hard rules first (a different variant, brand, type, colour,
       size, power or grade means a different product), then name similarity.
       Every pair ends as "same", "different" or "unsure".
    3. Review (optional): an AI reviewer can settle "unsure" pairs (Milestone 3).
    4. Group: "same" pairs are joined; a group holding any hard conflict is
       split at its weakest link, so A~B and B~C can't merge A and C when A and
       C are different products.
    5. Master: each group suggests the most complete row to keep.

Pure: no database and no network. Wrong merges cost more than missed ones,
so anything doubtful stays "unsure" rather than being grouped.
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise

from .rules import ABSENT_MEANS_STANDARD, CLASS_NAMES, PROPERTY_NAMES, VARIANT_SUFFIXES

# Name similarity (0-1) thresholds. Tuned on the labelled fixtures.
SUPPORT = 0.45       # same part and brand, no variant: names must be at least this alike
NAMES_SAME = 0.90    # no part number: this alike counts as the same item (medium)
NAMES_UNSURE = 0.60  # no part number: this alike needs a second look
LOOKALIKE = 0.75     # a "different" pair this alike is shown as a look-alike

MAX_BLOCK = 150       # rows sharing one part number compared all-to-all
NEIGHBOURS = 12       # other candidates kept per row, by shared rare words
MAX_UNSURE = 5000     # unsure pairs kept for review, most alike first


@dataclass(frozen=True)
class Item:
    row: int
    norm: dict
    code: str | None = None
    name: str = ""


@dataclass
class Pair:
    a: int
    b: int
    verdict: str                  # same | different | unsure
    reason: str                   # code, see explain()
    detail: str                   # plain language
    score: float                  # name similarity 0-1
    confidence: str | None = None  # high | medium | reviewed, for "same"
    lookalike: bool = False
    source: str = "rule"          # rule | text | ai | review
    hard: bool = False            # "different" because of a real conflict, not just unlike names


@dataclass
class Group:
    rows: list[int]
    master: int
    confidence: str
    reasons: list[str]


@dataclass
class Analysis:
    groups: list[Group]
    lookalikes: list[Pair]
    unsure: list[Pair]
    stats: dict = field(default_factory=dict)


class Reviewer:
    """Settles unsure pairs. Returns, per pair, ("same" | "different" | "unsure", reason)."""

    def review(self, pairs: list[tuple[Item, Item]]) -> list[tuple[str, str]]:  # pragma: no cover - interface
        raise NotImplementedError


# ---------------------------------------------------------------- similarity

@dataclass(frozen=True)
class _Features:
    tokens: frozenset[str]
    trigrams: frozenset[str]


def _features(item: Item) -> _Features:
    # The core name leaves out sizes, packs and brands (compared separately).
    text = item.norm.get("core") or item.norm.get("text", "")
    squashed = "#" + text.replace(" ", "") + "#"
    return _Features(frozenset(text.split()), frozenset(squashed[i:i + 3] for i in range(len(squashed) - 2)))


def _jaccard(x: frozenset, y: frozenset) -> float:
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


def name_similarity(fx: _Features, fy: _Features) -> float:
    return round(0.5 * _jaccard(fx.tokens, fy.tokens) + 0.5 * _jaccard(fx.trigrams, fy.trigrams), 3)


# ---------------------------------------------------------------- comparing two rows

def _by_property(values: Iterable[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for c in values:
        prop, _, _value = c.partition(":")
        out[prop].add(c)
    return out


def _classes_by_property(norm: dict) -> dict[str, set[str]]:
    return _by_property(norm.get("variant_classes", []))


def _suffixes_for(norm: dict, prop: str) -> str:
    found = [v.upper() for v in norm.get("variants", []) if any(c.startswith(prop + ":") for c in VARIANT_SUFFIXES.get(v.upper(), ()))]
    return "/".join(found)


def _describe(classes: set[str]) -> str:
    return " and ".join(sorted(CLASS_NAMES.get(c, c) for c in classes)) or "none written"


def _disjoint(x: Iterable, y: Iterable) -> bool:
    x, y = set(x), set(y)
    return bool(x) and bool(y) and not (x & y)


def _fmt(values: Iterable[float], unit: str) -> str:
    return "/".join(f"{v:g} {unit}" for v in values)


_LETTER_PREFIX = re.compile(r"^[a-z]{1,2}(?=\d)")


def same_part(px: str | None, py: str | None) -> bool:
    """Equal part numbers, allowing a one- or two-letter prefix on one side:
    "h700" = "700", "v220" = "220" (when at least three digits remain)."""
    if not px or not py:
        return False
    if px == py:
        return True
    bx, by = _LETTER_PREFIX.sub("", px), _LETTER_PREFIX.sub("", py)
    return bx == by and sum(ch.isdigit() for ch in bx) >= 3


def _conflicts(x: dict, y: dict) -> tuple[list[tuple[str, str]], list[str]]:
    """Hard conflicts (code, detail) and soft doubts (codes) between two rows."""
    hard: list[tuple[str, str]] = []
    soft: list[str] = []
    parts_match = same_part(x.get("part_base"), y.get("part_base"))

    bx, by = x.get("brand"), y.get("brand")
    if bx and by and bx != by:
        if parts_match and x.get("variant_classes") == y.get("variant_classes"):
            hard.append(("brand_equivalent", f"Equivalent parts from different brands ({bx.upper()} and {by.upper()}). Kept apart; you may choose to stock one."))
        else:
            hard.append(("brand_differs", f"Different brands: {bx.upper()} and {by.upper()}."))

    px, py = x.get("part_base"), y.get("part_base")
    if px and py and not parts_match:
        if px in py or py in px:
            soft.append("part_partial")
        else:
            hard.append(("part_differs", f"Different part numbers: {px.upper()} and {py.upper()}."))

    cx, cy = _classes_by_property(x), _classes_by_property(y)
    for prop in sorted(set(cx) | set(cy)):
        if cx.get(prop) and cy.get(prop):
            if cx[prop] != cy[prop]:
                detail = (
                    f"Different {PROPERTY_NAMES.get(prop, prop)}: {_suffixes_for(x, prop)} has {_describe(cx[prop])}, "
                    f"{_suffixes_for(y, prop)} has {_describe(cy[prop])}."
                )
                hard.append((f"{prop}_differs", detail))
        elif prop in ABSENT_MEANS_STANDARD:
            which = x if cx.get(prop) else y
            hard.append((f"{prop}_differs", f"Only one has {_describe(cx.get(prop) or cy.get(prop))} ({_suffixes_for(which, prop)})."))
        else:
            soft.append("variant_missing")
    if parts_match and not hard and x.get("variant_classes") == y.get("variant_classes") and set(x.get("variants", [])) != set(y.get("variants", [])):
        vx = "/".join(v.upper() for v in x.get("variants", []))
        vy = "/".join(v.upper() for v in y.get("variants", []))
        hard.append(("variant_spelling", f"Same type of variant written two ways ({vx} and {vy}). Kept apart; merge them yourself if they are the same stock item."))

    if _disjoint(x.get("types", []), y.get("types", [])):
        hard.append(("type_differs", f"Different kinds of product: {', '.join(x['types'])} and {', '.join(y['types'])}."))
    if _disjoint(x.get("colours", []), y.get("colours", [])):
        hard.append(("colour_differs", f"Different colours: {', '.join(x['colours'])} and {', '.join(y['colours'])}."))
    mx, my = _by_property(x.get("materials", [])), _by_property(y.get("materials", []))
    for prop in sorted(set(mx) & set(my)):
        if mx[prop] != my[prop]:
            hard.append(("material_differs", f"Different {prop.replace('_', ' ')}: {', '.join(sorted(v.split(':')[1] for v in mx[prop]))} and {', '.join(sorted(v.split(':')[1] for v in my[prop]))}."))
            break

    dx, dy = x.get("dims", {}), y.get("dims", {})
    if dx.get("thread") and dy.get("thread") and dx["thread"] != dy["thread"]:
        hard.append(("size_differs", f"Different threads: {dx['thread'].upper()} and {dy['thread'].upper()}."))
    if dx.get("sizes_mm") and dy.get("sizes_mm") and dx["sizes_mm"] != dy["sizes_mm"]:
        hard.append(("size_differs", f"Different sizes: {' x '.join(f'{v:g}' for v in dx['sizes_mm'])} mm and {' x '.join(f'{v:g}' for v in dy['sizes_mm'])} mm."))
    for key, code, label, unit in (
        ("length_mm", "size_differs", "lengths", "mm"),
        ("power_w", "power_differs", "power ratings", "W"),
        ("voltage_v", "voltage_differs", "voltages", "V"),
        ("current_a", "current_differs", "current ratings", "A"),
    ):
        if _disjoint(dx.get(key, []), dy.get(key, [])):
            hard.append((code, f"Different {label}: {_fmt(dx[key], unit)} and {_fmt(dy[key], unit)}."))
    if dx.get("poles") and dy.get("poles") and dx["poles"] != dy["poles"]:
        hard.append(("poles_differ", f"Different number of poles: {dx['poles']} and {dy['poles']}."))
    # Pack and container sizes (mass, volume) never split a product: an 18 kg
    # pail and a 400 g cartridge of the same grease are the same product.

    # Short codes (S2 vs S3, S1P vs S3) only when both names are in Latin
    # letters: Arabic names spell them differently.
    if "arabic" not in (x.get("script"), y.get("script")):
        parts = {px, py}
        cx_codes = set(x.get("codes", [])) - parts
        cy_codes = set(y.get("codes", [])) - parts
        if _disjoint(cx_codes, cy_codes):
            hard.append(("code_differs", f"Different model or class codes: {'/'.join(sorted(cx_codes)).upper()} and {'/'.join(sorted(cy_codes)).upper()}."))

    if _disjoint(x.get("numbers", []), y.get("numbers", [])):
        hard.append(("number_differs", f"Different grade, series or rating numbers: {'/'.join(x['numbers'])} and {'/'.join(y['numbers'])}."))
    return hard, soft


_SPEC_NAMES = {
    "thread": "thread", "length_mm": "length", "sizes_mm": "size", "power_w": "power",
    "voltage_v": "voltage", "current_a": "current rating", "poles": "number of poles", "material": "material", "colour": "colour",
}


def _spec_agreement(x: dict, y: dict) -> list[str]:
    """Specifications both rows state and agree on. Used when there is no part
    number: a hex bolt M8 x 25 A2 is the same item however the name is written."""
    agree = []
    dx, dy = x.get("dims", {}), y.get("dims", {})
    for key in ("thread", "length_mm", "sizes_mm", "power_w", "voltage_v", "current_a", "poles"):
        if dx.get(key) and dx.get(key) == dy.get(key):
            agree.append(key)
    if x.get("materials") and x.get("materials") == y.get("materials"):
        agree.append("material")
    if x.get("colours") and x.get("colours") == y.get("colours"):
        agree.append("colour")
    return agree


def compare(x: Item, y: Item, fx: _Features | None = None, fy: _Features | None = None) -> Pair:
    a, b = sorted((x, y), key=lambda i: i.row)
    nx, ny = a.norm, b.norm
    score = name_similarity(fx or _features(x), fy or _features(y))
    parts_match = same_part(nx.get("part_base"), ny.get("part_base"))

    hard, soft = _conflicts(nx, ny)
    if hard:
        code, detail = hard[0]
        # A look-alike is a near miss: the same part number, or alike names with
        # one single difference. An M6 x 50 and an M8 x 30 bolt differ twice.
        near_miss = parts_match or (score >= LOOKALIKE and len({c for c, _ in hard}) == 1)
        return Pair(a.row, b.row, "different", code, detail, score, lookalike=near_miss, hard=True)

    brand = nx.get("brand") or ny.get("brand")
    both_brands = bool(nx.get("brand")) and bool(ny.get("brand"))
    variants = [v.upper() for v in nx.get("variants", [])]
    types_agree = bool(set(nx.get("types", [])) & set(ny.get("types", [])))
    cross_script = nx.get("script") != ny.get("script")
    types_clash_free = types_agree or not (nx.get("types") and ny.get("types"))

    def same(confidence: str, code: str, detail: str, source: str = "rule") -> Pair:
        return Pair(a.row, b.row, "same", code, detail, score, confidence=confidence, source=source)

    def unsure(code: str, detail: str) -> Pair:
        return Pair(a.row, b.row, "unsure", code, detail, score)

    if parts_match and not soft:
        part = max(nx["part_base"], ny["part_base"], key=len).upper()
        strong_part = sum(ch.isdigit() for ch in part) >= 4
        label = f"{part}-{'/'.join(variants)}" if variants else part
        if variants and both_brands:
            return same("high", "same_brand_part_variant", f"Same brand ({brand.upper()}), same part number and variant ({label}).")
        if variants:
            return same("medium", "same_part_variant", f"Same part number and variant ({label}). {'One line has no brand' if brand else 'No brand on either line'}, so please confirm.")
        if both_brands and score >= SUPPORT:
            return same("high", "same_brand_part", f"Same brand ({brand.upper()}) and part number ({part}), and the names match.", source="text")
        if both_brands and strong_part and types_clash_free:
            return same("medium", "same_brand_long_part", f"Same brand ({brand.upper()}) and part number ({part}), though the names are worded differently.")
        if both_brands and types_agree and cross_script:
            return same("medium", "same_brand_part_language", f"Same brand ({brand.upper()}), part number ({part}) and kind of product; the names are in different languages, so please confirm.")
        if not both_brands and score >= NAMES_UNSURE:
            return same("medium", "same_part_names", f"Same part number ({part}) and similar names. {'One line has no brand' if brand else 'No brand on either line'}, so please confirm.", source="text")
        return unsure("same_part_weak", f"Same part number ({part}), but the names don't clearly describe the same product.")

    if parts_match or "part_partial" in soft:
        return unsure(soft[0] if soft else "same_part_weak", "Close match, but a detail is missing on one line (variant or full part number).")

    numbers_agree = bool(nx.get("numbers")) and nx.get("numbers") == ny.get("numbers")
    if types_agree and numbers_agree and (
        (both_brands and (score >= 0.7 or (cross_script and score >= 0.2)))
        or (not nx.get("brand") and not ny.get("brand") and score >= 0.35 and not cross_script)
    ):
        grade = "/".join(nx["numbers"])
        who = f"Same brand ({brand.upper()}), " if both_brands else "Same "
        return same("medium", "same_type_grade", f"{who}kind of product and size or grade ({grade}); names are {round(score * 100)}% alike.", source="text")

    agree = _spec_agreement(nx, ny)
    numeric = set(agree) & {"thread", "length_mm", "sizes_mm", "power_w", "voltage_v", "current_a"}
    if types_agree and numeric and (len(agree) >= 2 or score >= SUPPORT):
        kind = "/".join(sorted(set(nx["types"]) & set(ny["types"])))
        names = [_SPEC_NAMES[a] for a in agree]
        spec = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        return same("medium", "same_spec", f"Same kind of product ({kind}) with the same {spec}. No part number to confirm.")

    if cross_script and types_agree and (both_brands or numbers_agree or agree):
        return unsure("other_language", "Same kind of product described in two languages; not enough detail to be sure.")

    if types_agree and (numeric or numbers_agree) and score >= 0.25:
        return unsure("same_spec_weak", "Same kind of product and the same size or rating, but the names differ; worth a check.")

    if score >= NAMES_SAME and not cross_script:
        return same("medium", "similar_names", f"Names are {round(score * 100)}% alike and nothing contradicts them. No part number to confirm.", source="text")
    if score >= NAMES_UNSURE:
        return unsure("similar_names", f"Names are {round(score * 100)}% alike; not enough detail to be sure.")
    return Pair(a.row, b.row, "different", "names_differ", "Names are not alike.", score)


# ---------------------------------------------------------------- candidates

def _part_key(part: str) -> str:
    digits = "".join(ch for ch in part if ch.isdigit())
    return digits if len(digits) >= 3 else part


def _block_keys(norm: dict) -> list[str]:
    """Rows sharing any of these keys are compared all-to-all: the same part
    number, the same thread and length, rating, or kind of product and grade."""
    keys = []
    if norm.get("part_base"):
        keys.append("part:" + _part_key(norm["part_base"]))
    dims = norm.get("dims", {})
    if dims.get("thread"):
        keys.append(f"thread:{dims['thread']}:{dims.get('length_mm', [''])[0]}")
    for spec in ("sizes_mm", "power_w", "current_a"):
        if dims.get(spec):
            keys.append(f"{spec}:{dims[spec]}")
    if norm.get("types") and norm.get("numbers"):
        keys.append(f"grade:{'/'.join(norm['types'])}:{'/'.join(norm['numbers'])}")
    return keys


def candidate_pairs(items: list[Item], features: list[_Features]) -> set[tuple[int, int]]:
    """Index pairs worth comparing. Same part-number block, all-to-all (capped);
    otherwise the rows sharing the most rare words."""
    pairs: set[tuple[int, int]] = set()

    blocks: dict[str, list[int]] = defaultdict(list)
    for i, item in enumerate(items):
        for key in _block_keys(item.norm):
            blocks[key].append(i)
    for members in blocks.values():
        if len(members) > MAX_BLOCK:
            by_brand: dict[str | None, list[int]] = defaultdict(list)
            for i in members:
                by_brand[items[i].norm.get("brand")].append(i)
            groups = [m[:MAX_BLOCK] for m in by_brand.values()]
        else:
            groups = [members]
        for group in groups:
            for p in range(len(group)):
                for q in range(p + 1, len(group)):
                    pairs.add((group[p], group[q]))

    # Exact repeats (same brand and name) are chained, not compared all-to-all,
    # so a thousand copies of one line cost a thousand comparisons.
    exact: dict[tuple, list[int]] = defaultdict(list)
    for i, item in enumerate(items):
        exact[(item.norm.get("brand"), item.norm.get("text"))].append(i)
    for members in exact.values():
        pairs.update(pairwise(members))

    df = Counter(t for f in features for t in f.tokens)
    rare_limit = max(25, len(items) // 100)
    index: dict[str, list[int]] = defaultdict(list)
    for i, f in enumerate(features):
        for t in f.tokens:
            if df[t] <= rare_limit and df[t] > 1:
                index[t].append(i)
    for i, f in enumerate(features):
        shared: Counter[int] = Counter()
        for t in f.tokens:
            for j in index.get(t, ()):
                if j != i:
                    shared[j] += 1
        for j, _count in shared.most_common(NEIGHBOURS):
            pairs.add((min(i, j), max(i, j)))
    return pairs


# ---------------------------------------------------------------- grouping

class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        self.parent[self.find(x)] = self.find(y)


def _components(nodes: Iterable[int], edges: Iterable[tuple[int, int]]) -> list[list[int]]:
    uf = _UnionFind()
    for n in nodes:
        uf.find(n)
    for x, y in edges:
        uf.union(x, y)
    out: dict[int, list[int]] = defaultdict(list)
    for n in nodes:
        out[uf.find(n)].append(n)
    return [sorted(c) for c in out.values()]


def _edge_strength(p: Pair) -> tuple[int, float]:
    return ({"reviewed": 3, "high": 2, "medium": 1}.get(p.confidence or "", 0), p.score)


def _signature(norm: dict) -> tuple:
    """Everything _conflicts() reads. Rows with equal signatures can never
    conflict, so conflicts are checked once per pair of signatures."""
    dims = norm.get("dims", {})
    return (
        norm.get("brand"), norm.get("part_base"), tuple(norm.get("variants", [])), tuple(norm.get("variant_classes", [])),
        tuple(norm.get("types", [])), tuple(norm.get("colours", [])), tuple(norm.get("materials", [])),
        tuple(norm.get("codes", [])), tuple(norm.get("numbers", [])), norm.get("script") == "arabic",
        tuple(sorted((k, str(v)) for k, v in dims.items() if k not in ("mass_g", "volume_ml"))),
    )


def _build_groups(items: list[Item], by_row: dict[int, int], same_edges: dict[tuple[int, int], Pair], forbidden: set[tuple[int, int]]) -> list[Group]:
    """Join "same" pairs strongest first. Two groups are joined only if no
    member of one conflicts with a member of the other, so A~B and B~C never
    put A and C together when they are different products; the weakest link
    is the one left out."""
    uf = _UnionFind()
    sig_of = {row: _signature(items[by_row[row]].norm) for pair in same_edges for row in pair}
    norm_of_sig = {sig: items[by_row[row]].norm for row, sig in sig_of.items()}
    sigs: dict[int, set[tuple]] = {row: {sig} for row, sig in sig_of.items()}
    members: dict[int, list[int]] = {row: [row] for row in sig_of}
    edges: dict[int, list[Pair]] = {row: [] for row in sig_of}
    conflict_cache: dict[tuple, bool] = {}

    def conflict(s1: tuple, s2: tuple) -> bool:
        key = (s1, s2) if repr(s1) <= repr(s2) else (s2, s1)
        if key not in conflict_cache:
            conflict_cache[key] = bool(_conflicts(norm_of_sig[s1], norm_of_sig[s2])[0])
        return conflict_cache[key]

    for pair in sorted(same_edges.values(), key=_edge_strength, reverse=True):
        ra, rb = uf.find(pair.a), uf.find(pair.b)
        if ra == rb:
            edges[ra].append(pair)
            continue
        # A person's "same" overrides the rules; nothing else does.
        if pair.confidence != "reviewed" and any(conflict(x, y) for x in sigs[ra] for y in sigs[rb]):
            continue
        small, big = (ra, rb) if len(members[ra]) < len(members[rb]) else (rb, ra)
        if forbidden and any((min(r, o), max(r, o)) in forbidden for r in members[small] for o in members[big]):
            continue
        uf.parent[small] = big
        members[big] += members.pop(small)
        sigs[big] |= sigs.pop(small)
        edges[big] += edges.pop(small) + [pair]

    groups = []
    for root, rows in members.items():
        if len(rows) < 2:
            continue
        inside = edges[root]
        levels = {p.confidence for p in inside}
        confidence = "reviewed" if levels == {"reviewed"} else "high" if levels <= {"high", "reviewed"} else "medium"
        reasons = list(dict.fromkeys(p.detail for p in sorted(inside, key=_edge_strength, reverse=True)))[:3]
        rows = sorted(rows)
        groups.append(Group(rows=rows, master=choose_master([items[by_row[r]] for r in rows]).row, confidence=confidence, reasons=reasons))
    groups.sort(key=lambda g: g.rows[0])
    return groups


def choose_master(items: list[Item]) -> Item:
    """Most complete row, then most stock in single units (pack sizes applied),
    then has an item code, then first."""
    def key(item: Item) -> tuple:
        n = item.norm
        complete = sum(1 for v in (n.get("brand"), n.get("part_base"), n.get("unit_cost"), n.get("stock"), item.code) if v not in (None, ""))
        return (-complete, -(n.get("stock") or 0) * (n.get("pack") or 1), 0 if item.code else 1, item.row)

    return min(items, key=key)


def _one_per_cluster_pair(pairs: list[Pair], groups: list[Group]) -> list[Pair]:
    """Keep the first pair (most alike) between any two groups, so a group of
    five SKF rows next to a group of two FAG rows is one look-alike, not ten.
    Pairs inside one group are dropped."""
    cluster = {r: ("g", k) for k, g in enumerate(groups) for r in g.rows}
    seen: set[tuple] = set()
    out: list[Pair] = []
    for p in pairs:
        ca, cb = cluster.get(p.a, ("r", p.a)), cluster.get(p.b, ("r", p.b))
        if ca == cb:
            continue
        key = (min(ca, cb), max(ca, cb))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


# ---------------------------------------------------------------- the whole run

def analyse(
    items: list[Item],
    reviewer: Reviewer | None = None,
    max_reviews: int = 0,
    force_same: Iterable[tuple[int, int]] = (),
    forbid: Iterable[tuple[int, int]] = (),
) -> Analysis:
    """force_same and forbid are pairs of row numbers people have settled
    ("same" / "different"); they win over the rules and the AI."""
    started = time.monotonic()
    features = [_features(i) for i in items]
    by_row = {item.row: k for k, item in enumerate(items)}
    candidates = candidate_pairs(items, features)

    results: dict[tuple[int, int], Pair] = {}
    for i, j in candidates:
        p = compare(items[i], items[j], features[i], features[j])
        results[(p.a, p.b)] = p
    compared_at = time.monotonic()

    rows_present = set(by_row)
    forbid = {(min(a, b), max(a, b)) for a, b in forbid if a in rows_present and b in rows_present and a != b}
    force_same = {(min(a, b), max(a, b)) for a, b in force_same if a in rows_present and b in rows_present and a != b} - forbid
    for key in forbid:
        p = results.get(key) or compare(items[by_row[key[0]]], items[by_row[key[1]]])
        p.verdict, p.reason, p.detail, p.source, p.hard, p.lookalike = "different", "reviewed_different", "Marked as different by your team.", "review", True, False
        results[key] = p
    for key in force_same:
        p = results.get(key) or compare(items[by_row[key[0]]], items[by_row[key[1]]])
        p.verdict, p.reason, p.detail, p.source, p.confidence = "same", "reviewed_same", "Confirmed as the same item by your team.", "review", "reviewed"
        results[key] = p

    reviewed = 0
    if reviewer is not None and max_reviews > 0:
        unsure = sorted((p for p in results.values() if p.verdict == "unsure"), key=lambda p: -p.score)[:max_reviews]
        answers = reviewer.review([(items[by_row[p.a]], items[by_row[p.b]]) for p in unsure]) if unsure else []
        for p, (verdict, reason) in zip(unsure, answers, strict=True):
            if verdict == "same":
                p.verdict, p.confidence, p.source, p.reason, p.detail = "same", "medium", "ai", "ai_same", reason
            elif verdict == "different":
                p.verdict, p.source, p.reason, p.detail, p.hard = "different", "ai", "ai_different", reason, True
                part_a = items[by_row[p.a]].norm.get("part_base")
                p.lookalike = p.score >= LOOKALIKE or (part_a is not None and part_a == items[by_row[p.b]].norm.get("part_base"))
            reviewed += 1

    same_edges = {k: p for k, p in results.items() if p.verdict == "same"}
    forbidden = {k for k, p in results.items() if p.source in ("ai", "review") and p.verdict == "different"}
    groups = _build_groups(items, by_row, same_edges, forbidden)

    lookalikes = _one_per_cluster_pair(
        sorted((p for p in results.values() if p.verdict == "different" and p.lookalike), key=lambda p: (-p.score, p.a, p.b)), groups
    )
    unsure = _one_per_cluster_pair(
        sorted((p for p in results.values() if p.verdict == "unsure"), key=lambda p: (-p.score, p.a, p.b)), groups
    )[:MAX_UNSURE]

    return Analysis(
        groups=groups,
        lookalikes=lookalikes,
        unsure=unsure,
        stats={
            "items": len(items),
            "pairs_compared": len(results),
            "groups": len(groups),
            "duplicate_lines": sum(len(g.rows) - 1 for g in groups),
            "lookalikes": len(lookalikes),
            "needs_review": len(unsure),
            "ai_reviewed": reviewed,
            "ms_compare": int((compared_at - started) * 1000),
            "ms_total": int((time.monotonic() - started) * 1000),
        },
    )
