# CaseLens

A Cohere-native enterprise agent for warranty-claims triage: grounded RAG with native citations, tenant-scoped data, guarded actions, and an audit trail on every step.

## Live demo

A live instance is up at https://caselens-web.mangowave-84b15261.centralus.azurecontainerapps.io

The demo sits behind an access token, so ask me for it over the same channel where I shared the repo. I keep it out of this README on purpose. One honest heads up: the first load can take a few seconds, because the apps scale to zero when idle and need a moment to spin back up.

## What it is and why

Enterprises want to put an agent in front of sensitive operational data and let it both answer questions and take actions. The hard part is not the chat, it is doing this safely: the agent must stay inside one tenant's data, refuse actions a role cannot take, ground its answers in real documents, and leave a reviewable trail. CaseLens is a focused build of that pattern over a simulated warranty-claims domain. It runs a Cohere Command tool-use loop that retrieves policy with RAG, reads claims scoped to the caller's tenant, and proposes status changes behind RBAC and a deterministic state machine. Scoping lives below the model, citations are produced by Cohere over the final answer, and every tool call and action is written to an append-only audit log.

## Console

![console](docs/assets/console.png)

_Placeholder: a screenshot or GIF of the console will be added here by the maintainer._

## Architecture

The system is a small monorepo: a FastAPI backend that hosts the agent and the data layer, and a Next.js console that streams the agent's work.

```
Browser console (apps/web)
   |  POST /agent/stream  (Server-Sent Events)
   v
FastAPI (apps/api)
   |  ctx = TenantContext from X-Tenant-Id / X-User-Id / X-Role headers (mock auth)
   |  run_agent_events(ctx, message)
   v
Command tool-use loop, tools bound to ctx
   |                       |                          |
   rag_search        query_claims / get_claim    update_claim_status
   (Embed + Rerank)  (tenant-scoped reads)       (RBAC + transitions + audit)
   |                       |                          |
   pgvector + Cohere   ClaimsRepository            ClaimsRepository
                       + audit_log                 + audit_log
   v
final Command turn receives the passages as documents=,
returns the grounded answer with native citations
```

**Agent loop.** `run_agent_events(ctx, message, interactive)` is a generator that runs Command Chat with tool use and yields typed events as they happen: `tool_call`, `tool_result`, `answer`, `citations`, and `action_proposed`. The non-streaming `run_agent` is built on top of the same generator and collects the events into a single result, so the API and the eval share one code path. The loop honors the determinism boundary (ADR-0005): the model reasons, selects tools, and explains, while deterministic Python does the reads and the mutations.

**Tools.** Four tools, bound to the tenant context when they are constructed:

- `rag_search(query)`: retrieval over the global policy corpus. It returns the reranked passages, it does not compose prose.
- `query_claims(filters)` and `get_claim(claim_id)`: tenant-scoped reads of claims. A claim id from another tenant returns nothing, without revealing whether it exists.
- `update_claim_status(claim_id, new_status)`: a guarded write. It checks RBAC, validates the transition against a small deterministic state machine, mutates through the repository, and writes an audit row.

**RAG with native citations (ADR-0007).** Ingestion chunks the markdown corpus, embeds with Embed 4, and stores vectors in pgvector. Retrieval embeds the query, runs a cosine vector search for the top candidates, and reranks with rerank-v3.5. For the agent, the final Command turn receives the retrieved passages as `documents=`, so Cohere produces the answer with native inline citations whose character offsets map to the text the model actually generated. Each citation maps back to its source passages. The standalone RAG answer path used by the CLI and the retrieval eval keeps its own single-shot compose step; the agent path grounds inside the loop.

**Data layer.** Postgres holds `tenants`, `users`, `claims`, and an append-only `audit_log`, alongside the RAG `documents` and `chunks`. Every tenant-owned table carries a `tenant_id`. Access goes through a repository whose every method takes a `TenantContext` and filters by `ctx.tenant_id`. Money is stored as integer cents, never a float (ADR-0005).

