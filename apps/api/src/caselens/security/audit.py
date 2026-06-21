import json
from typing import Any

import psycopg

from caselens.data.models import TenantContext

_INSERT = (
    "INSERT INTO audit_log (tenant_id, actor_user_id, action, target_type, target_id, metadata) "
    "VALUES (%s, %s, %s, %s, %s, %s::jsonb)"
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
