from typing import Any

import psycopg

from caselens.security import rbac
from caselens.security.audit import audit

from .models import Claim, ClaimFilters, ClaimStatus, TenantContext

_COLUMNS = (
    "id, tenant_id, claimant_name, product, description, status, severity, cost_cents, submitted_at"
)

# Every read/write path is scoped by tenant_id. There is no unscoped query here.
_GET_SQL = f"SELECT {_COLUMNS} FROM claims WHERE id = %(id)s AND tenant_id = %(tenant_id)s"
_UPDATE_SQL = (
    f"UPDATE claims SET status = %(status)s "
    f"WHERE id = %(id)s AND tenant_id = %(tenant_id)s RETURNING {_COLUMNS}"
)


def build_list_query(
    ctx: TenantContext, filters: ClaimFilters | None
) -> tuple[str, dict[str, Any]]:
    sql = f"SELECT {_COLUMNS} FROM claims WHERE tenant_id = %(tenant_id)s"
    params: dict[str, Any] = {"tenant_id": ctx.tenant_id}
    if filters and filters.status is not None:
        sql += " AND status = %(status)s"
        params["status"] = filters.status.value
    if filters and filters.product is not None:
        sql += " AND product = %(product)s"
        params["product"] = filters.product
    if filters and filters.severity is not None:
        sql += " AND severity = %(severity)s"
        params["severity"] = filters.severity
    sql += " ORDER BY id"
    return sql, params


def _row_to_claim(row: tuple[Any, ...]) -> Claim:
    return Claim(
        id=row[0],
        tenant_id=row[1],
        claimant_name=row[2],
        product=row[3],
        description=row[4],
        status=ClaimStatus(row[5]),
        severity=row[6],
        cost_cents=row[7],
        submitted_at=row[8],
    )


def _filters_metadata(filters: ClaimFilters | None) -> dict[str, Any]:
    if filters is None:
        return {}
    return {
        "status": filters.status.value if filters.status else None,
        "product": filters.product,
        "severity": filters.severity,
    }


class ClaimsRepository:
    """Tenant-scoped access to claims. Every method requires a TenantContext."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def list(self, ctx: TenantContext, filters: ClaimFilters | None = None) -> list[Claim]:
        rbac.require_role(ctx, rbac.READ)
        sql, params = build_list_query(ctx, filters)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        claims = [_row_to_claim(row) for row in rows]
        audit(
            ctx,
            rbac.READ,
            "claim",
            None,
            {"count": len(claims), "filters": _filters_metadata(filters)},
            conn=self._conn,
        )
        self._conn.commit()
        return claims

    def get(self, ctx: TenantContext, claim_id: int) -> Claim | None:
        rbac.require_role(ctx, rbac.READ)
        with self._conn.cursor() as cur:
            cur.execute(_GET_SQL, {"id": claim_id, "tenant_id": ctx.tenant_id})
            row = cur.fetchone()
        claim = _row_to_claim(row) if row else None
        audit(ctx, rbac.READ, "claim", str(claim_id), {"found": claim is not None}, conn=self._conn)
        self._conn.commit()
        return claim

    def update_status(self, ctx: TenantContext, claim_id: int, status: ClaimStatus) -> Claim | None:
        rbac.require_role(ctx, rbac.UPDATE_STATUS)
        status = ClaimStatus(status)
        with self._conn.cursor() as cur:
            cur.execute(
                _UPDATE_SQL,
                {"status": status.value, "id": claim_id, "tenant_id": ctx.tenant_id},
            )
            row = cur.fetchone()
        claim = _row_to_claim(row) if row else None
        audit(
            ctx,
            rbac.UPDATE_STATUS,
            "claim",
            str(claim_id),
            {"status": status.value, "applied": claim is not None},
            conn=self._conn,
        )
        self._conn.commit()
        return claim
