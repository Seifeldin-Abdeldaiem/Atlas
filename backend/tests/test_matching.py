"""Milestone 2: matching without AI.

The accuracy tests print precision and recall for every labelled catalogue in
tests/fixtures/catalogue (run pytest -s to see them) and fail below the floor.
Precision is held high on purpose: a wrong merge costs a customer more than a
missed one, which stays visible under "needs review".
"""

from __future__ import annotations

import pathlib
import time

import pytest

from atlas.catalogue.evaluate import score
from atlas.catalogue.match import Item, analyse, choose_master, compare, same_part
from atlas.catalogue.normalize import normalise_row, normalise_table
from atlas.ingest import ingest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "catalogue"


def item(row: int, name: str, **columns: str) -> Item:
    mapping = {"item_name": "name", **{k: k for k in columns}}
    return Item(row, normalise_row({"name": name, **columns}, mapping), code=columns.get("item_code"), name=name)


def verdict(x: str, y: str, **kw) -> tuple[str, str]:
    p = compare(item(1, x, **kw), item(2, y, **kw))
    return p.verdict, p.reason


# ---------- Rules ----------


@pytest.mark.parametrize(
    ("x", "y"),
    [
        ("SKF 6205-2RS Deep Groove Ball Bearing", "6205 2RS SKF bearing"),
        ("SKF 6205-2RS Deep Groove Ball Bearing", "رولمان بلي ٦٢٠٥ ٢ار اس اس كي اف"),
        ("SKF 6205-2RS bearing", "BRG 62052RS skf"),
        ("Hex bolt M8x25 A2 SS", "M8 X 25MM HEX HD BOLT STAINLESS A2"),
        ("Shell Gadus S2 V220 2 Grease 18 KG Pail", "Shell Gadus S2 V220 2 grease 400gm cartridge"),
        ("LED flood light 100W IP65", "LED floodlight 100 W 220V IP65"),
        ("MCB 16A single pole", "Circuit breaker MCB 16A 1P"),
    ],
)
def test_same_item_written_differently(x, y):
    assert verdict(x, y)[0] == "same"


@pytest.mark.parametrize(
    ("x", "y", "reason"),
    [
        ("SKF 6205-2RS bearing", "SKF 6205-ZZ bearing", "seal_differs"),
        ("SKF 6205-2RS bearing", "SKF 6205-2RS/C3 bearing", "clearance_differs"),
        ("SKF 6205-2RS bearing", "SKF 6205-2RS1 bearing", "variant_spelling"),
        ("SKF 6205-2RS bearing", "FAG 6205-2RS bearing", "brand_equivalent"),
        ("SKF 6205-2RS bearing", "SKF 6206-2RS bearing", "part_differs"),
        ("Shell Gadus S2 V220 2 grease", "Shell Gadus S2 V220 3 grease", "number_differs"),
        ("شحم شل جادوس في٢٢٠ ٢", "زيت تروس شل ٢٢٠", "type_differs"),
        ("3M safety helmet white H-700", "3M safety helmet yellow H-700", "colour_differs"),
        ("LED flood light 100W IP65", "LED flood light 150W IP65", "power_differs"),
        ("Hex bolt M8x25 A2", "Hex bolt M8x25 A4", "material_differs"),
        ("Hex bolt M8x25 A2", "Hex bolt M8x30 A2", "size_differs"),
        ("MCB 16A single pole", "MCB 20A single pole", "current_differs"),
        ("MCB 16A single pole", "MCB 16A double pole", "poles_differ"),
        ("Safety shoes S3 size 42", "Safety shoes S1P size 42", "code_differs"),
    ],
)
def test_look_alikes_are_kept_apart(x, y, reason):
    p = compare(item(1, x), item(2, y))
    assert (p.verdict, p.reason, p.hard) == ("different", reason, True)
    assert p.detail and "{" not in p.detail


