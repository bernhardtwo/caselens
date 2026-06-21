import json
from typing import Any

import psycopg

from caselens.data.models import AuditEntry, TenantContext

_INSERT = (
    "INSERT INTO audit_log (tenant_id, actor_user_id, action, target_type, target_id, metadata) "
    "VALUES (%s, %s, %s, %s, %s, %s::jsonb)"
)

_SELECT = (
    "SELECT id, tenant_id, actor_user_id, action, target_type, target_id, metadata, created_at "
    "FROM audit_log WHERE tenant_id = %s ORDER BY id DESC LIMIT %s"
)


def audit(
    ctx: TenantContext,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict[str, Any] | None = None,
    *,
    conn: psycopg.Connection,
) -> None:
    """Append one row to the audit log. The caller owns the transaction (commit)."""
    with conn.cursor() as cur:
        cur.execute(
            _INSERT,
            (
                ctx.tenant_id,
                ctx.user_id,
                action,
                target_type,
                target_id,
                json.dumps(metadata or {}),
            ),
        )


def list_audit(
    ctx: TenantContext, *, conn: psycopg.Connection, limit: int = 100
) -> list[AuditEntry]:
    """Audit rows for the caller's tenant, newest first. Scoped; another tenant sees nothing."""
    with conn.cursor() as cur:
        cur.execute(_SELECT, (ctx.tenant_id, limit))
        rows = cur.fetchall()
    return [
        AuditEntry(
            id=row[0],
            tenant_id=row[1],
            actor_user_id=row[2],
            action=row[3],
            target_type=row[4],
            target_id=row[5],
            metadata=row[6] or {},
            created_at=row[7],
        )
        for row in rows
    ]
