"""People review the results (milestone 5).

Group actions:  approve     the group is right (confidence becomes "reviewed")
                reject      these lines are not duplicates (the group goes)
                set_master  keep this line
                remove_row  this line doesn't belong in the group
Pair actions:   same        merge the two lines (into a group, joining groups if needed)
                different   they are different (the pair leaves the lists)

Each action is recorded in review_decisions, applied to the stored results at
once, and re-applied by analysis.run() on every later run. Figures and the
headline summary are recalculated, and any export (now out of date) is dropped.
"""

from __future__ import annotations

from itertools import combinations
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from . import datasets
from .catalogue.match import Group, Item, choose_master
from .catalogue.value import GroupFigures, figures, headline, standard_name
from .errors import AtlasError
from .export import discard

GROUP_ACTIONS = ("approve", "reject", "set_master", "remove_row")
PAIR_ACTIONS = ("same", "different")


# ---------------------------------------------------------------- decisions for a re-run

def load_decisions(conn: psycopg.Connection, dataset_id: UUID) -> dict:
    """Constraints for analyse() plus what to re-apply after grouping, in the
    order people made them (a later decision wins)."""
    force_same: set[tuple[int, int]] = set()
    forbid: set[tuple[int, int]] = set()
    approve: list[set[int]] = []
    masters: list[int] = []
    for d in conn.execute("SELECT action, rows FROM review_decisions WHERE dataset_id = %s ORDER BY id", (dataset_id,)):
        rows = list(d["rows"])
        pairs = {(min(a, b), max(a, b)) for a, b in combinations(rows, 2)}
        if d["action"] == "same":
            force_same |= pairs
            forbid -= pairs
        elif d["action"] in ("different", "reject"):
            forbid |= pairs
            force_same -= pairs
        elif d["action"] == "remove_row":
            out = {(min(rows[0], r), max(rows[0], r)) for r in rows[1:]}
            forbid |= out
            force_same -= out
        elif d["action"] == "approve":
            approve.append(set(rows))
        elif d["action"] == "set_master":
            masters.append(rows[0])
    return {"force_same": force_same, "forbid": forbid, "approve": approve, "masters": masters}


def reapply(groups: list[Group], decisions: dict) -> None:
    """Approvals and chosen masters for groups that still exist."""
    for g in groups:
        members = set(g.rows)
        if any(rows == members for rows in decisions.get("approve", [])):
            g.confidence = "reviewed"
        chosen = [r for r in decisions.get("masters", []) if r in members]
        if chosen:
            g.master = chosen[-1]


# ---------------------------------------------------------------- applying actions now

def _record(conn: psycopg.Connection, org_id: UUID, dataset_id: UUID, action: str, rows: list[int], user_id: UUID | None) -> None:
    conn.execute(
        "INSERT INTO review_decisions (org_id, dataset_id, action, rows, user_id) VALUES (%s, %s, %s, %s, %s)",
        (org_id, dataset_id, action, rows, user_id),
    )
    datasets.audit(conn, org_id, user_id, f"review.{action}", dataset_id, rows=len(rows))


def _items(conn: psycopg.Connection, dataset: dict, rows: list[int]) -> tuple[dict[int, Item], dict[int, str | None]]:
    found = conn.execute(
        "SELECT row_number, original, norm FROM tasks WHERE dataset_id = %s AND row_number = ANY(%s)", (dataset["id"], rows)
    ).fetchall()
    mapping = dataset["mapping"]
    code_col, unit_col, name_col = mapping.get("item_code"), mapping.get("unit"), mapping.get("item_name")
    items = {
        r["row_number"]: Item(
            r["row_number"], r["norm"] or {}, code=(r["original"] or {}).get(code_col) if code_col else None, name=(r["original"] or {}).get(name_col) or ""
        )
        for r in found
    }
    units = {r["row_number"]: (r["original"] or {}).get(unit_col) for r in found} if unit_col else {}
    return items, units


def _money_ok(dataset: dict) -> bool:
    stock = ((dataset["analysis"] or {}).get("summary") or {}).get("stock") or {}
    return not stock.get("mixed_currencies")


