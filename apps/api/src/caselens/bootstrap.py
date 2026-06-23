"""One-shot deploy bootstrap: schema (with retry) -> ingest -> seed.

Calls the data-layer functions directly instead of the argparse CLIs, so the caselens-bootstrap
entry point cannot be derailed by how the container passes (or omits) argv. Each step is
idempotent, so re-running is safe; the schema step is retried while Postgres is still unreachable
(a Neon instance may cold start).
"""

import sys
import time

import psycopg

from caselens.data.db import apply_schema as apply_data_schema
from caselens.data.generators import seed_database
from caselens.rag.db import connect, init_db
from caselens.rag.ingest import default_corpus_paths, ingest_documents

_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 30.0
_RETRY_DEADLINE_SECONDS = 300.0


def init_databases() -> None:
    """Create the rag and data schemas, retrying while Postgres refuses connections.

    Backs off exponentially (capped at _RETRY_MAX_SECONDS) until _RETRY_DEADLINE_SECONDS, then
    re-raises. Only connection failures are retried; any other error fails fast.
    """
    deadline = time.monotonic() + _RETRY_DEADLINE_SECONDS
    delay = _RETRY_BASE_SECONDS
    while True:
        try:
            with connect() as conn:
                init_db(conn)
                apply_data_schema(conn)
            return
        except psycopg.OperationalError as exc:
            if time.monotonic() >= deadline:
                raise
            print(f"Esperando a Postgres; reintento en {delay:.0f}s ({exc})", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, _RETRY_MAX_SECONDS)


def ingest_corpus() -> None:
    """Ingest the default corpus; fail loudly if no documents are found."""
    paths = default_corpus_paths()
    if not paths:
        raise FileNotFoundError("No se encontraron documentos en data/corpus para ingerir.")
    report = ingest_documents(paths)
    print(f"Ingeridos {report.documents_ingested} documentos ({report.chunks_written} chunks).")


def main() -> int:
    """Schema (retried) -> ingest -> seed. Any failure propagates, so the job exits non-zero."""
    init_databases()
    ingest_corpus()
    counts = seed_database()
    print(f"Seed: {counts['tenants']} tenants, {counts['users']} users, {counts['claims']} claims.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
