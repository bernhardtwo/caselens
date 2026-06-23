import json
import os
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from caselens.agent.loop import AgentEvent, AgentResult, EventType, run_agent, run_agent_events
from caselens.agent.tools import apply_status_change
from caselens.clients import MissingApiKeyError
from caselens.config.settings import get_settings
from caselens.data.models import AuditEntry, Claim, ClaimFilters, ClaimStatus, Role, TenantContext
from caselens.data.pool import close_pool, db_connection, open_pool
from caselens.data.repository import ClaimsRepository
from caselens.rag.models import RetrievedChunk
from caselens.security.audit import audit, list_audit


def require_access(request: Request) -> None:
    """Demo access gate. When ACCESS_TOKEN is set, every endpoint except /health requires a
    matching X-Access-Token header (or access_token cookie). Unset means the gate is off.
    This is not real auth; the tenant/role switcher remains the in-app demo control."""
    token = get_settings().access_token
    if not token or request.url.path == "/health":
        return
    provided = request.headers.get("X-Access-Token") or request.cookies.get("access_token")
    if provided != token:
        raise HTTPException(status_code=401, detail="Token de acceso inválido o ausente.")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    open_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(title="caselens", dependencies=[Depends(require_access)], lifespan=lifespan)

# Dev console runs on a separate origin; allow it to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def serialize_claim(claim: Claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "claimant_name": claim.claimant_name,
        "product": claim.product,
        "description": claim.description,
        "status": claim.status.value,
        "severity": claim.severity,
        "cost_cents": claim.cost_cents,
        "submitted_at": claim.submitted_at.isoformat(),
    }


def serialize_audit(entry: AuditEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "actor_user_id": entry.actor_user_id,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "metadata": entry.metadata,
        "created_at": entry.created_at.isoformat(),
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
    with db_connection() as conn:
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


@app.get("/claims")
def list_claims(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    status: str | None = None,
    product: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    try:
        status_filter = ClaimStatus(status) if status else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado desconocido: {status}") from None
    filters = ClaimFilters(status=status_filter, product=product, severity=severity)
    with db_connection() as conn:
        claims = ClaimsRepository(conn).list(ctx, filters)
        return {"claims": [serialize_claim(c) for c in claims]}


@app.get("/audit")
def get_audit(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)], limit: int = 100
) -> dict[str, Any]:
    with db_connection() as conn:
        entries = list_audit(ctx, conn=conn, limit=limit)
        return {"audit": [serialize_audit(e) for e in entries]}


@app.get("/dev/identities")
def dev_identities() -> dict[str, Any]:
    """DEV/DEMO only: list seeded tenants and their users to populate the console switcher.
    Stands in for real auth and is intentionally not tenant-scoped."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM tenants ORDER BY id")
            tenants = cur.fetchall()
            cur.execute("SELECT id, tenant_id, email, role FROM users ORDER BY tenant_id, id")
            users = cur.fetchall()
    members: dict[int, list[dict[str, Any]]] = {}
    for user_id, tenant_id, email, role in users:
        members.setdefault(tenant_id, []).append({"id": user_id, "email": email, "role": role})
    return {
        "tenants": [
            {"id": tenant_id, "name": name, "users": members.get(tenant_id, [])}
            for tenant_id, name in tenants
        ]
    }
