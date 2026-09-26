"""Measure AI review on a labelled catalogue: accuracy with and without AI,
tokens used and an approximate cost per 1,000 rows. Calls the real API, so it
costs money and asks before it starts.

    cd backend
    ANTHROPIC_API_KEY=... .venv/bin/python -m atlas.catalogue.ai_check tests/fixtures/catalogue/blind.csv

The file needs a true_product_id column (rows sharing it are duplicates).
Run it before changing the prompt, the model or the thresholds.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

from ..ingest import ingest
from .ai_review import DEFAULT_MODEL, ClaudeReviewer
from .evaluate import score
from .match import Item, analyse
from .normalize import normalise_table

# Approximate list prices in USD per million tokens (input, output), for the
# estimate only. Check current pricing before quoting a customer.
PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=pathlib.Path)
    parser.add_argument("--model", default=os.environ.get("AI_REVIEW_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-pairs", type=int, default=2000)
    parser.add_argument("--label-column", default="true_product_id")
    parser.add_argument("--yes", action="store_true", help="don't ask before calling the API")
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first. Nothing was sent.", file=sys.stderr)
        return 2

    result = ingest(args.file.read_bytes())
    norms = normalise_table(result.table, result.mapping)
    rows = {r.row_number: r for r in result.table.rows}
    labels = {n: rows[n].values.get(args.label_column, "") for n in norms}
    if not any(labels.values()):
        print(f"No {args.label_column} column found.", file=sys.stderr)
        return 2
    items = [Item(n, norms[n]) for n in norms]

    without = analyse(items)
    before = score(without, labels, norms)
    print(f"{args.file.name}: {len(items)} rows, {len(without.unsure)} pairs need review")
    print(f"  rules only:   {before.line()}")
    if not without.unsure:
        print("  nothing for the AI to review.")
        return 0
    if not args.yes and input(f"Send up to {min(len(without.unsure), args.max_pairs)} pairs to {args.model}? [y/N] ").strip().lower() != "y":
        print("Stopped. Nothing was sent.")
        return 1

    import anthropic

    reviewer = ClaudeReviewer(anthropic.Anthropic(max_retries=3), model=args.model)
    with_ai = analyse(items, reviewer=reviewer, max_reviews=args.max_pairs)
    after = score(with_ai, labels, norms)
    usage = reviewer.stats
    print(f"  with AI:      {after.line()}")
    print(f"  requests {usage.requests}, input tokens {usage.input_tokens:,}, output tokens {usage.output_tokens:,}, failed batches {usage.failed_batches}")
    if usage.stopped:
        print(f"  AI review stopped early: {usage.stopped}")
    price = PRICES.get(args.model)
    if price:
        cost = usage.input_tokens / 1e6 * price[0] + usage.output_tokens / 1e6 * price[1]
        print(f"  approximate cost ${cost:.4f}, about ${cost / len(items) * 1000:.4f} per 1,000 rows (list prices, check before quoting)")
    for x, y in after.wrong[:10]:
        print(f"  wrongly merged: row {x} and row {y}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