**Console.** A single client page streams `/agent/stream` by reading the `fetch` `ReadableStream` and parsing the SSE records itself, because `EventSource` is GET only. It renders the live tool-call trace as the primary element, the grounded answer with citation spans highlighted inline by character offset, and a sources panel where hovering a citation highlights its source and back.

## Security model

Security is the point of the project, not a layer added at the end. Three properties carry it.

**The tenant context is bound below the model.** Tools are created by `build_tools(ctx)`, which closes over `ctx.tenant_id`. The tenant id never appears in any tool's JSON schema and is never supplied by the model. This is the load-bearing property: a prompt injection that tells the agent to read another tenant's claims still runs under the bound `ctx`, so the repository filters to the caller's tenant and the call returns nothing. Scoping cannot be talked around, because the model has no channel to express a different tenant. The repository enforces the same scoping at the query boundary, and a cross-tenant `get` returns `None` rather than another tenant's row, so existence is not even leaked.

**RBAC at the action boundary.** Roles are `agent`, `reviewer`, and `admin`. Reads are open to the tenant; status changes are gated. The single gated mutation path checks `require_role` before it mutates, so an unauthorized role is refused whether the request comes from the autonomous agent or from the human confirmation endpoint. A denied attempt is recorded, not silently dropped.

**Append-only audit and human-in-the-loop.** Every tool call is audited, every scoped read and mutation is audited, and every RBAC denial is audited, all scoped to the tenant. The audit log is written by inserts only; there is no update or delete path in code, and the table carries no foreign key so the trail survives row deletion. Mutations are human-in-the-loop in the interactive (console) mode: instead of committing, the agent emits `action_proposed` with the intended change, and the change commits only when a human confirms it through `POST /actions/confirm`, which runs the same RBAC, transition, and audit checks. The autonomous mode used by the eval executes directly. The behavior is a single flag on one loop, not two copies.

These properties are covered by tests: cross-tenant isolation, schema-has-no-tenant-id, RBAC denial with audit, and one audit row per scoped read and per action.

## Cohere-native stack (ADR-0001)

The agent is built directly on Cohere primitives, with no framework wrapper between the code and the API. Model ids are configured in `apps/api/src/caselens/config/settings.py`:

- Command for reasoning and tool use: `command-a-03-2025`
- Embed 4 for document and query embeddings: `embed-v4.0`
- Rerank for retrieval reranking: `rerank-v3.5`

Grounded generation uses Cohere's native citations. A live smoke test for the three endpoints lives at `apps/api/scripts/smoke_cohere.py`.

## Evaluation and quality gates

Two golden-set harnesses live under `eval/`:

- **Retrieval eval** (`eval/run_retrieval_eval.py`, 13 cases in `eval/golden/retrieval.jsonl`): reports recall@k and rerank lift (rank before versus after rerank), with an optional grounded-answer citation check via `--answers`.
- **Agent eval** (`eval/run_agent_eval.py`, 5 scenarios in `eval/golden/agent.jsonl`): asserts tool selection, scoping, RBAC, and citations. The set includes the security scenarios: an RBAC-denied update that must be refused, and a cross-tenant claim request that must return nothing.

Both harnesses call Cohere, so they throttle with a `--sleep` flag to respect the trial rate limit, and both run locally with a key and a populated database. They are not yet wired into CI as a blocking gate (planned, ADR-0006).

What gates CI today is the test suite and the linters. GitHub Actions runs `ruff check`, `ruff format --check`, and `pytest` for the API, against a pgvector Postgres service so the tenant-isolation, RBAC, and audit integration tests run, plus `pnpm lint` and `pnpm build` for the web. The pytest suite drives the agent loop and the SSE stream with a mocked Command, so it stays green without a Cohere key. No metrics are quoted here because none are recorded in the repo; run the harnesses to produce them.

