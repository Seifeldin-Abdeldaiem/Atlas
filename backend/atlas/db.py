"""Database access.

Every connection switches to the atlas_app role, which is subject to
row-level security. Tenant work happens inside `tenant(org_id)`, which sets
app.org_id for that transaction only; Postgres then hides every other
company's rows. There is no way to query tenant tables without it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def _configure(conn: psycopg.Connection) -> None:
    role = get_settings().db_app_role
    conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
    conn.commit()


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=settings.db_pool_max,
            kwargs={"row_factory": dict_row, "autocommit": False},
            configure=_configure,
            open=True,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def tenant(org_id: UUID | str) -> Iterator[psycopg.Connection]:
    """A transaction that can only see and write rows of this organization."""
    with pool().connection() as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.org_id', %s, true)", (str(org_id),))
            yield conn


@contextmanager
def system() -> Iterator[psycopg.Connection]:
    """A transaction with no organization set. Tenant tables read as empty;
    only the narrow SECURITY DEFINER functions do anything useful here."""
    with pool().connection() as conn:
        with conn.transaction():
            yield conn
