"""A failing tool must not poison the agent's shared connection, and its audit must still be
written. Reproduces the InFailedSqlTransaction cascade without a real Postgres."""

import json
from types import SimpleNamespace

import psycopg

from caselens.agent import loop as agent_loop
from caselens.agent.loop import run_agent
from caselens.agent.tools import AgentTool, ToolOutcome
from caselens.data.models import Role, TenantContext


class _Cursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        if self._conn.aborted:
            raise psycopg.errors.InFailedSqlTransaction("current transaction is aborted")
        if sql == "__FAIL__":
            self._conn.aborted = True
            raise psycopg.errors.SyntaxError("boom")


class _FakeConn:
    """psycopg-like connection that models the aborted-transaction state machine."""

    def __init__(self) -> None:
        self.aborted = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        if self.aborted:
            raise psycopg.errors.InFailedSqlTransaction("cannot commit an aborted transaction")
        self.commits += 1

    def rollback(self) -> None:
        self.aborted = False
        self.rollbacks += 1


def _call(call_id: str, name: str, args: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id, type="function", function=SimpleNamespace(name=name, arguments=json.dumps(args))
    )


def _resp(*, tool_calls=None, text=None) -> SimpleNamespace:
    content = [SimpleNamespace(text=text)] if text is not None else None
    return SimpleNamespace(
        message=SimpleNamespace(
            tool_calls=tool_calls, tool_plan=None, content=content, citations=None
        )
    )


def _fake_co(responses: list) -> SimpleNamespace:
    iterator = iter(responses)
    return SimpleNamespace(chat=lambda **kwargs: next(iterator))


def test_failing_tool_does_not_poison_session_and_audit_is_written(monkeypatch):
    conn = _FakeConn()

    def failing_run(**kwargs) -> ToolOutcome:
        with conn.cursor() as cur:
            cur.execute("__FAIL__")  # aborts the transaction, like a bad query
        return ToolOutcome(result={})  # unreachable

    tool = AgentTool("boom", "always fails", {"type": "object", "properties": {}}, failing_run)

    audits: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        agent_loop,
        "audit_isolated",
        lambda ctx, action, target_type, target_id, metadata=None: audits.append(
            (action, metadata)
        ),
    )

    co = _fake_co(
        [
            _resp(tool_calls=[_call("t1", "boom", {})]),
            _resp(text="No pude completar la herramienta."),
        ]
    )
    ctx = TenantContext(tenant_id=1, user_id=1, role=Role.REVIEWER)

    result = run_agent(ctx, "hazlo", co=co, conn=conn, tools=[tool])

    # The failure was reported to the model, not raised out of the loop.
    assert result.tool_trace[0].result["error"]
    assert result.answer == "No pude completar la herramienta."
    # Contained: the shared connection was rolled back and is usable again (commit succeeded).
    assert conn.rollbacks == 1
    assert conn.aborted is False
    assert conn.commits == 1
    # The audit was still written, marked not-ok, via the isolated path.
    assert audits == [("agent.tool_call", {"ok": False, "denied": False})]


def test_audit_isolated_writes_and_commits_on_its_own_connection(monkeypatch):
    class _AuditCursor:
        def __init__(self, conn: "_AuditConn") -> None:
            self._conn = conn

        def __enter__(self) -> "_AuditCursor":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def execute(self, sql: str, params: object = None) -> None:
            self._conn.rows.append(params)

    class _AuditConn:
        def __init__(self) -> None:
            self.rows: list = []
            self.commits = 0
            self.closed = False

        def cursor(self) -> _AuditCursor:
            return _AuditCursor(self)

        def commit(self) -> None:
            self.commits += 1

        def close(self) -> None:
            self.closed = True

    fake = _AuditConn()
    # No pool open -> db_connection falls back to a one-off direct connection (our fake).
    monkeypatch.setattr("caselens.data.pool.get_pool", lambda: None)
    monkeypatch.setattr("caselens.data.pool.connect", lambda *a, **k: fake)

    from caselens.security.audit import audit_isolated

    ctx = TenantContext(tenant_id=1, user_id=2, role=Role.REVIEWER)
    audit_isolated(ctx, "agent.tool_call", "tool", "boom", {"ok": False})

    assert len(fake.rows) == 1  # one audit row inserted
    assert fake.commits == 1  # committed independently of any caller transaction
    assert fake.closed is True  # the dedicated connection was released
