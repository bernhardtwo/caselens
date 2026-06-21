"""Postgres-backed tests for tenant isolation, RBAC, and audit.

Run against the local compose DB (`docker compose -f infra/docker-compose.yml up -d`)
or the CI Postgres service. Skipped automatically when no database is reachable.
"""

import psycopg
import pytest

from caselens.data.db import apply_schema, connect
from caselens.data.models import ClaimStatus, Role, TenantContext
from caselens.data.repository import ClaimsRepository
from caselens.security.rbac import PermissionDeniedError

pytestmark = pytest.mark.integration


@pytest.fixture
def conn():
    try:
        connection = connect()
    except psycopg.OperationalError:
        pytest.skip("Postgres no disponible (levanta infra/docker-compose).")
    apply_schema(connection)
    with connection.cursor() as cur:
        cur.execute("TRUNCATE audit_log, claims, users, tenants RESTART IDENTITY CASCADE")
    connection.commit()
    yield connection
    connection.close()


def _seed(conn: psycopg.Connection) -> dict[str, int]:
    """Insert two tenants directly (no audit rows) and return their ids."""
    ids: dict[str, int] = {}
    with conn.cursor() as cur:
        for key, name in (("a", "Tenant A"), ("b", "Tenant B")):
            cur.execute("INSERT INTO tenants (name) VALUES (%s) RETURNING id", (name,))
            ids[key] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
                (ids[key], f"reviewer@{key}.example", Role.REVIEWER.value),
            )
            ids[f"{key}_reviewer"] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
                (ids[key], f"agent@{key}.example", Role.AGENT.value),
            )
            ids[f"{key}_agent"] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO claims "
                "(tenant_id, claimant_name, product, description, status, severity) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (ids[key], "Claimant", "Product", "desc", ClaimStatus.OPEN.value, "low"),
            )
            ids[f"{key}_claim"] = cur.fetchone()[0]
    conn.commit()
    return ids


def _audit_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log")
        return cur.fetchone()[0]


def test_get_does_not_cross_tenants(conn):
    ids = _seed(conn)
    repo = ClaimsRepository(conn)
    ctx_a = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    assert repo.get(ctx_a, ids["a_claim"]) is not None
    assert repo.get(ctx_a, ids["b_claim"]) is None


def test_list_only_returns_own_tenant(conn):
    ids = _seed(conn)
    repo = ClaimsRepository(conn)
    ctx_a = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    claims = repo.list(ctx_a)
    assert {c.id for c in claims} == {ids["a_claim"]}


def test_update_status_does_not_cross_tenants(conn):
    ids = _seed(conn)
    repo = ClaimsRepository(conn)
    ctx_a = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    assert repo.update_status(ctx_a, ids["b_claim"], ClaimStatus.APPROVED) is None
    ctx_b = TenantContext(ids["b"], ids["b_reviewer"], Role.REVIEWER)
    assert repo.get(ctx_b, ids["b_claim"]).status == ClaimStatus.OPEN


def test_rbac_denies_agent_update_and_writes_no_audit(conn):
    ids = _seed(conn)
    repo = ClaimsRepository(conn)
    ctx_agent = TenantContext(ids["a"], ids["a_agent"], Role.AGENT)
    with pytest.raises(PermissionDeniedError):
        repo.update_status(ctx_agent, ids["a_claim"], ClaimStatus.APPROVED)
    reviewer_ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    assert repo.get(reviewer_ctx, ids["a_claim"]).status == ClaimStatus.OPEN
    assert _audit_count(conn) == 1  # only the get above; the denied update wrote nothing


def test_audit_writes_one_row_per_operation_with_actor_and_tenant(conn):
    ids = _seed(conn)
    repo = ClaimsRepository(conn)
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    repo.get(ctx, ids["a_claim"])
    repo.list(ctx)
    repo.update_status(ctx, ids["a_claim"], ClaimStatus.APPROVED)
    with conn.cursor() as cur:
        cur.execute("SELECT tenant_id, actor_user_id, target_type FROM audit_log ORDER BY id")
        rows = cur.fetchall()
    assert len(rows) == 3
    assert all(r == (ids["a"], ids["a_reviewer"], "claim") for r in rows)
