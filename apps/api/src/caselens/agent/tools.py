import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import cohere
import psycopg

from caselens.config.settings import Settings, get_settings
from caselens.data.models import Claim, ClaimFilters, ClaimStatus, TenantContext
from caselens.data.repository import ClaimsRepository
from caselens.rag.answer import build_answer
from caselens.rag.models import GroundedAnswer
from caselens.rag.retrieve import retrieve
from caselens.security import rbac
from caselens.security.audit import audit

# Deterministic claim status state machine (spec-0003 tunable).
ALLOWED_TRANSITIONS: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.OPEN: frozenset({ClaimStatus.IN_REVIEW, ClaimStatus.REJECTED}),
    ClaimStatus.IN_REVIEW: frozenset(
        {ClaimStatus.APPROVED, ClaimStatus.REJECTED, ClaimStatus.OPEN}
    ),
    ClaimStatus.APPROVED: frozenset({ClaimStatus.CLOSED}),
    ClaimStatus.REJECTED: frozenset({ClaimStatus.OPEN, ClaimStatus.CLOSED}),
    ClaimStatus.CLOSED: frozenset(),
}

_STATUS_VALUES = [status.value for status in ClaimStatus]


def can_transition(current: ClaimStatus, new: ClaimStatus) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, frozenset())


@dataclass
class ToolOutcome:
    result: dict[str, Any]
    grounded: GroundedAnswer | None = None
    action: dict[str, Any] | None = None
    denied: bool = False


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[..., ToolOutcome]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _claim_to_dict(claim: Claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "claimant_name": claim.claimant_name,
        "product": claim.product,
        "status": claim.status.value,
        "severity": claim.severity,
        "cost_cents": claim.cost_cents,
    }


def build_tools(
    ctx: TenantContext,
    *,
    conn: psycopg.Connection,
    co: cohere.ClientV2,
    settings: Settings | None = None,
) -> list[AgentTool]:
    """Tools bound to ctx. The tenant_id lives in this closure, never in a tool schema,
    so a prompt-injected request for another tenant still runs under the bound ctx."""
    settings = settings or get_settings()
    repo = ClaimsRepository(conn)

    def rag_search(query: str) -> ToolOutcome:
        chunks = retrieve(query, co=co, conn=conn, settings=settings)
        if not chunks:
            grounded = GroundedAnswer(text="", citations=[], sources=[])
        else:
            grounded = build_answer(query, chunks, co=co, settings=settings)
        return ToolOutcome(
            result={
                "answer": grounded.text,
                "sources": [os.path.basename(c.source_path) for c in grounded.sources],
                "citations": len(grounded.citations),
            },
            grounded=grounded,
        )

    def query_claims(
        status: str | None = None, product: str | None = None, severity: str | None = None
    ) -> ToolOutcome:
        filters = ClaimFilters(
            status=ClaimStatus(status) if status else None,
            product=product,
            severity=severity,
        )
        claims = repo.list(ctx, filters)
        return ToolOutcome(
            result={"claims": [_claim_to_dict(c) for c in claims], "count": len(claims)}
        )

    def get_claim(claim_id: int) -> ToolOutcome:
        claim = repo.get(ctx, int(claim_id))
        # Cross-tenant or missing both return null; never reveal which.
        return ToolOutcome(result={"claim": _claim_to_dict(claim) if claim else None})

    def update_claim_status(claim_id: int, new_status: str) -> ToolOutcome:
        claim_id = int(claim_id)
        if not rbac.can(ctx, rbac.UPDATE_STATUS):
            audit(
                ctx,
                "agent.update_denied",
                "claim",
                str(claim_id),
                {"reason": "rbac", "requested_status": new_status},
                conn=conn,
            )
            conn.commit()
            return ToolOutcome(
                result={"ok": False, "denied": True, "reason": "role not permitted"}, denied=True
            )
        try:
            target = ClaimStatus(new_status)
        except ValueError:
            return ToolOutcome(result={"ok": False, "reason": f"unknown status: {new_status}"})
        current = repo.get(ctx, claim_id)
        if current is None:
            return ToolOutcome(result={"ok": False, "reason": "claim not found"})
        if not can_transition(current.status, target):
            return ToolOutcome(
                result={
                    "ok": False,
                    "reason": f"transition {current.status.value} -> {target.value} not allowed",
                }
            )
        repo.update_status(ctx, claim_id, target)
        action = {
            "action": "update_claim_status",
            "claim_id": claim_id,
            "from": current.status.value,
            "to": target.value,
        }
        return ToolOutcome(result={"ok": True, **action}, action=action)

    return [
        AgentTool(
            "rag_search",
            "Search the company's global policy and product documents and return a grounded "
            "answer with citations. Use for warranty coverage, exclusions, procedures, or manuals.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The policy question to research."}
                },
                "required": ["query"],
            },
            rag_search,
        ),
        AgentTool(
            "query_claims",
            "List claims for the current tenant, optionally filtered. Only the current tenant's "
            "claims are ever returned.",
            {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": _STATUS_VALUES},
                    "product": {"type": "string"},
                    "severity": {"type": "string"},
                },
            },
            query_claims,
        ),
        AgentTool(
            "get_claim",
            "Fetch one claim by id for the current tenant. Returns nothing if the claim does not "
            "belong to the current tenant.",
            {
                "type": "object",
                "properties": {"claim_id": {"type": "integer"}},
                "required": ["claim_id"],
            },
            get_claim,
        ),
        AgentTool(
            "update_claim_status",
            "Change a claim's status for the current tenant. Permission-checked, limited to valid "
            "transitions, and audited.",
            {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "integer"},
                    "new_status": {"type": "string", "enum": _STATUS_VALUES},
                },
                "required": ["claim_id", "new_status"],
            },
            update_claim_status,
        ),
    ]
