"""GET /claims and GET /audit scoping tests against the local/CI Postgres (spec-0004)."""

import psycopg
import pytest

from caselens.api.app import get_audit, list_claims
from caselens.data.db import apply_schema, connect
from caselens.data.models import ClaimStatus, Role, TenantContext
from caselens.security.audit import audit

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


def _seed(conn: psycopg.Connection) -> dict:
    ids: dict = {}
    with conn.cursor() as cur:
        for key, name, n_claims in (("a", "Tenant A", 2), ("b", "Tenant B", 1)):
            cur.execute("INSERT INTO tenants (name) VALUES (%s) RETURNING id", (name,))
            ids[key] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
                (ids[key], f"reviewer@{key}", Role.REVIEWER.value),
            )
            ids[f"{key}_user"] = cur.fetchone()[0]
            claim_ids = []
            for _ in range(n_claims):
                cur.execute(
                    "INSERT INTO claims (tenant_id, claimant_name, product, "
                    "description, status, severity) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                    (ids[key], "C", "P", "d", ClaimStatus.OPEN.value, "low"),
                )
                claim_ids.append(cur.fetchone()[0])
            ids[f"{key}_claims"] = claim_ids
    conn.commit()
    return ids


def test_claims_are_tenant_scoped(conn):
    ids = _seed(conn)
    ctx_a = TenantContext(ids["a"], ids["a_user"], Role.REVIEWER)
    returned = {claim["id"] for claim in list_claims(ctx_a)["claims"]}
    assert returned == set(ids["a_claims"])
    assert all(bid not in returned for bid in ids["b_claims"])


def test_audit_is_scoped_newest_first_and_includes_denied(conn):
    ids = _seed(conn)
    ctx_a = TenantContext(ids["a"], ids["a_user"], Role.REVIEWER)
    ctx_b = TenantContext(ids["b"], ids["b_user"], Role.REVIEWER)
    audit(ctx_a, "agent.tool_call", "tool", "query_claims", {}, conn=conn)
    audit(ctx_a, "action.confirm_denied", "claim", "1", {"reason": "rbac"}, conn=conn)
    audit(ctx_b, "agent.tool_call", "tool", "query_claims", {}, conn=conn)
    conn.commit()

    rows_a = get_audit(ctx_a)["audit"]
    assert len(rows_a) == 2  # only tenant A's rows
    assert [row["id"] for row in rows_a] == sorted((row["id"] for row in rows_a), reverse=True)
    assert "action.confirm_denied" in {row["action"] for row in rows_a}

    rows_b = get_audit(ctx_b)["audit"]
    assert len(rows_b) == 1


def test_claims_filter_passes_through(conn):
    ids = _seed(conn)
    ctx_a = TenantContext(ids["a"], ids["a_user"], Role.REVIEWER)
    assert list_claims(ctx_a, status="approved")["claims"] == []
    assert len(list_claims(ctx_a, status="open")["claims"]) == 2
