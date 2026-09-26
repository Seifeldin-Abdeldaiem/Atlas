"""Measure matching against a labelled catalogue: rows that share a label
(for example a true_product_id column) are the real duplicates.

Pairwise scores: every pair of rows is either in the same Atlas group or not,
and either shares a label or not.
    precision = grouped pairs that truly match / all grouped pairs
    recall    = truly matching pairs that were grouped / all truly matching pairs
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .match import Analysis


@dataclass
class Score:
    precision: float
    recall: float
    true_pairs: int
    grouped_pairs: int
    correct_pairs: int
    variant_merges: int
    needs_review_share: float
    wrong: list[tuple[int, int]]
    missed: list[tuple[int, int]]

    def line(self) -> str:
        return (
            f"precision {self.precision:.1%} ({self.correct_pairs}/{self.grouped_pairs})  "
            f"recall {self.recall:.1%} ({self.correct_pairs}/{self.true_pairs})  "
            f"variant merges {self.variant_merges}  needs review {self.needs_review_share:.1%}"
        )


def pairs_of(groups: list[list[int]]) -> set[tuple[int, int]]:
    return {(min(x, y), max(x, y)) for g in groups for x, y in combinations(g, 2)}


def score(analysis: Analysis, labels: dict[int, str], norms: dict[int, dict] | None = None) -> Score:
    by_label: dict[str, list[int]] = {}
    for row, label in labels.items():
        if label:
            by_label.setdefault(label, []).append(row)
    truth = pairs_of(list(by_label.values()))
    predicted = pairs_of([g.rows for g in analysis.groups])
    correct = truth & predicted

    merges = 0
    if norms:
        for x, y in predicted:
            if norms[x].get("variant_classes") != norms[y].get("variant_classes") and norms[x].get("part_base") == norms[y].get("part_base"):
                merges += 1
    in_review = {r for p in analysis.unsure for r in (p.a, p.b)}
    return Score(
        precision=len(correct) / len(predicted) if predicted else 1.0,
        recall=len(correct) / len(truth) if truth else 1.0,
        true_pairs=len(truth),
        grouped_pairs=len(predicted),
        correct_pairs=len(correct),
        variant_merges=merges,
        needs_review_share=len(in_review) / len(labels) if labels else 0.0,
        wrong=sorted(predicted - truth),
        missed=sorted(truth - predicted),
    )
