"""Apply SQL migrations in order. Run as the database owner role:

    DATABASE_OWNER_URL=postgres://... python -m atlas.migrate

The owner role needs permission to create roles (CREATEROLE) the first time,
because 0001 creates atlas_app.
"""

from __future__ import annotations

import os
import pathlib
import sys

import psycopg

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations"


def main() -> int:
    url = os.environ.get("DATABASE_OWNER_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("Set DATABASE_OWNER_URL to the database owner's connection string.", file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        # Session lock: two deploys starting at once can't both migrate.
        conn.execute("SELECT pg_advisory_lock(424242)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = {row[0] for row in conn.execute("SELECT name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            print(f"applying {path.name}")
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        conn.execute("SELECT pg_advisory_unlock(424242)")
    print("migrations up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
