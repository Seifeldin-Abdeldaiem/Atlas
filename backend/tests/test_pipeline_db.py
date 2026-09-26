"""End to end against a real, disposable Postgres, like the tenant isolation
tests: parse result saved -> analysis queued -> worker run -> API reads.

    DATABASE_OWNER_URL=postgresql://atlas_owner:change-me@localhost:5432/atlas pytest tests/test_pipeline_db.py
"""

from __future__ import annotations

import os
import pathlib
import uuid

import pytest

from .util import expect_error

psycopg = pytest.importorskip("psycopg")
URL = os.environ.get("DATABASE_OWNER_URL")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_OWNER_URL not set")
FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "catalogue"


@pytest.fixture(scope="module")
def ids():
    for key, value in {
        "DATABASE_URL": URL,
        "CLERK_ISSUER": "https://example.clerk.accounts.dev",
        "STORAGE_BUCKET": "test",
        "STORAGE_ACCESS_KEY_ID": "test",
        "STORAGE_SECRET_ACCESS_KEY": "test",
    }.items():
        os.environ.setdefault(key, value)
    from atlas import db, migrate
    from atlas.config import get_settings

    get_settings.cache_clear()
    os.environ["DATABASE_OWNER_URL"] = URL
    assert migrate.main() == 0
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("SET ROLE atlas_app")
        a = conn.execute("SELECT org_id, user_id FROM ensure_identity(%s,'Pipeline A','u_pa','pa@a.test','A','admin')", (f"org_pa_{uuid.uuid4()}",)).fetchone()
        b = conn.execute("SELECT org_id, user_id FROM ensure_identity(%s,'Pipeline B','u_pb','pb@b.test','B','admin')", (f"org_pb_{uuid.uuid4()}",)).fetchone()
    yield {"a": a, "b": b}
    db.close_pool()


def identity(pair):
    from atlas.auth import Identity

    return Identity(org_id=pair[0], user_id=pair[1], role="admin")


def upload(org_id, content: bytes) -> uuid.UUID:
    from atlas import datasets, db
    from atlas.ingest import ingest

    dataset_id = uuid.uuid4()
    with db.tenant(org_id) as conn:
        conn.execute("INSERT INTO datasets (id, org_id, name, status) VALUES (%s, %s, 'test', 'parsing')", (dataset_id, org_id))
        datasets.save_parse_result(conn, org_id, dataset_id, ingest(content))
    return dataset_id


def start(org_id, dataset_id) -> str:
    from atlas import analysis, datasets, db

    with db.tenant(org_id) as conn:
        return analysis.start(conn, org_id, datasets.get_dataset(conn, dataset_id))["run_id"]


def test_catalogue_analysis_end_to_end(ids):
    from atlas import analysis, datasets, db
    from atlas.api import analysis as api

    org = ids["a"][0]
    dataset_id = upload(org, (FIXTURES / "stores.csv").read_bytes())
    run_id = start(org, dataset_id)
    with db.tenant(org) as conn:
        assert conn.execute("SELECT status FROM datasets WHERE id = %s", (dataset_id,)).fetchone()["status"] == "analysing"
        assert conn.execute("SELECT count(*) AS n FROM jobs WHERE payload->>'run_id' = %s", (run_id,)).fetchone()["n"] == 1

    result = analysis.run(org, dataset_id, run_id)
    assert result is not None and result.groups

    status = api.get_analysis(dataset_id, identity=identity(ids["a"]))
    assert status["status"] == "analysed"
    summary = status["analysis"]["summary"]
    assert summary["groups"] == len(result.groups) and summary["duplicate_lines"] > 0

    page = api.list_groups(dataset_id, identity=identity(ids["a"]), confidence=None, limit=200, offset=0)
    assert page["total"] == len(result.groups)
    first = page["groups"][0]
    assert first["id"] == "G-0001" and first["reasons"]
    assert sum(m["role"] == "master" for m in first["members"]) == 1
    assert all(m["name"] for m in first["members"])

    high = api.list_groups(dataset_id, identity=identity(ids["a"]), confidence="high", limit=200, offset=0)
    assert all(g["confidence"] == "high" for g in high["groups"])

    looks = api.list_pairs(dataset_id, identity=identity(ids["a"]), kind="lookalike", limit=50, offset=0)
    assert looks["total"] == len(result.lookalikes) and looks["pairs"][0]["detail"]

    # Another company sees nothing, not even that the dataset exists.
    with expect_error("not_found"):
        api.list_groups(dataset_id, identity=identity(ids["b"]), confidence=None, limit=50, offset=0)
    with db.tenant(ids["b"][0]) as conn:
        assert conn.execute("SELECT count(*) AS n FROM match_groups WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM match_members WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM match_pairs WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"] == 0

    # Changing the columns throws the results away.
    with db.tenant(org) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        datasets.apply_mapping(conn, dataset, dataset["mapping"])
        assert conn.execute("SELECT count(*) AS n FROM match_groups WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"] == 0
        assert datasets.get_dataset(conn, dataset_id)["status"] == "ready"