def test_doubtful_pairs_stay_unsure():
    assert verdict("SKF 6205 bearing", "SKF 6205-2RS bearing")[0] == "unsure"  # seal not written on one line
    assert verdict("Gloves nitrile sz 9", "قفاز نيتريل مقاس ٩")[0] == "unsure"  # two languages, no brand


def test_part_prefixes():
    assert same_part("h700", "700") and same_part("v220", "220")
    assert not same_part("6205", "6206") and not same_part("v22", "22")


def test_column_brand_and_part_are_used():
    p = compare(item(1, "Deep groove ball bearing", brand="SKF", part_number="6205-2RS"), item(2, "bearing 6205 2rs", brand="skf"))
    assert (p.verdict, p.confidence) == ("same", "high")


# ---------- Grouping ----------


def test_chains_never_join_conflicting_rows():
    # B looks like both A (2RS) and C (ZZ) because it names no seal;
    # A and C must still end up apart.
    rows = [
        item(2, "SKF 6205-2RS deep groove bearing", brand="SKF"),
        item(3, "SKF 6205-2RS deep groove ball bearing", brand="SKF"),
        item(4, "SKF 6205-ZZ deep groove ball bearing", brand="SKF"),
        item(5, "SKF 6205-ZZ deep groove bearing", brand="SKF"),
    ]
    result = analyse(rows)
    assert [g.rows for g in result.groups] == [[2, 3], [4, 5]]
    assert [(p.a, p.b) for p in result.lookalikes] == [(2, 4)] or len(result.lookalikes) == 1


def test_master_is_the_most_complete_row():
    rows = [
        Item(2, {"brand": "skf", "part_base": "6205"}, code=None),
        Item(3, {"brand": "skf", "part_base": "6205", "stock": 4.0, "unit_cost": 4.2}, code="BRG-1"),
        Item(4, {"brand": "skf", "part_base": "6205", "stock": 9.0, "unit_cost": 4.1}, code="BRG-2"),
    ]
    assert choose_master(rows).row == 4


def test_look_alikes_are_listed_once_per_pair_of_groups():
    wordings = ["{} 6205-2RS bearing", "{} 6205 2RS ball bearing", "Bearing 6205-2RS ({})", "{} 6205-2RS deep groove"]
    rows = [item(n, w.format("SKF")) for n, w in enumerate(wordings, start=2)] + [item(n, w.format("FAG")) for n, w in enumerate(wordings[:3], start=6)]
    result = analyse(rows)
    assert len(result.groups) == 2
    assert len([p for p in result.lookalikes if p.reason == "brand_equivalent"]) == 1


def test_reviewer_settles_unsure_pairs():
    class Always:
        def __init__(self, answer):
            self.answer, self.seen = answer, 0

        def review(self, pairs):
            self.seen += len(pairs)
            return [(self.answer, "Checked by the reviewer.") for _ in pairs]

    rows = [item(2, "SKF 6205 bearing"), item(3, "SKF 6205-2RS bearing")]
    assert analyse(rows).groups == []
    yes = Always("same")
    result = analyse(rows, reviewer=yes, max_reviews=10)
    assert yes.seen == 1 and [g.rows for g in result.groups] == [[2, 3]] and result.groups[0].reasons == ["Checked by the reviewer."]
    no = analyse(rows, reviewer=Always("different"), max_reviews=10)
    assert no.groups == [] and no.unsure == [] and no.lookalikes[0].reason == "ai_different"
    capped = Always("same")
    analyse(rows, reviewer=capped, max_reviews=0)
    assert capped.seen == 0


# ---------- Accuracy on labelled catalogues ----------


def evaluate(path: pathlib.Path):
    result = ingest(path.read_bytes())
    mapping = result.mapping
    norms = normalise_table(result.table, mapping)
    rows = {r.row_number: r for r in result.table.rows}
    items = [Item(n, norms[n], rows[n].values.get(mapping.get("item_code") or ""), rows[n].values[mapping["item_name"]]) for n in norms]
    analysis = analyse(items)
    labels = {n: rows[n].values["true_product_id"] for n in norms}
    assert "true_product_id" not in mapping.values(), "the answer key must never be used for matching"
    return score(analysis, labels, norms)


