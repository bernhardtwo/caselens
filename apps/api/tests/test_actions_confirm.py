"""POST /actions/confirm tests against the local/CI Postgres (spec-0004)."""

import psycopg
import pytest
from fastapi import HTTPException

from caselens.api.app import ConfirmRequest, confirm_action
from caselens.data.db import apply_schema, connect
from caselens.data.models import ClaimStatus, Role, TenantContext

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
    ids: dict[str, int] = {}
    with conn.cursor() as cur:
        for key, name in (("a", "Tenant A"), ("b", "Tenant B")):
            cur.execute("INSERT INTO tenants (name) VALUES (%s) RETURNING id", (name,))
            ids[key] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
                (ids[key], f"reviewer@{key}", Role.REVIEWER.value),
            )
            ids[f"{key}_reviewer"] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s) RETURNING id",
                (ids[key], f"agent@{key}", Role.AGENT.value),
            )
            ids[f"{key}_agent"] = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO claims (tenant_id, claimant_name, product, "
                "description, status, severity) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (ids[key], "C", "P", "d", ClaimStatus.OPEN.value, "low"),
            )
            ids[f"{key}_claim"] = cur.fetchone()[0]
    conn.commit()
    return ids


def _status(conn: psycopg.Connection, claim_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM claims WHERE id = %s", (claim_id,))
        return cur.fetchone()[0]


def _count(conn: psycopg.Connection, action: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action = %s", (action,))
        return cur.fetchone()[0]


def test_confirm_commits_and_audits(conn):
    ids = _seed(conn)
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    result = confirm_action(ConfirmRequest(claim_id=ids["a_claim"], to_status="in_review"), ctx)
    assert result == {"ok": True, "claim_id": ids["a_claim"], "from": "open", "to": "in_review"}
    assert _status(conn, ids["a_claim"]) == "in_review"
    assert _count(conn, "claim.update_status") >= 1


def test_confirm_denied_for_agent_role_no_mutation(conn):
    ids = _seed(conn)
    ctx = TenantContext(ids["a"], ids["a_agent"], Role.AGENT)
    with pytest.raises(HTTPException) as exc:
        confirm_action(ConfirmRequest(claim_id=ids["a_claim"], to_status="in_review"), ctx)
    assert exc.value.status_code == 403
    assert _status(conn, ids["a_claim"]) == "open"
    assert _count(conn, "action.confirm_denied") == 1
    assert _count(conn, "claim.update_status") == 0


def test_confirm_cross_tenant_is_not_found(conn):
    ids = _seed(conn)
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    with pytest.raises(HTTPException) as exc:
        confirm_action(ConfirmRequest(claim_id=ids["b_claim"], to_status="in_review"), ctx)
    assert exc.value.status_code == 404
    assert _status(conn, ids["b_claim"]) == "open"


def test_confirm_invalid_transition_conflicts(conn):
    ids = _seed(conn)
    ctx = TenantContext(ids["a"], ids["a_reviewer"], Role.REVIEWER)
    with pytest.raises(HTTPException) as exc:
        confirm_action(ConfirmRequest(claim_id=ids["a_claim"], to_status="approved"), ctx)
    assert exc.value.status_code == 409
    assert _status(conn, ids["a_claim"]) == "open"
