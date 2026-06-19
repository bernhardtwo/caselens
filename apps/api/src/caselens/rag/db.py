from collections.abc import Sequence
from pathlib import Path

import psycopg

from caselens.config.settings import Settings, get_settings

_SCHEMA = Path(__file__).parent / "schema.sql"


def connect(settings: Settings | None = None) -> psycopg.Connection:
    settings = settings or get_settings()
    return psycopg.connect(settings.database_url)


def to_vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


def init_db(conn: psycopg.Connection, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    ddl = _SCHEMA.read_text(encoding="utf-8")
    if settings.embedding_dim != 1536:
        ddl = ddl.replace("vector(1536)", f"vector({settings.embedding_dim})")
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
