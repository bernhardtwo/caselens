import os
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from caselens.agent.loop import AgentResult, run_agent
from caselens.clients import MissingApiKeyError
from caselens.data.models import Role, TenantContext

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


def serialize_result(result: AgentResult) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "citations": [asdict(c) for c in result.citations],
        "sources": [
            {
                "source": os.path.basename(s.source_path),
                "title": s.title,
                "section": s.section,
                "rerank_score": s.rerank_score,
            }
            for s in result.sources
        ],
        "tool_trace": [asdict(t) for t in result.tool_trace],
        "actions_taken": result.actions_taken,
    }


@app.post("/agent")
def agent_endpoint(
    body: AgentRequest, ctx: Annotated[TenantContext, Depends(get_tenant_context)]
) -> dict[str, Any]:
    try:
        result = run_agent(ctx, body.message)
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return serialize_result(result)
