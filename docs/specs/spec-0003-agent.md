# spec-0003 — Agent (Command tool-use loop)

- Status: Draft
- Date: 2026-06-20
- Related: ADR-0001 (Cohere-native), ADR-0002 (grounded citations), ADR-0003 (security-first), ADR-0005 (determinism), ADR-0006 (eval gate)
- Builds on: spec-0001 (RAG), spec-0002 (data layer)

## Purpose

The centerpiece. A Cohere Command tool-use loop that takes a user message inside a tenant context, reasons about it, calls tools to retrieve policy, query scoped claims, and take guarded actions, and returns a grounded answer with citations. Every tool call is audited. This is where the RAG and the data layer come together as one agent.

## Scope

**In**
- A Command Chat tool-use loop (multi-step) bound to a `TenantContext`
- Three tools: `rag_search`, `query_claims`, `update_claim_status`
- Tenant scoping bound at tool-construction time, never supplied by the model
- Guarded actions: RBAC + allowed transitions + audit
- Grounded citations on any answer drawn from documents
- An agent eval golden set, including a cross-tenant attempt that must be refused
- A FastAPI endpoint to invoke the agent

**Out (later days)**
- The UI and live streaming of tool-calls (Day 6-8)
- The connector abstraction (Day 8-9)

## Decisions in this spec

- **The agent is built directly on Command Chat with tool use** (ADR-0001). A single tool-use loop. No LangGraph unless the control flow genuinely outgrows it.
- **The TenantContext is bound when the tools are constructed** (`build_tools(ctx)`), not passed by the model. The model never sees or supplies a `tenant_id`. This is the load-bearing security property: a prompt-injected request to read another tenant's claims still runs under the bound `ctx`, so it returns nothing. Scoping lives below the model (ADR-0003).
- **Determinism boundary** (ADR-0005): the model decides which tools to call and explains the result; the tools (deterministic code) do the retrieval, the scoped reads, and the mutations. The model never mutates state directly.
- **`update_claim_status` is guarded**: it checks RBAC (`require_role`), allows only valid status transitions (a small deterministic state machine), and writes an audit row. The model proposes; the tool enforces.
- **Every tool call is audited**, not just actions, via the `audit()` helper from spec-0002.
- **Grounded citations are required** on answers that use `rag_search` results (ADR-0002).
- **Invocation is a FastAPI endpoint** (`POST /agent`). Non-streaming first; SSE streaming of tool-calls is deferred to the UI day.

## Tools

- `rag_search(query)` → passages + citations. Read-only over the global policy corpus. Reuses spec-0001 retrieve/answer.
- `query_claims(filters)` / `get_claim(claim_id)` → claims for the bound tenant only, via `ClaimsRepository` with `ctx`. A claim id from another tenant returns nothing.
- `update_claim_status(claim_id, new_status)` → guarded action: RBAC check, allowed-transition check, mutation via the repository, audit row.

## Interfaces (Python)

- `build_tools(ctx: TenantContext) -> list[Tool]` — tools bound to `ctx`.
- `run_agent(ctx: TenantContext, message: str) -> AgentResult`
- `AgentResult = { answer, citations, sources, tool_trace, actions_taken }` — `tool_trace` lists each tool call and its result for transparency.
- `POST /agent` body `{ message }`; the tenant context comes from the (mocked for now) authenticated session, never from the body.

## Eval (agent golden set, seeds the CI gate)

Scenarios, each asserting tool selection, scoping, and audit:
- A policy question → `rag_search` → grounded answer with a citation.
- A claims question for the agent's own tenant → `query_claims` → correct, scoped results.
- A status update the role is allowed to make → `update_claim_status` → mutation + audit row.
- A status update the role is NOT allowed to make → refused by RBAC, no mutation.
- A request for another tenant's claim → returns nothing; the attempt is auditable. Scoping is never crossed.

## Cost

Agent runs use Command plus the RAG calls (embed + rerank) per `rag_search`. The eval set will hit the trial 10/min limit, so reuse the throttle pattern from the retrieval eval.

## Tunables

Max tool-use iterations per turn; the model and temperature; the set of allowed status transitions.