## Tech stack

- **Backend:** Python 3.11+, FastAPI, uvicorn, the Cohere SDK, pydantic-settings, psycopg 3. Postgres with the pgvector extension. Managed with uv; linted and formatted with ruff; tested with pytest.
- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind v4, pnpm. State with React hooks, icons as inline SVG, no UI framework.
- **Infra and CI:** Docker Compose for local Postgres (`pgvector/pgvector:pg16`), GitHub Actions for CI.

## Repository layout

```
apps/api/          FastAPI backend
  src/caselens/
    agent/         tool-use loop (loop.py) and the ctx-bound tools (tools.py)
    rag/           ingest, embed, retrieve, rerank, grounded answer, CLI
    data/          schema.sql, models, tenant-scoped repository, synthetic generator
    security/      rbac.py, audit.py
    api/app.py     HTTP endpoints
    config/        settings
  tests/           unit and Postgres-backed integration tests
  scripts/         Cohere smoke test
apps/web/          Next.js console (chat, tool-call trace, inline citations, sources)
data/corpus/       8 synthetic policy and product documents (markdown)
docs/adr/          architecture decision records (0001-0007)
docs/specs/        specs (0000 brief, 0001 RAG, 0002 data, 0003 agent, 0004 UI)
eval/              retrieval and agent golden sets and runners
infra/             docker-compose and pgvector init
```

## Getting started