def _write_group(conn: psycopg.Connection, dataset: dict, group_id: UUID, rows: list[int], master: int | None, confidence: str, reasons: list[str]) -> None:
    """Rewrite one group's members, master and figures."""
    items, units = _items(conn, dataset, rows)
    rows = sorted(r for r in rows if r in items)
    if len(rows) < 2:
        conn.execute("DELETE FROM match_groups WHERE id = %s", (group_id,))
        return
    master_row = master if master in rows else choose_master([items[r] for r in rows]).row
    f = figures(Group(rows, master_row, confidence, reasons), items, units, _money_ok(dataset))
    name = standard_name([items[r] for r in rows], items[master_row])
    conn.execute(
        """UPDATE match_groups SET master_row = %s, confidence = %s, reasons = %s, name_standard = %s, stock_total = %s,
                  stock_on_duplicates = %s, value_on_duplicates = %s, cost_low = %s, cost_high = %s WHERE id = %s""",
        (master_row, confidence, Jsonb(reasons), name, f.stock_total, f.stock_on_duplicates, f.value_on_duplicates, f.cost_low, f.cost_high, group_id),
    )
    conn.execute("DELETE FROM match_members WHERE group_id = %s", (group_id,))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO match_members (group_id, org_id, dataset_id, row_number, role) VALUES (%s, %s, %s, %s, %s)",
            [(group_id, dataset["org_id"], dataset["id"], r, "master" if r == master_row else "duplicate") for r in rows],
        )


def refresh_summary(conn: psycopg.Connection, dataset: dict) -> dict:
    """Recount the headline from the stored results after a change."""
    state = dict(dataset["analysis"] or {})
    summary = dict(state.get("summary") or {})
    counts = conn.execute(
        """SELECT (SELECT count(*) FROM match_groups WHERE dataset_id = %(d)s) AS groups,
                  (SELECT count(*) FROM match_members WHERE dataset_id = %(d)s) AS members,
                  (SELECT count(*) FROM match_pairs WHERE dataset_id = %(d)s AND kind = 'lookalike') AS lookalikes,
                  (SELECT count(*) FROM match_pairs WHERE dataset_id = %(d)s AND kind = 'review') AS review,
                  (SELECT count(*) FROM match_groups WHERE dataset_id = %(d)s AND confidence = 'reviewed') AS reviewed""",
        {"d": dataset["id"]},
    ).fetchone()
    summary.update(
        groups=counts["groups"], duplicate_lines=counts["members"] - counts["groups"], lookalikes=counts["lookalikes"],
        needs_review=counts["review"], groups_reviewed=counts["reviewed"],
    )
    old = summary.get("stock") or {}
    rows = conn.execute(
        "SELECT stock_total, stock_on_duplicates, value_on_duplicates, cost_low, cost_high FROM match_groups WHERE dataset_id = %s", (dataset["id"],)
    ).fetchall()
    as_figures = [
        GroupFigures(*(None if r[k] is None else float(r[k]) for k in ("stock_total", "stock_on_duplicates", "value_on_duplicates", "cost_low", "cost_high")))
        for r in rows
    ]
    if old:
        mixed = set(old.get("mixed_currencies") or [])
        summary["stock"] = headline(as_figures, old.get("currency"), old.get("has_stock", False), old.get("has_cost", False), mixed or ({old["currency"]} if old.get("currency") else set()))
    state["summary"] = summary
    conn.execute("UPDATE datasets SET analysis = %s, updated_at = now() WHERE id = %s", (Jsonb(state), dataset["id"]))
    discard(conn, dataset["id"])
    return summary


def _analysed(conn: psycopg.Connection, dataset_id: UUID) -> dict:
    dataset = datasets.get_dataset(conn, dataset_id)
    if dataset["status"] != "analysed":
        raise AtlasError("not_ready", status_code=409)
    return dataset


