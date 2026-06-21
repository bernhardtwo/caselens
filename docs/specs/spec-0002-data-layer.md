# spec-0002 — Data layer (claims, tenancy, RBAC, audit)

- Status: Draft
- Date: 2026-06-20
- Related: ADR-0003 (security-first), ADR-0005 (determinism boundary)

## Purpose

The security spine of the product. This layer holds the claims data, the tenant and user model, and enforces who can see and do what. Every agent tool built later sits on top of this. If scoping is wrong here, nothing above it is safe.

## Scope

**In**
- Tenant and user model, with roles for RBAC
- Claims table, synthetic and multi-tenant
- A data-access layer that enforces tenant scoping at the boundary, not in prompts or glue
- RBAC checks gating actions
- Append-only audit log of every scoped read and every action
- A synthetic generator for multi-tenant claims

**Out (later days)**
- The agent tools that consume this layer (Day 4-6)
- The UI (Day 6-8)

## Decisions in this spec

- **Multi-tenancy: single Postgres, row-level scoping via a `tenant_id` column** on every tenant-owned table. Simplest model that demonstrates the pattern clearly.
- **Scoping is enforced in code at the repository boundary.** Every data call takes a `TenantContext` and filters by `ctx.tenant_id`. There is no unscoped read path. This sits below the agent (ADR-0003), so a compromised prompt cannot cross tenants. (Optional defense-in-depth later: Postgres row-level security.)
- **RBAC**: a small role enum (e.g. `agent`, `reviewer`, `admin`) with permission checks gating actions like updating a claim's status.
- **Audit log**: an append-only table written on every scoped read and every action, recording actor, tenant, action, target, timestamp, and metadata.
- **Reuse the existing Postgres + pgvector database.** Add `tenants`, `users`, `claims`, `audit_log`. The RAG corpus (`documents`, `chunks`) stays global, since those are the company's shared policy documents; claims are tenant-scoped. Per-tenant document isolation is deferred.
- **Money stays deterministic** (ADR-0005): any claim cost is stored as a currency-aware integer (cents), never a float.

## Data model

- `tenants(id, name, created_at)`
- `users(id, tenant_id, email, role, created_at)`
- `claims(id, tenant_id, claimant_name, product, description, status, severity, cost_cents nullable, submitted_at)`
- `audit_log(id, tenant_id, actor_user_id, action, target_type, target_id, metadata jsonb, created_at)`

All tenant-owned tables carry `tenant_id`. Indexes on `tenant_id` where queried.

## Interfaces (Python)

- `TenantContext(tenant_id, user_id, role)` — passed to every data call.
- `ClaimsRepository`: `list(ctx, filters)`, `get(ctx, claim_id)`, `update_status(ctx, claim_id, status)` — all require `ctx`, all filter by `ctx.tenant_id`. A `get` for another tenant's claim returns nothing, never another tenant's row.
- `rbac`: `require_role(ctx, action)` / `can(ctx, action)`.
- `audit(ctx, action, target_type, target_id, metadata)` — called by the repository and actions.

## Tests (seed of the CI eval gate)

- **Cross-tenant isolation**: a `ctx` for tenant A cannot read or update tenant B's claims.
- **RBAC**: an unauthorized role is denied on a gated action.
- **Audit**: every scoped read and action writes exactly one audit row with the right actor and tenant.

## Cost

No Cohere calls in this layer; it is pure data and logic. Nothing to throttle.

## Tunables

Number of synthetic tenants and claims per tenant.
