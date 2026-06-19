# Project Brief — CaseLens (working name)

**A secure, deployable enterprise AI agent, built Cohere-native, that connects to a company's tools and data, answers questions with grounded citations, and takes guarded actions over sensitive operational data.**

Target role: Cohere — Forward Deployed Engineer, Agentic Platform (North).
Builder: Bernardo Vega. Timeline: ~12 days, finish before end of June 2026.

> Naming and domain are placeholders. Working domain: enterprise warranty-claims triage. Both are easy to rename before Day 1.

---

## 1. Thesis

A mini-"North": drop an AI agent into a simulated enterprise environment, connect it to that company's documents, database, and an external API, and let it answer and act over sensitive data while staying scoped, audited, and grounded in citations. The whole thing is containerized so it can run in any cloud or a customer VPC.

The build is Cohere-native on purpose: Command for the agent's reasoning and tool use, Embed 4 plus Rerank 4 for retrieval, and grounded generation with inline citations. Using Cohere's own stack is the single strongest signal for this role.

## 2. Why this project (FDE requirement mapping)

| FDE requirement | How this project proves it |
|---|---|
| Build and deploy agent-based applications | The whole product is a deployed multi-tool agent |
| Python, production-grade code | Python backend, tests, CI gate |
| Full-stack coding | Next.js workspace UI with live tool-calls and citations |
| Agents over sensitive enterprise data | Tenant/user scoping, RBAC, audit log on every action |
| Connect agents with workplace tools | Pluggable connectors: docs (RAG), database, external API |
| RAG / semantic search | Embed 4 + Rerank 4 + grounded citations via Command |
| Deploy in private or hybrid cloud | Portable container, cloud-agnostic, VPC-ready |
| Cloud platforms (Azure/AWS/GCP) | Live deploy to one cloud, scale-to-zero |
| Rapid, high-quality experiments | Agent eval harness wired into CI as a gate |

## 3. Scope

**In scope**
- Agent loop on Cohere Command (multi-step tool use)
- RAG: ingest → chunk → Embed 4 → vector store → retrieve → Rerank 4 → grounded answer with inline citations
- Connectors: document store (RAG), claims database, one mock external API
- Security posture: tenant/user data scoping enforced at the query layer, RBAC, audit log of every tool call and action
- Full-stack workspace UI: chat, live tool-calls, sources/citations panel, action confirmations, audit view
- Portable containerized deploy (scale-to-zero), secrets management, basic observability
- Agent eval harness as a CI gate

**Out of scope (deliberately, this is the Cohere tilt)**
- Model training / retraining / continuous-training pipelines
- Orchestration platforms (Airflow / Kubeflow / Vertex Pipelines)
- Heavy DevSecOps suite (SonarQube / Checkmarx)

**Hygiene, not headline**
- CI/CD (GitHub Actions + OIDC, reused from LedgerLens)
- Light IaC, container scan (Trivy)

## 4. Architecture (high level)

- **Frontend:** Next.js workspace UI. Streams the agent's tool-calls and renders citations.
- **Backend:** Python API. Hosts the agent loop and the connectors. Same-origin proxy to the frontend.
- **Agent:** Cohere Command Chat with tool use. Tools: `rag_search`, `query_claims` (tenant-scoped), `take_action` (guarded).
- **RAG:** Embed 4 for document and query embeddings; vector store (pgvector in Postgres); Rerank 4 on retrieved candidates; Command produces the grounded answer with inline citations.
- **Data:** Postgres. Synthetic claims plus synthetic policy/manual documents. Tenant and user model. All data access scoped by tenant.
- **Security:** RBAC, per-request scoping, secrets via environment / secret store, append-only audit log.
- **Deploy:** Docker multi-stage, deployed to a scale-to-zero container runtime. Cloud-agnostic by design.

## 5. Governing decisions (write these as ADRs on Day 1)

- **ADR-0001 — Cohere-native stack.** Command + Embed + Rerank, used directly, over a framework wrapper. LangGraph only if the agent graph genuinely needs it.
- **ADR-0002 — Grounded answers required.** Every agent answer over documents must carry inline citations; uncited claims are a defect.
- **ADR-0003 — Security-first by default.** Tenant scoping enforced at the data layer, RBAC, and an audit record for every tool call and action.
- **ADR-0004 — Portable deploy.** Cloud-agnostic container is the deliverable; the chosen cloud is just the first target.
- **ADR-0005 — Determinism boundary** (reused from LedgerLens). The agent reasons, explains, and decides; deterministic code performs the actual data reads, math, and actions.
- **ADR-0006 — Eval as a gate.** A golden set of cases gates CI; the agent does not ship if it regresses.

## 6. Twelve-day plan

| Days | Focus |
|---|---|
| 1 | Specs + ADRs, repo scaffold (Python backend + Next.js frontend), synthetic-data plan, CI green-shell, Cohere key wired (`CO_API_KEY`) with a Command + Embed + Rerank smoke test |
| 2-3 | RAG core: ingest → chunk → Embed 4 → pgvector → retrieve → Rerank 4 → grounded answer with citations. Retrieval eval set |
| 3-4 | Data layer: synthetic claims in Postgres, tenant/user model, RBAC, scoping enforced at the query layer |
| 4-6 | Agent: Command tool-use loop with `rag_search`, `query_claims`, `take_action`; audit log; agent eval set |
| 6-8 | Full-stack workspace UI: chat, live tool-calls, citations panel, action confirmations, audit view |
| 8-9 | Connector abstraction + a second connector (mock external API) to demonstrate the integration story |
| 9-10 | Portable deploy: Dockerize, deploy scale-to-zero, secrets, basic observability |
| 10-11 | CI/CD + eval gate + Trivy; README with the mapping table, architecture diagram, ADR index, security notes, and the "deploy into a customer environment" narrative |
| 11-12 | Demo + video walkthrough; tear down billable resources. Stretch: a second tenant to show isolation visually |

## 7. De-risk first

Get these green by Day 3, everything hangs off them:
1. RAG quality and citations (chunking, Embed 4, Rerank 4, grounded Chat output)
2. The Cohere tool-use loop (multi-step, reliable tool selection)
3. Tenant scoping enforced at the data layer (the security spine)

**If days slip, cut in this order:** the second connector and second tenant first, then UI polish. Never cut citations, scoping, or the agent eval, those are the differentiating signal.

## 8. Cost guardrails

- Cohere trial key: 1,000 calls/month, no card. Enough to build and test; add billing only for the demo if needed. Be call-careful during iteration. Env var is `CO_API_KEY`.
- Container runtime: scale-to-zero, near-free when idle.
- Postgres: small instance; stop it between demos.
- Tear down billable resources after the video, same discipline as LedgerLens.
