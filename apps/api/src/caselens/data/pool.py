"""Process-wide connection pool (psycopg_pool).

Opened in the FastAPI lifespan and shared by the endpoints and the agent. The CLI and the
bootstrap keep using direct one-off connections (caselens.data.db.connect).
"""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from caselens.config.settings import Settings, get_settings
from caselens.data.db import connect

_pool: ConnectionPool | None = None


def open_pool(settings: Settings | None = None) -> ConnectionPool:
    """Open the shared pool if it is not already open. Idempotent."""
    global _pool
    if _pool is None:
        settings = settings or get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,  # ponytail: fixed; lift to a setting if a deploy needs to tune concurrency
            name="caselens",
            open=False,
        )
        _pool.open()
    return _pool


def get_pool() -> ConnectionPool | None:
    """The shared pool, or None outside the API (CLI, bootstrap, tests)."""
    return _pool


def close_pool() -> None:
    """Close the shared pool and forget it. Idempotent."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def db_connection() -> Iterator[psycopg.Connection]:
    """Yield a connection from the pool when it is open, else a one-off direct connection.

    Lets endpoints and the agent run identically whether the pool exists (under the API) or
    not (CLI, tests). Writes must still commit explicitly; the pool rolls back on return.
    """
    pool = get_pool()
    if pool is not None:
        with pool.connection() as conn:
            yield conn
    else:
        conn = connect()
        try:
            yield conn
        finally:
            conn.close()
