from pathlib import Path

import psycopg

# ponytail: connect is generic infra that happens to live in rag.db; re-export it
# here so the data layer has one entry point. Promote to caselens.db if a third caller appears.
from caselens.rag.db import connect

_SCHEMA = Path(__file__).parent / "schema.sql"

__all__ = ["apply_schema", "connect"]


def apply_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
