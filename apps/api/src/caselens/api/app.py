import json
import os
from collections.abc import Iterable, Iterator
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from caselens.agent.loop import AgentEvent, AgentResult, EventType, run_agent, run_agent_events
from caselens.agent.tools import apply_status_change
from caselens.clients import MissingApiKeyError
from caselens.data.db import connect
from caselens.data.models import Role, TenantContext
from caselens.rag.models import RetrievedChunk
from caselens.security.audit import audit

app = FastAPI(title="caselens")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class AgentRequest(BaseModel):
    message: str


def get_tenant_context(
    x_tenant_id: Annotated[int, Header()] = 1,
    x_user_id: Annotated[int, Header()] = 1,
    x_role: Annotated[str, Header()] = Role.REVIEWER.value,
) -> TenantContext:
    """Dev-only mock of the authenticated session. The tenant context never comes from the body."""
    try:
        role = Role(x_role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Rol desconocido: {x_role}") from None
    return TenantContext(tenant_id=x_tenant_id, user_id=x_user_id, role=role)


def serialize_source(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
        "source": os.path.basename(chunk.source_path),
        "title": chunk.title,
        "section": chunk.section,
        "rerank_score": chunk.rerank_score,
    }


def serialize_result(result: AgentResult) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "citations": [asdict(c) for c in result.citations],
        "sources": [serialize_source(s) for s in result.sources],
        "tool_trace": [asdict(t) for t in result.tool_trace],
        "actions_taken": result.actions_taken,
    }


def serialize_event(event: AgentEvent) -> dict[str, Any]:
    if event.type is EventType.CITATIONS:
        return {
            "citations": [asdict(c) for c in event.data["citations"]],
            "sources": [serialize_source(s) for s in event.data["sources"]],
        }
    return event.data


def format_sse(event_name: str, data: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_stream(events: Iterable[AgentEvent]) -> Iterator[str]:
    for event in events:
        yield format_sse(event.type.value, serialize_event(event))


@app.post("/agent")
def agent_endpoint(
    body: AgentRequest, ctx: Annotated[TenantContext, Depends(get_tenant_context)]
) -> dict[str, Any]:
    try:
        result = run_agent(ctx, body.message)
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return serialize_result(result)


@app.post("/agent/stream")
def agent_stream(
    body: AgentRequest, ctx: Annotated[TenantContext, Depends(get_tenant_context)]
) -> StreamingResponse:
    # Interactive: mutations are proposed (action_proposed), committed only via /actions/confirm.
    def generate() -> Iterator[str]:
        try:
            yield from sse_stream(run_agent_events(ctx, body.message, interactive=True))
        except MissingApiKeyError as exc:
            yield format_sse("error", {"detail": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")


class ConfirmRequest(BaseModel):
    claim_id: int
    to_status: str


@app.post("/actions/confirm")
def confirm_action(
    body: ConfirmRequest, ctx: Annotated[TenantContext, Depends(get_tenant_context)]
) -> dict[str, Any]:
    # Commit a proposed mutation through the same gated path, scoped to the caller's tenant.
    conn = connect()
    try:
        result = apply_status_change(ctx, body.claim_id, body.to_status, conn=conn)
        if result.get("denied"):
            audit(
                ctx,
                "action.confirm_denied",
                "claim",
                str(body.claim_id),
                {"reason": "rbac", "requested_status": body.to_status},
                conn=conn,
            )
            conn.commit()
            raise HTTPException(status_code=403, detail="El rol no puede confirmar la acción.")
        if not result["ok"]:
            reason = result["reason"]
            code = 404 if "not found" in reason else 400 if "unknown status" in reason else 409
            raise HTTPException(status_code=code, detail=reason)
        return result
    finally:
        conn.close()