def group_action(conn: psycopg.Connection, org_id: UUID, user_id: UUID | None, dataset_id: UUID, label: str, action: str, row: int | None = None) -> dict:
    if action not in GROUP_ACTIONS:
        raise AtlasError("invalid_review", status_code=400)
    dataset = _analysed(conn, dataset_id)
    group = conn.execute("SELECT * FROM match_groups WHERE dataset_id = %s AND label = %s FOR UPDATE", (dataset_id, label)).fetchone()
    if group is None:
        raise AtlasError("not_found", status_code=404)
    rows = [m["row_number"] for m in conn.execute("SELECT row_number FROM match_members WHERE group_id = %s ORDER BY row_number", (group["id"],))]
    if action in ("set_master", "remove_row") and row not in rows:
        raise AtlasError("invalid_review", status_code=400)

    if action == "approve":
        _record(conn, org_id, dataset_id, "approve", rows, user_id)
        conn.execute("UPDATE match_groups SET confidence = 'reviewed' WHERE id = %s", (group["id"],))
    elif action == "reject":
        _record(conn, org_id, dataset_id, "reject", rows, user_id)
        conn.execute("DELETE FROM match_groups WHERE id = %s", (group["id"],))
    elif action == "set_master":
        _record(conn, org_id, dataset_id, "set_master", [row], user_id)
        _write_group(conn, dataset, group["id"], rows, row, group["confidence"], group["reasons"])
    else:  # remove_row
        _record(conn, org_id, dataset_id, "remove_row", [row, *[r for r in rows if r != row]], user_id)
        rest = [r for r in rows if r != row]
        _write_group(conn, dataset, group["id"], rest, group["master_row"] if group["master_row"] != row else None, group["confidence"], group["reasons"])
    return refresh_summary(conn, datasets.get_dataset(conn, dataset_id))


def pair_action(conn: psycopg.Connection, org_id: UUID, user_id: UUID | None, dataset_id: UUID, row_a: int, row_b: int, verdict: str) -> dict:
    if verdict not in PAIR_ACTIONS or row_a == row_b:
        raise AtlasError("invalid_review", status_code=400)
    dataset = _analysed(conn, dataset_id)
    a, b = sorted((row_a, row_b))
    exists = conn.execute(
        "SELECT count(*) AS n FROM tasks WHERE dataset_id = %s AND row_number = ANY(%s) AND norm IS NOT NULL", (dataset_id, [a, b])
    ).fetchone()["n"]
    if exists != 2:
        raise AtlasError("invalid_review", status_code=400)
    _record(conn, org_id, dataset_id, verdict, [a, b], user_id)
    conn.execute("DELETE FROM match_pairs WHERE dataset_id = %s AND row_a = %s AND row_b = %s", (dataset_id, a, b))
    if verdict == "same":
        found = conn.execute(
            """SELECT g.id, g.label, g.master_row, g.reasons, m.row_number FROM match_members m JOIN match_groups g ON g.id = m.group_id
                WHERE m.dataset_id = %s AND m.row_number = ANY(%s) ORDER BY g.label""",
            (dataset_id, [a, b]),
        ).fetchall()
        groups = {r["id"]: r for r in found}
        reason = "Confirmed as the same item by your team."
        if not groups:
            label = _next_label(conn, dataset_id)
            group_id = conn.execute(
                "INSERT INTO match_groups (org_id, dataset_id, label, confidence, master_row, reasons) VALUES (%s, %s, %s, 'reviewed', %s, %s) RETURNING id",
                (org_id, dataset_id, label, a, Jsonb([reason])),
            ).fetchone()["id"]
            _write_group(conn, dataset, group_id, [a, b], None, "reviewed", [reason])
        else:
            keep, *others = list(groups.values())
            rows = {r for r in (a, b)}
            for g in [keep, *others]:
                rows |= {m["row_number"] for m in conn.execute("SELECT row_number FROM match_members WHERE group_id = %s", (g["id"],))}
            for g in others:
                conn.execute("DELETE FROM match_groups WHERE id = %s", (g["id"],))
            reasons = list(dict.fromkeys([*keep["reasons"], reason]))[:3]
            _write_group(conn, dataset, keep["id"], sorted(rows), keep["master_row"], "reviewed", reasons)
    return refresh_summary(conn, datasets.get_dataset(conn, dataset_id))


def _next_label(conn: psycopg.Connection, dataset_id: UUID) -> str:
    row = conn.execute("SELECT max(substring(label from 3)::int) AS n FROM match_groups WHERE dataset_id = %s", (dataset_id,)).fetchone()
    return f"G-{(row['n'] or 0) + 1:04d}"
