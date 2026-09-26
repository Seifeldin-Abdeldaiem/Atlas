"""Row-level security tests. They need a real, disposable Postgres:

    DATABASE_OWNER_URL=postgres://atlas:atlas@localhost:5432/atlas_test pytest tests/test_tenant_isolation.py

Each test works as the atlas_app role, exactly as the API and worker do.
"""

from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
URL = os.environ.get("DATABASE_OWNER_URL")
pytestmark = pytest.mark.skipif(not URL, reason="DATABASE_OWNER_URL not set")


@pytest.fixture(scope="module")
def orgs():
    from atlas import migrate

    os.environ["DATABASE_OWNER_URL"] = URL
    assert migrate.main() == 0
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("SET ROLE atlas_app")
        a = conn.execute("SELECT org_id, user_id FROM ensure_identity(%s,'A','u_a','a@a.test','A','admin')", (f"org_a_{uuid.uuid4()}",)).fetchone()
        b = conn.execute("SELECT org_id, user_id FROM ensure_identity(%s,'B','u_b','b@b.test','B','admin')", (f"org_b_{uuid.uuid4()}",)).fetchone()
    return {"a": a, "b": b}


def as_org(conn, org_id):
    conn.execute("SET ROLE atlas_app")
    conn.execute("SELECT set_config('app.org_id', %s, false)", (str(org_id),))


def make_dataset(org_id) -> uuid.UUID:
    dataset_id = uuid.uuid4()
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, org_id)
        conn.execute("INSERT INTO datasets (id, org_id, name, status) VALUES (%s, %s, 'd', 'ready')", (dataset_id, org_id))
        conn.execute("INSERT INTO tasks (org_id, dataset_id, row_number, original) VALUES (%s, %s, 2, '{\"Title\": \"secret\"}')", (org_id, dataset_id))
    return dataset_id


def test_company_b_cannot_read_company_a(orgs):
    a_org, b_org = orgs["a"][0], orgs["b"][0]
    dataset_id = make_dataset(a_org)
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, b_org)
        assert conn.execute("SELECT count(*) FROM datasets WHERE id = %s", (dataset_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM tasks WHERE dataset_id = %s", (dataset_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM organizations WHERE id = %s", (a_org,)).fetchone()[0] == 0


def test_company_b_cannot_modify_or_delete_company_a(orgs):
    a_org, b_org = orgs["a"][0], orgs["b"][0]
    dataset_id = make_dataset(a_org)
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, b_org)
        assert conn.execute("UPDATE datasets SET name = 'x' WHERE id = %s", (dataset_id,)).rowcount == 0
        assert conn.execute("DELETE FROM tasks WHERE dataset_id = %s", (dataset_id,)).rowcount == 0


def test_cannot_write_rows_into_another_company(orgs):
    a_org, b_org = orgs["a"][0], orgs["b"][0]
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, b_org)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO datasets (org_id, name, status) VALUES (%s, 'planted', 'ready')", (a_org,))


def test_no_org_set_sees_nothing(orgs):
    make_dataset(orgs["a"][0])
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("SET ROLE atlas_app")
        assert conn.execute("SELECT count(*) FROM datasets").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0


def test_users_of_other_companies_are_invisible(orgs):
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, orgs["b"][0])
        emails = {r[0] for r in conn.execute("SELECT email FROM users")}
        assert "a@a.test" not in emails
        assert "b@b.test" in emails


def test_app_role_cannot_disable_security(orgs):
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("SET ROLE atlas_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("ALTER TABLE datasets DISABLE ROW LEVEL SECURITY")


def test_catalogue_columns_are_protected_too(orgs):
    """Dataset kind and normalised catalogue values (Phase 4) sit on protected
    tables; this checks them explicitly, including the bulk update the app uses."""
    a_org, b_org = orgs["a"][0], orgs["b"][0]
    dataset_id = make_dataset(a_org)
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, a_org)
        conn.execute("UPDATE datasets SET kind = 'catalogue' WHERE id = %s", (dataset_id,))
        conn.execute("UPDATE tasks SET norm = '{\"brand\": \"skf\"}' WHERE dataset_id = %s", (dataset_id,))
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, b_org)
        assert conn.execute("SELECT count(*) FROM tasks WHERE norm IS NOT NULL AND dataset_id = %s", (dataset_id,)).fetchone()[0] == 0
        assert conn.execute("UPDATE datasets SET kind = 'tasks' WHERE id = %s", (dataset_id,)).rowcount == 0
        planted = conn.execute(
            """UPDATE tasks t SET norm = v.norm
                 FROM jsonb_to_recordset(%s::jsonb) AS v(row_number integer, norm jsonb)
                WHERE t.dataset_id = %s AND t.row_number = v.row_number""",
            ('[{"row_number": 2, "norm": {"brand": "planted"}}]', dataset_id),
        )
        assert planted.rowcount == 0
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, a_org)
        assert conn.execute("SELECT kind FROM datasets WHERE id = %s", (dataset_id,)).fetchone()[0] == "catalogue"
        assert conn.execute("SELECT norm->>'brand' FROM tasks WHERE dataset_id = %s", (dataset_id,)).fetchone()[0] == "skf"


def test_analysis_results_are_protected(orgs):
    """Duplicate groups, members and pairs (Phase 4): company B can't plant
    results into company A's dataset or read them."""
    a_org, b_org = orgs["a"][0], orgs["b"][0]
    dataset_id = make_dataset(a_org)
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, a_org)
        group_id = conn.execute(
            "INSERT INTO match_groups (org_id, dataset_id, label, confidence, master_row) VALUES (%s, %s, 'G-0001', 'high', 2) RETURNING id",
            (a_org, dataset_id),
        ).fetchone()[0]
        conn.execute("INSERT INTO match_members (group_id, org_id, dataset_id, row_number, role) VALUES (%s, %s, %s, 2, 'master')", (group_id, a_org, dataset_id))
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, b_org)
        assert conn.execute("SELECT count(*) FROM match_groups WHERE id = %s", (group_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM match_members WHERE group_id = %s", (group_id,)).fetchone()[0] == 0
        assert conn.execute("DELETE FROM match_groups WHERE id = %s", (group_id,)).rowcount == 0
        for sql, args in (
            ("INSERT INTO match_groups (org_id, dataset_id, label, confidence, master_row) VALUES (%s, %s, 'G-9', 'high', 2)", (a_org, dataset_id)),
            ("INSERT INTO match_pairs (org_id, dataset_id, kind, row_a, row_b, reason_code, detail, score, source) VALUES (%s, %s, 'review', 2, 3, 'x', 'x', 0.5, 'rule')", (a_org, dataset_id)),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(sql, args)


def test_review_decisions_are_protected(orgs):
    a_org, b_org = orgs["a"][0], orgs["b"][0]
    dataset_id = make_dataset(a_org)
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, a_org)
        conn.execute("INSERT INTO review_decisions (org_id, dataset_id, action, rows) VALUES (%s, %s, 'same', '{2,3}')", (a_org, dataset_id))
    with psycopg.connect(URL, autocommit=True) as conn:
        as_org(conn, b_org)
        assert conn.execute("SELECT count(*) FROM review_decisions WHERE dataset_id = %s", (dataset_id,)).fetchone()[0] == 0
        assert conn.execute("DELETE FROM review_decisions WHERE dataset_id = %s", (dataset_id,)).rowcount == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("INSERT INTO review_decisions (org_id, dataset_id, action, rows) VALUES (%s, %s, 'different', '{2,3}')", (a_org, dataset_id))
