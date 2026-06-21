# spec-0005 — Portable deploy

- Status: Draft
- Date: 2026-06-20
- Related: ADR-0004 (portable deploy), ADR-0003 (security-first)
- Builds on: everything

## Purpose

Package CaseLens as a portable container deployment. It runs anywhere with Docker, deploys to Azure Container Apps as the concrete target, and stays cloud-agnostic so the same images could move to Cloud Run. This turns the working local demo into a running, shareable instance.

## Scope

**In**
- Dockerfiles for apps/api and apps/web (multi-stage, minimal runtime images)
- A production docker-compose (api + web + postgres/pgvector) that brings up the whole stack with one command, including an idempotent bootstrap (schema + corpus ingest + seed)
- Config via env and secrets (CO_API_KEY, DATABASE_URL, NEXT_PUBLIC_API_URL); a prod .env.example
- A lightweight access gate for the hosted demo, given the trial key's limits
- A documented deploy to Azure Container Apps, with a note on Cloud Run portability
- Health checks

**Out (not now)**
- A CI/CD auto-deploy pipeline, autoscaling tuning, and IaC that provisions the managed database (documented, not automated)

## Decisions

- **Two Dockerfiles.** api: uv multi-stage build, slim runtime. web: pnpm build to the Next.js standalone output, slim runtime. Nothing cloud-specific in either image.
- **The portable artifact is a production docker-compose** bringing up api + web + postgres(pgvector) plus a bootstrap step, in one command, on any machine with Docker. This is the cloud-agnostic story made concrete, not just asserted.
- **The container needs only a Postgres-with-pgvector (via DATABASE_URL) and CO_API_KEY.** On Azure: ACA for api and web, Azure Database for PostgreSQL flexible server with pgvector, ACA secrets. The same images run on Cloud Run with Cloud SQL. Portability is a property of the build, not a separate effort.
- **Bootstrap runs idempotently at deploy** (init container or entrypoint): init-db, then ingest, then seed, so a fresh or re-deployed instance has data. This requires making the seed idempotent (truncate/upsert), which closes the deferred debt since it is now needed.
- **The hosted demo sits behind a lightweight access gate** (a shared token via env, checked at the edge of api and web). It is not a real auth system; it is enough to share the URL selectively so the trial key is not exposed to open traffic. The tenant/role switcher remains the in-app demo control.
- **Secrets are never baked into images**; they are passed as env/secrets at runtime.
- **The web reaches the api via NEXT_PUBLIC_API_URL**; CORS allows the deployed web origin.

## Consequences

- `docker compose -f infra/docker-compose.prod.yml up` runs the full stack anywhere.
- The Azure path is documented and reproducible (az CLI or Bicep).
- The seed becomes idempotent, which also makes local resets cleaner.
- A shareable, access-gated demo URL, suitable to show without burning the trial quota on open traffic.

## Tunables

The access token; container resource sizes; whether the bootstrap reseeds or preserves data on redeploy.
