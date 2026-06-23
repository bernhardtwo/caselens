import psycopg

from caselens import bootstrap


def test_runs_steps_in_order_and_returns_zero(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "rag_main", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(bootstrap, "seed_main", lambda argv: calls.append("seed") or 0)
    assert bootstrap.main() == 0
    assert calls == [["init-db"], ["ingest"], "seed"]


def test_retries_init_db_until_postgres_answers(monkeypatch):
    attempts = {"n": 0}

    def flaky(argv):
        if argv == ["init-db"]:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise psycopg.OperationalError("connection refused")
        return 0

    monkeypatch.setattr(bootstrap, "rag_main", flaky)
    monkeypatch.setattr(bootstrap, "seed_main", lambda argv: 0)
    monkeypatch.setattr(bootstrap.time, "sleep", lambda _seconds: None)
    assert bootstrap.main() == 0
    assert attempts["n"] == 3


def test_stops_at_first_failing_step(monkeypatch):
    calls = []

    def rag(argv):
        calls.append(argv)
        return 0 if argv == ["init-db"] else 7  # ingest fails

    monkeypatch.setattr(bootstrap, "rag_main", rag)
    monkeypatch.setattr(bootstrap, "seed_main", lambda argv: calls.append("seed") or 0)
    assert bootstrap.main() == 7
    assert "seed" not in calls
