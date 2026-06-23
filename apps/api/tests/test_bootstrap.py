import psycopg
import pytest

from caselens import bootstrap


class _DummyConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_runs_steps_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "init_databases", lambda: calls.append("init"))
    monkeypatch.setattr(bootstrap, "ingest_corpus", lambda: calls.append("ingest"))
    monkeypatch.setattr(
        bootstrap,
        "seed_database",
        lambda: calls.append("seed") or {"tenants": 1, "users": 1, "claims": 1},
    )
    assert bootstrap.main() == 0
    assert calls == ["init", "ingest", "seed"]


def test_init_databases_retries_until_postgres_answers(monkeypatch):
    attempts = {"n": 0}

    def flaky_connect():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise psycopg.OperationalError("connection refused")
        return _DummyConn()

    monkeypatch.setattr(bootstrap, "connect", flaky_connect)
    monkeypatch.setattr(bootstrap, "init_db", lambda conn: None)
    monkeypatch.setattr(bootstrap, "apply_data_schema", lambda conn: None)
    monkeypatch.setattr(bootstrap.time, "sleep", lambda _seconds: None)
    bootstrap.init_databases()
    assert attempts["n"] == 3


def test_init_databases_does_not_retry_non_connection_errors(monkeypatch):
    def connect():
        raise psycopg.ProgrammingError("syntax error")

    monkeypatch.setattr(bootstrap, "connect", connect)
    monkeypatch.setattr(bootstrap.time, "sleep", lambda _seconds: None)
    with pytest.raises(psycopg.ProgrammingError):
        bootstrap.init_databases()


def test_stops_before_seed_when_ingest_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "init_databases", lambda: calls.append("init"))

    def boom():
        calls.append("ingest")
        raise RuntimeError("ingest failed")

    monkeypatch.setattr(bootstrap, "ingest_corpus", boom)
    monkeypatch.setattr(bootstrap, "seed_database", lambda: calls.append("seed"))
    with pytest.raises(RuntimeError):
        bootstrap.main()
    assert "seed" not in calls


def test_ingest_corpus_raises_when_no_documents(monkeypatch):
    monkeypatch.setattr(bootstrap, "default_corpus_paths", list)
    with pytest.raises(FileNotFoundError):
        bootstrap.ingest_corpus()
