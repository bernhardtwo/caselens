-- Data-layer schema (spec-0002): tenants, users, claims, append-only audit log.
-- Applied alongside the RAG core schema by `caselens-rag init-db`.
-- audit_log carries no FK so the trail survives tenant/user deletion.

CREATE TABLE IF NOT EXISTS tenants (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  BIGINT NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    email      TEXT NOT NULL,
    role       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS claims (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     BIGINT NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    claimant_name TEXT NOT NULL,
    product       TEXT NOT NULL,
    description   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'open',
    severity      TEXT NOT NULL,
    cost_cents    BIGINT,
    submitted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     BIGINT NOT NULL,
    actor_user_id BIGINT NOT NULL,
    action        TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS users_tenant_id_idx ON users (tenant_id);
CREATE INDEX IF NOT EXISTS claims_tenant_id_idx ON claims (tenant_id);
CREATE INDEX IF NOT EXISTS audit_log_tenant_id_idx ON audit_log (tenant_id);
