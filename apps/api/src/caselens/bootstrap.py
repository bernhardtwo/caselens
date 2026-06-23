"""One-shot deploy bootstrap: init-db (with retry) -> ingest -> seed.

Wraps the existing caselens-rag and caselens-seed entry points so a container job can run
the whole sequence as a single command. Each step is idempotent, so re-running is safe;
init-db is retried while Postgres is still unreachable (a Neon instance may cold start).
"""

import sys
import time

import psycopg

from caselens.data.generators import main as seed_main
from caselens.rag.cli import main as rag_main

_RETRY_BASE_SECONDS = 2.0
_RETRY_MAX_SECONDS = 30.0
_RETRY_DEADLINE_SECONDS = 300.0


def _init_db_with_retry() -> int:
    """Run `caselens-rag init-db`, retrying while Postgres refuses connections.

    Backs off exponentially (capped at _RETRY_MAX_SECONDS) until _RETRY_DEADLINE_SECONDS,
    then gives up. Only connection failures are retried; any other error fails fast.
    """
    deadline = time.monotonic() + _RETRY_DEADLINE_SECONDS
    delay = _RETRY_BASE_SECONDS
    while True:
        try:
            return rag_main(["init-db"])
        except psycopg.OperationalError as exc:
            if time.monotonic() >= deadline:
                print(f"Postgres no respondió a tiempo: {exc}", file=sys.stderr)
                return 1
            print(f"Esperando a Postgres; reintento en {delay:.0f}s ({exc})", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, _RETRY_MAX_SECONDS)


def main() -> int:
    """init-db (retried) -> ingest -> seed, stopping at the first non-zero step."""
    steps = (
        _init_db_with_retry,
        lambda: rag_main(["ingest"]),
        lambda: seed_main([]),
    )
    for step in steps:
        rc = step()
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