# Floors sit a little under today's results so a regression fails loudly.
# blind.csv was never used for tuning.
@pytest.mark.parametrize(
    ("name", "min_precision", "min_recall"),
    [("bearings.csv", 0.98, 0.95), ("fasteners.csv", 0.98, 0.95), ("stores.csv", 0.98, 0.85), ("blind.csv", 0.95, 0.85)],
)
def test_accuracy(name, min_precision, min_recall):
    s = evaluate(FIXTURES / name)
    print(f"\n{name}: {s.line()}")
    assert s.variant_merges == 0
    assert s.precision >= min_precision, s.wrong[:10]
    assert s.recall >= min_recall, s.missed[:10]


def test_twenty_thousand_rows_in_reasonable_time():
    names = [line.split(",")[1] for f in ("stores.csv", "blind.csv") for line in (FIXTURES / f).read_text(encoding="utf-8").splitlines()[1:]]
    rows = [item(i + 2, names[i % len(names)].replace("M8", f"M{3 + i % 17}")) for i in range(20_000)]
    started = time.monotonic()
    result = analyse(rows)
    elapsed = time.monotonic() - started
    print(f"\n20,000 rows analysed in {elapsed:.1f}s, {result.stats['pairs_compared']:,} pairs compared")
    assert elapsed < 120


# The public landing page shows these rows and Atlas's answers as "real results"
# (web/components/landing/sample.ts). Keep the two in step.
LANDING_EXAMPLE = [
    ("BRG-0142", "SKF 6205-2RS Deep Groove Ball Bearing", "SKF"),
    ("BRG-0388", "6205 2RS SKF bearing", "SKF"),
    ("BRG-1177", "Bearing 6205-2RS (SKF)", ""),
    ("BRG-2051", "رولمان بلي 6205 2RS اس كي اف", ""),
    ("BRG-0143", "SKF 6205-ZZ Deep Groove Ball Bearing", "SKF"),
    ("BRG-0412", "SKF 6205-2RS/C3", "SKF"),
    ("FST-2210", "Hex bolt M8x25 A2 SS", ""),
    ("FST-3019", "M8 X 25MM HEX HD BOLT STAINLESS", ""),
    ("FST-2208", "Hex bolt M8x20 A2 SS", ""),
    ("CHM-0071", "Loctite 243 threadlocker 50ml", "Loctite"),
    ("CHM-0460", "Threadlock medium strength blue 243 50 ml", ""),
]


def test_landing_example():
    items = [item(i, name, item_code=code, brand=brand) for i, (code, name, brand) in enumerate(LANDING_EXAMPLE)]
    code = {it.row: it.code for it in items}
    result = analyse(items)

    groups = {frozenset(code[r] for r in g.rows): (g.confidence, g.reasons[0]) for g in result.groups}
    assert groups == {
        frozenset({"BRG-0142", "BRG-0388", "BRG-1177", "BRG-2051"}): ("high", "Same brand (SKF), same part number and variant (6205-2RS)."),
        frozenset({"FST-2210", "FST-3019"}): ("medium", "Same kind of product (bolt) with the same thread and length. No part number to confirm."),
    }
    lookalikes = {frozenset((code[p.a], code[p.b])): p.detail for p in result.lookalikes}
    assert lookalikes[frozenset({"BRG-0142", "BRG-0143"})] == "Different seal type: 2RS has rubber seals on both sides, ZZ has metal shields on both sides."
    assert lookalikes[frozenset({"BRG-0388", "BRG-0412"})] == "Only one has C3 (larger) internal clearance (C3)."
    assert lookalikes[frozenset({"FST-2210", "FST-2208"})] == "Different lengths: 25 mm and 20 mm."
    assert [frozenset((code[p.a], code[p.b])) for p in result.unsure] == [frozenset({"CHM-0071", "CHM-0460"})]
