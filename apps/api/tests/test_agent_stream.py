"""Agent event-stream tests with Command mocked, against the local/CI Postgres (spec-0004)."""

import json
from types import SimpleNamespace

import psycopg
import pytest

from caselens.agent import tools as agent_tools
from caselens.agent.loop import EventType, run_agent_events
from caselens.api.app import format_sse, serialize_event, sse_stream
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
        cur.execute("INSERT INTO tenants (name) VALUES ('Tenant A') RETURNING id")
        ids["a"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
            (ids["a"], "reviewer@a", Role.REVIEWER.value),
        )
        ids["a_reviewer"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO claims (tenant_id, claimant_name, product, "
            "description, status, severity) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (ids["a"], "C", "Solar Inverter X1", "d", ClaimStatus.OPEN.value, "low"),
        )
        ids["a_claim"] = cur.fetchone()[0]
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


def test_event_sequence_for_a_read(conn):
    ids = _seed(conn)
    co = _fake_co([_resp(tool_calls=[_call("t1", "query_claims", {})]), _resp(text="Listo.")])
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    events = list(run_agent_events(ctx, "lista mis reclamos", interactive=True, co=co, conn=conn))
    assert [e.type for e in events] == [
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.ANSWER,
    ]
    assert events[0].data["name"] == "query_claims"
    assert events[2].data["text"] == "Listo."


def test_interactive_update_proposes_without_mutation(conn):
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
            _resp(text="Propongo el cambio."),
        ]
    )
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    events = list(run_agent_events(ctx, "pásalo a revisión", interactive=True, co=co, conn=conn))
    proposed = [e for e in events if e.type == EventType.ACTION_PROPOSED]
    assert proposed[0].data == {
        "claim_id": ids["a_claim"],
        "from_status": "open",
        "to_status": "in_review",
    }
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM claims WHERE id = %s", (ids["a_claim"],))
        assert cur.fetchone()[0] == "open"
        cur.execute("SELECT action FROM audit_log ORDER BY id")
        actions = [row[0] for row in cur.fetchall()]
    assert "claim.update_status" not in actions
    assert "agent.tool_call" in actions


def test_rag_search_emits_citations_event(conn, monkeypatch):
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
        text="Cubierto.",
        citations=[Citation(start=0, end=8, text="Cubierto", sources=["0"])],
        sources=[chunk],
    )
    monkeypatch.setattr(agent_tools, "retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(agent_tools, "build_answer", lambda *a, **k: grounded)
    co = _fake_co(
        [
            _resp(tool_calls=[_call("t1", "rag_search", {"query": "garantía?"})]),
            _resp(text="Cubierto 5 años."),
        ]
    )
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    events = list(run_agent_events(ctx, "¿qué cubre?", interactive=True, co=co, conn=conn))
    citations = next(e for e in events if e.type == EventType.CITATIONS)
    assert len(citations.data["citations"]) == 1
    assert citations.data["sources"][0].source_path.endswith("warranty-policy.md")


def test_sse_stream_formats_typed_events():
    from caselens.agent.loop import AgentEvent

    events = [
        AgentEvent(EventType.TOOL_CALL, {"name": "query_claims", "arguments": {}}),
        AgentEvent(EventType.ANSWER, {"text": "ok"}),
    ]
    chunks = list(sse_stream(events))
    assert chunks[0].startswith("event: tool_call\ndata: ")
    assert chunks[1].startswith("event: answer\ndata: ")
    assert json.loads(chunks[1].split("data: ", 1)[1].strip()) == {"text": "ok"}


def test_serialize_event_renders_citations_to_json():
    from caselens.agent.loop import AgentEvent

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
    event = AgentEvent(
        EventType.CITATIONS,
        {"citations": [Citation(start=0, end=3, text="abc", sources=["0"])], "sources": [chunk]},
    )
    payload = serialize_event(event)
    json.dumps(payload)  # must be JSON-serializable
    assert payload["sources"][0]["source"] == "warranty-policy.md"
    assert payload["citations"][0]["sources"] == ["0"]


def test_format_sse_shape():
    out = format_sse("tool_result", {"name": "get_claim", "result": {"claim": None}})
    assert out == 'event: tool_result\ndata: {"name": "get_claim", "result": {"claim": null}}\n\n'
