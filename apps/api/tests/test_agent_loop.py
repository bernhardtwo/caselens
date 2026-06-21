"""Agent loop tests with Command mocked, against the local/CI Postgres (spec-0003)."""

import json
from types import SimpleNamespace

import psycopg
import pytest

from caselens.agent import tools as agent_tools
from caselens.agent.loop import run_agent
from caselens.data.db import apply_schema, connect
from caselens.data.models import ClaimStatus, Role, TenantContext
from caselens.rag.models import Citation, GroundedAnswer, RetrievedChunk

pytestmark = pytest.mark.integration


@pytest.fixture
def conn():
    try:
        connection = connect()
    except psycopg.OperationalError:
        pytest.skip("Postgres no disponible (levanta infra/docker-compose).")
    apply_schema(connection)
    with connection.cursor() as cur:
        cur.execute("TRUNCATE audit_log, claims, users, tenants RESTART IDENTITY CASCADE")
    connection.commit()
    yield connection
    connection.close()


def _seed(conn: psycopg.Connection) -> dict[str, int]:
    ids: dict[str, int] = {}
    with conn.cursor() as cur:
        for key, name in (("a", "Tenant A"), ("b", "Tenant B")):
            cur.execute("INSERT INTO tenants (name) VALUES (%s) RETURNING id", (name,))
            ids[key] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
                (ids[key], f"reviewer@{key}", Role.REVIEWER.value),
            )
            ids[f"{key}_reviewer"] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
                (ids[key], f"agent@{key}", Role.AGENT.value),
            )
            ids[f"{key}_agent"] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO claims (tenant_id, claimant_name, product, "
                "description, status, severity) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (ids[key], "C", "Solar Inverter X1", "d", ClaimStatus.OPEN.value, "low"),
            )
            ids[f"{key}_claim"] = cur.fetchone()[0]
    conn.commit()
    return ids


def _call(call_id: str, name: str, args: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _resp(*, tool_calls=None, text=None, tool_plan=None) -> SimpleNamespace:
    content = [SimpleNamespace(text=text)] if text is not None else None
    return SimpleNamespace(
        message=SimpleNamespace(
            tool_calls=tool_calls, tool_plan=tool_plan, content=content, citations=None
        )
    )


def _fake_co(responses: list) -> SimpleNamespace:
    iterator = iter(responses)
    return SimpleNamespace(chat=lambda **kwargs: next(iterator))


def _audit_actions(conn: psycopg.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT action FROM audit_log ORDER BY id")
        return [row[0] for row in cur.fetchall()]


def test_query_claims_is_tenant_scoped(conn):
    ids = _seed(conn)
    co = _fake_co(
        [_resp(tool_calls=[_call("t1", "query_claims", {})]), _resp(text="Tienes 1 reclamo.")]
    )
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    result = run_agent(ctx, "lista mis reclamos", co=co, conn=conn)
    assert result.tool_trace[0].name == "query_claims"
    returned = {claim["id"] for claim in result.tool_trace[0].result["claims"]}
    assert returned == {ids["a_claim"]}
    assert "agent.tool_call" in _audit_actions(conn)


def test_cross_tenant_get_returns_nothing(conn):
    ids = _seed(conn)
    co = _fake_co(
        [
            _resp(tool_calls=[_call("t1", "get_claim", {"claim_id": ids["b_claim"]})]),
            _resp(text="No encuentro ese reclamo."),
        ]
    )
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    result = run_agent(ctx, "muéstrame el reclamo", co=co, conn=conn)
    assert result.tool_trace[0].result["claim"] is None


def test_update_allowed_mutates_and_audits(conn):
    ids = _seed(conn)
    co = _fake_co(
        [
            _resp(
                tool_calls=[
                    _call(
                        "t1",
                        "update_claim_status",
                        {"claim_id": ids["a_claim"], "new_status": "in_review"},
                    )
                ]
            ),
            _resp(text="Listo, en revisión."),
        ]
    )
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    result = run_agent(ctx, "pásalo a revisión", co=co, conn=conn)
    assert result.actions_taken == [
        {
            "action": "update_claim_status",
            "claim_id": ids["a_claim"],
            "from": "open",
            "to": "in_review",
        }
    ]
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM claims WHERE id = %s", (ids["a_claim"],))
        assert cur.fetchone()[0] == "in_review"
    assert "claim.update_status" in _audit_actions(conn)


def test_update_denied_for_agent_role(conn):
    ids = _seed(conn)
    co = _fake_co(
        [
            _resp(
                tool_calls=[
                    _call(
                        "t1",
                        "update_claim_status",
                        {"claim_id": ids["a_claim"], "new_status": "approved"},
                    )
                ]
            ),
            _resp(text="No tienes permiso."),
        ]
    )
    ctx = TenantContext(ids["a"], ids["a_agent"], Role.AGENT)
    result = run_agent(ctx, "apruébalo", co=co, conn=conn)
    assert result.tool_trace[0].result["denied"] is True
    assert result.actions_taken == []
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM claims WHERE id = %s", (ids["a_claim"],))
        assert cur.fetchone()[0] == "open"
    actions = _audit_actions(conn)
    assert "agent.update_denied" in actions
    assert "claim.update_status" not in actions


def test_rag_search_grounds_answer_with_citations(conn, monkeypatch):
    ids = _seed(conn)
    chunk = RetrievedChunk(
        chunk_id=1,
        document_id=1,
        source_path="data/corpus/warranty-policy.md",
        title="Warranty",
        section="Coverage",
        ordinal=0,
        text="Covered.",
        vector_distance=0.1,
        vector_rank=1,
        rerank_score=0.9,
        rerank_rank=1,
    )
    grounded = GroundedAnswer(
        text="Covered for 5 years.",
        citations=[Citation(start=0, end=7, text="Covered", sources=["0"])],
        sources=[chunk],
    )
    monkeypatch.setattr(agent_tools, "retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(agent_tools, "build_answer", lambda *a, **k: grounded)
    co = _fake_co(
        [
            _resp(tool_calls=[_call("t1", "rag_search", {"query": "warranty?"})]),
            _resp(text="La garantía cubre 5 años."),
        ]
    )
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    result = run_agent(ctx, "¿qué cubre la garantía?", co=co, conn=conn)
    assert result.tool_trace[0].name == "rag_search"
    assert len(result.citations) == 1
    assert result.sources[0].source_path.endswith("warranty-policy.md")
