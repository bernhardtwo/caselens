# spec-0004 — UI (agent console)

- Status: Draft
- Date: 2026-06-20
- Related: ADR-0002 (grounded citations), ADR-0003 (security-first), ADR-0005 (determinism)
- Builds on: spec-0003 (agent), spec-0002 (data layer)

## Purpose

The layer that makes everything demonstrable. A web console where you chat with the agent, watch it call its tools live, see the citations behind its answers, confirm actions before they commit, and inspect the audit trail. Crucially, it is also the demo control: switching tenant and role on screen shows the scoping and RBAC holding in real time, not just in tests.

## Scope

**In**
- A chat console (apps/web) talking to the FastAPI agent
- Live tool-call trace streamed as the agent works (SSE)
- A citations / sources panel for answers grounded in policy
- Human-in-the-loop confirmation before any mutation commits
- An audit view of the tool-calls and actions for the tenant
- A tenant / user / role switcher (dev auth) that doubles as the demo control

**Out (later days)**
- Real authentication and multi-user sessions
- The connector management UI (Day 8-9)

## Decisions in this spec

- **Frontend is Next.js 16 (App Router) + Tailwind v4 in apps/web**, talking to the FastAPI backend. Clean enterprise-console aesthetic; the live tool-call trace is the hero element, not a hidden log.
- **The agent gets an SSE streaming endpoint** (`POST /agent/stream`) that emits typed events as it runs: `tool_call`, `tool_result`, `answer`, `citations`, `action_proposed`. The existing non-streaming `POST /agent` stays for the eval and programmatic use. The loop yields events; the UI renders them as they arrive, so the agent's reasoning is visible.
- **Mutations are human-in-the-loop in interactive mode.** When the agent decides to change a claim, the interactive run does not commit it; it emits `action_proposed` with the intended change. The UI shows it and requires explicit confirmation. On confirm, a dedicated endpoint commits the action through the same guarded, audited path. The autonomous path (used by the eval) keeps executing directly. This makes the determinism boundary and the audit trail tangible: the agent proposes, a human approves, the system records.
- **Dev auth is a tenant/user/role switcher** that sets the `X-Tenant-Id / X-User-Id / X-Role` headers. It is both the stand-in for real auth and the demo control: switch tenant and the visible claims change; switch to a role without permission and the same action is refused on screen. The security properties become a live demo, not a claim.
- **The audit view reads the audit log** for the current tenant, showing each tool-call and action with actor and timestamp, including denied attempts.

## Backend additions

- `POST /agent/stream` — SSE, emits the typed events above.
- `POST /actions/confirm` — commits a proposed mutation (guarded by RBAC + allowed transition + audit).
- `GET /audit` — audit rows for the current tenant (scoped).
- `GET /claims` — scoped claims list, for context panels.

All read the tenant context from headers (the mock dependency), never from the body.

## Frontend (apps/web)

- A single console page: chat transcript, a live tool-call trace panel, a citations/sources panel, the action-confirmation prompt, an audit panel, and the tenant/role switcher in the header.
- Streams from `/agent/stream` and renders events incrementally.
- The action-confirmation prompt is unmissable and states exactly what will change.

## Out-of-scope reminders

No real login, no persistence of chat history beyond the session, no connector UI yet. This is the agent console that proves the platform works.

## Tunables

Which events are shown in the trace; how much of each tool result is surfaced; the set of roles offered in the switcher.