def test_a_run_is_dropped_if_the_mapping_changes_meanwhile(ids):
    from atlas import analysis, datasets, db

    org = ids["a"][0]
    dataset_id = upload(org, (FIXTURES / "bearings.csv").read_bytes())
    run_id = start(org, dataset_id)
    with db.tenant(org) as conn:
        dataset = datasets.get_dataset(conn, dataset_id)
        datasets.apply_mapping(conn, dataset, {**dataset["mapping"], "brand": None})
    assert analysis.run(org, dataset_id, run_id) is None
    with db.tenant(org) as conn:
        assert conn.execute("SELECT count(*) AS n FROM match_groups WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"] == 0


def test_task_exports_cannot_be_analysed_yet(ids):
    from atlas import analysis, datasets, db

    org = ids["a"][0]
    dataset_id = upload(org, b"Summary,Status\nCreate login page,Open\nCreate login screen,Open\n")
    with db.tenant(org) as conn, expect_error("analysis_not_available"):
        analysis.start(conn, org, datasets.get_dataset(conn, dataset_id))


def test_failed_run_gives_the_dataset_back(ids):
    from atlas import analysis, db

    org = ids["a"][0]
    dataset_id = upload(org, (FIXTURES / "bearings.csv").read_bytes())
    run_id = start(org, dataset_id)
    analysis.fail(org, dataset_id, run_id, "analysis_failed")
    with db.tenant(org) as conn:
        row = conn.execute("SELECT status, analysis FROM datasets WHERE id = %s", (dataset_id,)).fetchone()
    assert row["status"] == "ready" and row["analysis"]["error_code"] == "analysis_failed"


def test_ai_settings_and_cache_are_per_workspace(ids):
    from atlas import analysis, db
    from atlas.api import analysis as api
    from atlas.auth import Identity

    a, b = ids["a"], ids["b"]
    settings = api.get_workspace_settings(identity=identity(a))
    assert settings["ai_review"] is True and settings["can_edit"] is True
    member = Identity(org_id=a[0], user_id=a[1], role="member")
    with expect_error("admin_only"):
        api.put_workspace_settings(api.SettingsIn(ai_review=False), identity=member)
    assert api.put_workspace_settings(api.SettingsIn(ai_review=False), identity=identity(a))["ai_review"] is False
    assert api.get_workspace_settings(identity=identity(b))["ai_review"] is True
    api.put_workspace_settings(api.SettingsIn(ai_review=True), identity=identity(a))

    analysis.DbCache(a[0]).put_many({"k1": ("same", "Same bearing.")}, "claude-opus-5")
    assert analysis.DbCache(a[0]).get_many(["k1"]) == {"k1": ("same", "Same bearing.")}
    assert analysis.DbCache(b[0]).get_many(["k1"]) == {}
    with db.tenant(b[0]) as conn:
        assert conn.execute("SELECT count(*) AS n FROM ai_cache WHERE key = 'k1'").fetchone()["n"] == 0


