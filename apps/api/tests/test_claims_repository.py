from caselens.data import repository
from caselens.data.models import ClaimFilters, ClaimStatus, Role, TenantContext
from caselens.data.repository import build_list_query


def _ctx() -> TenantContext:
    return TenantContext(tenant_id=7, user_id=3, role=Role.REVIEWER)


def test_every_query_path_is_tenant_scoped():
    # Guards the security invariant: no read or write path without a tenant predicate.
    assert "tenant_id = %(tenant_id)s" in repository._GET_SQL
    assert "tenant_id = %(tenant_id)s" in repository._UPDATE_SQL
    sql, params = build_list_query(_ctx(), None)
    assert "tenant_id = %(tenant_id)s" in sql
    assert params["tenant_id"] == 7


def test_list_query_applies_filters_and_keeps_scope():
    filters = ClaimFilters(status=ClaimStatus.OPEN, product="Solar Inverter X1", severity="high")
    sql, params = build_list_query(_ctx(), filters)
    assert "tenant_id = %(tenant_id)s" in sql
    assert "status = %(status)s" in sql and params["status"] == "open"
    assert "product = %(product)s" in sql and params["product"] == "Solar Inverter X1"
    assert "severity = %(severity)s" in sql and params["severity"] == "high"


def test_list_query_omits_absent_filters():
    sql, params = build_list_query(_ctx(), ClaimFilters(status=ClaimStatus.APPROVED))
    assert "status = %(status)s" in sql
    assert "product = %(product)s" not in sql
    assert "severity = %(severity)s" not in sql
    assert set(params) == {"tenant_id", "status"}