**Prerequisites:** Docker, [uv](https://docs.astral.sh/uv/), Node 22 with pnpm 10, and a Cohere API key.

The HTTP API and the evals need a Cohere key. The data and panel endpoints (`/claims`, `/audit`, `/actions/confirm`) need only Postgres.

1. **Start Postgres.** The compose file exposes `${POSTGRES_PORT:-5432}`. This setup uses 5433 to avoid clashing with a local Postgres. `--wait` blocks until the healthcheck passes.

   ```bash
   POSTGRES_PORT=5433 docker compose -f infra/docker-compose.yml up -d --wait
   ```

2. **Configure environment.** Put these in `apps/api/.env` (loaded automatically) or export them. `DATABASE_URL` must match the port above.

   ```bash
   CO_API_KEY=your-cohere-key
   DATABASE_URL=postgresql://caselens:caselens@localhost:5433/caselens
   ```

3. **Create the schema.**

   ```bash
   uv run --project apps/api caselens-rag init-db
   ```

   On a freshly created volume, Postgres restarts once while it initializes, so a very early `init-db` can race the startup and fail to connect. Starting with `up -d --wait` avoids it; otherwise just run `init-db` again.

4. **Ingest the corpus** (uses Embed 4, needs the key). Defaults to `data/corpus/*.md`.

   ```bash
   uv run --project apps/api caselens-rag ingest
   ```

5. **Seed synthetic tenants, users, and claims.**

   ```bash
   uv run --project apps/api caselens-seed --reset
   ```

6. **Run the API** on port 8000.

   ```bash
   uv run --project apps/api uvicorn caselens.api.app:app --reload
   ```

7. **Run the console** on port 3000, from `apps/web`. The browser calls the web's own
   `/api/*`, which a Next route handler proxies to the API at `API_INTERNAL_URL` (default
   `http://localhost:8000`), so there is no CORS and no API URL baked into the build.

   ```bash
   cd apps/web
   pnpm install
   pnpm dev
   ```

   Open http://localhost:3000.

**Tests and gates.**

```bash
# API: unit plus integration; integration tests skip if no Postgres is reachable
uv run --project apps/api pytest
# Web
cd apps/web && pnpm lint && pnpm build
```

**Evals** (need the key and a seeded, ingested database):

```bash
uv run --project apps/api python eval/run_retrieval_eval.py --answers
uv run --project apps/api python eval/run_agent_eval.py
```

A one-shot RAG query from the CLI is also available:

```bash
uv run --project apps/api caselens-rag query "What does the warranty cover for a solar inverter?"
```

## Configuration

| Variable | Side | Default | Purpose |
|---|---|---|---|
| `CO_API_KEY` | api | none | Cohere key for Command, Embed, and Rerank. Needed for ingest, `/agent`, `/agent/stream`, and the evals. |
| `DATABASE_URL` | api | `postgresql://caselens:caselens@localhost:5432/caselens` | Postgres connection string. Point it at 5433 when using `POSTGRES_PORT=5433`. |
| `WEB_ORIGIN` | api | `http://localhost:3000` | Origin allowed by CORS for the browser console. |
| `ACCESS_TOKEN` | api | none | Shared token for the hosted-demo gate. When set, every endpoint except `/health` requires `X-Access-Token`; unset means open. |
| `POSTGRES_PORT` | infra | `5432` | Host port for the Postgres container. |
| `API_INTERNAL_URL` | web | `http://localhost:8000` | Upstream API for the web's same-origin `/api` proxy. Dev: `localhost:8000`; prod compose: `http://api:8000`. |

Retrieval and agent behavior are tunable in `settings.py`: vector top-k (20), rerank top-n (5), chunk size and overlap, embedding dimension (1536), agent max iterations (6), and temperature (0.2).

## Hosted demo access gate

The hosted demo can sit behind a lightweight shared-token gate so the trial Cohere key is not exposed to open traffic. It activates only when `ACCESS_TOKEN` is set on the API (via `infra/.env.prod`): every endpoint except `/health` then requires a matching `X-Access-Token` header (or `access_token` cookie), returning 401 otherwise. The console prompts for the token once, stores it in `sessionStorage`, and attaches it to every call, including the SSE stream, through the same-origin `/api` proxy. With `ACCESS_TOKEN` unset the gate is off and local dev runs without friction. This is a demo gate, not real authentication; the tenant/role switcher remains the in-app control.

## Design decisions

The project is decision-driven: each major choice has an ADR, and each layer has a spec.

**ADRs** (`docs/adr/`): 0001 Cohere-native stack, 0002 grounded citations required, 0003 security-first by default, 0004 portable cloud-agnostic deploy, 0005 determinism boundary, 0006 evaluation as a CI gate, 0007 native grounded citations over the final answer (refines 0002).

**Specs** (`docs/specs/`): 0000 project brief, 0001 RAG core, 0002 data layer, 0003 agent, 0004 UI console.

## Status and roadmap

**Implemented**

- RAG core: ingest, chunk, Embed 4, pgvector, retrieve, rerank-v3.5, grounded answers with citations, and a retrieval eval harness.
- Data layer: tenants, users, claims, and an append-only audit log, with a tenant-scoped repository, RBAC, audit helpers, and a synthetic multi-tenant generator with a seed CLI.
- Agent: a Command tool-use loop with the four tools, native grounded citations over the final answer, an audit record for every tool call and every denied attempt, and interactive versus autonomous modes.
- API: `/health`, `/agent`, `/agent/stream` (SSE), `/actions/confirm`, `/audit`, `/claims`, with CORS and mock header-based auth.
- Console: chat, a live tool-call trace, inline native citations, and a sources panel.
- An agent eval harness including the security scenarios, and CI running the linters and the test suite (with a Postgres service) for both apps.

**Planned**

- Console: the action-confirmation prompt, the audit view, and the tenant/user/role switcher. The backend endpoints exist; the UI for them is the next slice.
- Connectors: the connector abstraction and a second connector (a mock external API). `connectors/` is currently an empty placeholder.
- Portable deploy: an application Dockerfile, a scale-to-zero target, secrets handling, and basic observability (ADR-0004). Only the local Postgres compose exists today.
- Hardening: wiring the golden evals into CI as a blocking gate (ADR-0006), Postgres row-level security as defense in depth, per-tenant document isolation, real authentication in place of the mock headers, and a container scan.