def test_analysis_records_whether_ai_ran(ids):
    import json as _json
    from types import SimpleNamespace

    from atlas import analysis, db
    from atlas.catalogue.ai_review import ClaudeReviewer

    org = ids["a"][0]
    # Without a key the worker's run skips AI and says so.
    dataset_id = upload(org, (FIXTURES / "stores.csv").read_bytes())
    analysis.run(org, dataset_id, start(org, dataset_id), use_ai=True)
    with db.tenant(org) as conn:
        summary = conn.execute("SELECT analysis FROM datasets WHERE id = %s", (dataset_id,)).fetchone()["analysis"]["summary"]
    assert summary["ai"] == "not_configured" and summary["needs_review"] > 0

    # With a reviewer, answers are cached for the workspace.
    def create(**kwargs):
        pairs = _json.loads(kwargs["messages"][0]["content"].split("\n", 1)[1])
        text = _json.dumps({"answers": [{"pair": p["pair"], "verdict": "unsure", "reason": "Can't tell."} for p in pairs]})
        return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5", content=[SimpleNamespace(type="text", text=text)], usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    reviewer = ClaudeReviewer(client, cache=analysis.DbCache(org))
    analysis.run(org, dataset_id, start(org, dataset_id), reviewer=reviewer)
    assert reviewer.stats.requests >= 1
    with db.tenant(org) as conn:
        assert conn.execute("SELECT count(*) AS n FROM ai_cache").fetchone()["n"] >= summary["needs_review"]


def storage_available() -> bool:
    try:
        from atlas import storage

        storage.put("probe/atlas-tests", b"ok")
        storage.delete("probe/atlas-tests")
        return True
    except Exception:
        return False


def test_export_end_to_end(ids):
    import csv
    import io

    from atlas import analysis, datasets, db, export, storage
    from atlas.api import analysis as api

    if not storage_available():
        pytest.skip("file storage not reachable (set STORAGE_* to the local storage server)")
    org = ids["a"][0]
    dataset_id = upload(org, (FIXTURES / "stores.csv").read_bytes())
    analysis.run(org, dataset_id, start(org, dataset_id))
    with db.tenant(org) as conn:
        summary = conn.execute("SELECT analysis FROM datasets WHERE id = %s", (dataset_id,)).fetchone()["analysis"]["summary"]
    assert summary["stock"]["has_stock"] and summary["stock"]["units_on_duplicates"] > 0 and summary["stock"]["value_on_duplicates"] > 0
    page = api.list_groups(dataset_id, identity=identity(ids["a"]), confidence=None, limit=200, offset=0)
    assert all(g["name_standard"] for g in page["groups"])
    assert any(g["value_on_duplicates"] for g in page["groups"])

    state = api.start_export(dataset_id, identity=identity(ids["a"]))["export"]
    assert state["state"] == "building"
    with db.tenant(org) as conn:
        run_id = conn.execute("SELECT export->>'run_id' AS r FROM datasets WHERE id = %s", (dataset_id,)).fetchone()["r"]
    assert export.run(org, dataset_id, run_id)
    ready = api.get_export(dataset_id, identity=identity(ids["a"]))["export"]
    assert ready["state"] == "ready" and ready["file"]["name"].endswith(" - Atlas.csv")

    response = api.download_export(dataset_id, identity=identity(ids["a"]))
    assert response.headers["content-type"].startswith("text/csv") and "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
    source = (FIXTURES / "stores.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == len(source)
    assert rows[0][: len(source[0].split(","))] == source[0].split(",") and rows[0][-12] == "atlas_group"
    roles = {r[rows[0].index("atlas_role")] for r in rows[1:]}
    assert {"master", "duplicate", "unique"} <= roles

    with expect_error("not_found"):
        api.download_export(dataset_id, identity=identity(ids["b"]))

    # New column choices make the export stale: the file is deleted.
    with db.tenant(org) as conn:
        key = conn.execute("SELECT object_key FROM dataset_files WHERE dataset_id = %s AND kind = 'export'", (dataset_id,)).fetchone()["object_key"]
        dataset = datasets.get_dataset(conn, dataset_id)
        datasets.apply_mapping(conn, dataset, dataset["mapping"])
        assert conn.execute("SELECT count(*) AS n FROM dataset_files WHERE dataset_id = %s AND kind = 'export'", (dataset_id,)).fetchone()["n"] == 0
        assert datasets.get_dataset(conn, dataset_id)["original_filename"] is None  # only the upload row is joined, and this test had none
    from botocore.exceptions import ClientError

    with pytest.raises(ClientError):
        storage.get_any(key)


def test_review_actions_apply_now_and_survive_a_rerun(ids):
    from atlas import analysis, db, review
    from atlas.api import analysis as api

    org, user = ids["a"]
    dataset_id = upload(org, (FIXTURES / "stores.csv").read_bytes())
    analysis.run(org, dataset_id, start(org, dataset_id))

    def groups():
        return {g["id"]: g for g in api.list_groups(dataset_id, identity=identity(ids["a"]), confidence=None, limit=200, offset=0)["groups"]}

    def rows_of(g):
        return sorted(m["row_number"] for m in g["members"])

    before = groups()
    big = [g for g in before.values() if len(g["members"]) >= 3]
    pairs2 = [g for g in before.values() if len(g["members"]) == 2]
    approve, trim, reject = big[0], big[1], pairs2[0]

    with db.tenant(org) as conn:
        s = review.group_action(conn, org, user, dataset_id, approve["id"], "approve")
        assert s["groups_reviewed"] == 1
        other = next(r for r in rows_of(approve) if r != approve["master_row"])
        review.group_action(conn, org, user, dataset_id, approve["id"], "set_master", other)
        removed = next(r for r in rows_of(trim) if r != trim["master_row"])
        review.group_action(conn, org, user, dataset_id, trim["id"], "remove_row", removed)
        s = review.group_action(conn, org, user, dataset_id, reject["id"], "reject")
    after = groups()
    assert after[approve["id"]]["confidence"] == "reviewed" and after[approve["id"]]["master_row"] == other
    assert removed not in rows_of(after[trim["id"]])
    assert reject["id"] not in after
    assert s["groups"] == len(before) - 1

    todo = api.list_pairs(dataset_id, identity=identity(ids["a"]), kind="review", limit=50, offset=0)["pairs"]
    looks = api.list_pairs(dataset_id, identity=identity(ids["a"]), kind="lookalike", limit=50, offset=0)["pairs"]
    same = todo[0]
    different = looks[0]
    with db.tenant(org) as conn:
        review.pair_action(conn, org, user, dataset_id, same["a"]["row_number"], same["b"]["row_number"], "same")
        review.pair_action(conn, org, user, dataset_id, different["a"]["row_number"], different["b"]["row_number"], "different")
    merged = [g for g in groups().values() if {same["a"]["row_number"], same["b"]["row_number"]} <= set(rows_of(g))]
    assert len(merged) == 1 and merged[0]["confidence"] == "reviewed"
    left = api.list_pairs(dataset_id, identity=identity(ids["a"]), kind="lookalike", limit=200, offset=0)["pairs"]
    assert (different["a"]["row_number"], different["b"]["row_number"]) not in {(p["a"]["row_number"], p["b"]["row_number"]) for p in left}

    # Run the analysis again: every decision is still there.
    analysis.run(org, dataset_id, start(org, dataset_id))
    rerun = groups()
    by_rows = {tuple(rows_of(g)): g for g in rerun.values()}
    approved = next(g for g in rerun.values() if other in rows_of(g))
    assert approved["master_row"] == other
    assert all(not set(rows_of(reject)) <= set(rows_of(g)) for g in rerun.values())
    assert all(not ({removed} | (set(rows_of(trim)) - {removed})) <= set(rows_of(g)) or len(rows_of(g)) < 2 for g in rerun.values())
    assert any({same["a"]["row_number"], same["b"]["row_number"]} <= set(k) for k in by_rows)

    # Another company can't touch these results.
    with db.tenant(ids["b"][0]) as conn, expect_error("not_found"):
        review.group_action(conn, ids["b"][0], ids["b"][1], dataset_id, approve["id"], "reject")
    with db.tenant(ids["b"][0]) as conn:
        assert conn.execute("SELECT count(*) AS n FROM review_decisions WHERE dataset_id = %s", (dataset_id,)).fetchone()["n"] == 0

    # Nonsense is refused.
    with db.tenant(org) as conn, expect_error("invalid_review"):
        review.group_action(conn, org, user, dataset_id, approved["id"], "set_master", 999999)
