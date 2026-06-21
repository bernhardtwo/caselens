import pytest

from caselens.data.models import Role, TenantContext
from caselens.security.rbac import READ, UPDATE_STATUS, PermissionDeniedError, can, require_role


def _ctx(role: Role) -> TenantContext:
    return TenantContext(tenant_id=1, user_id=1, role=role)


def test_agent_can_read_but_not_update():
    assert can(_ctx(Role.AGENT), READ)
    assert not can(_ctx(Role.AGENT), UPDATE_STATUS)


def test_reviewer_and_admin_can_update():
    assert can(_ctx(Role.REVIEWER), UPDATE_STATUS)
    assert can(_ctx(Role.ADMIN), UPDATE_STATUS)


def test_require_role_denies_unauthorized():
    with pytest.raises(PermissionDeniedError):
        require_role(_ctx(Role.AGENT), UPDATE_STATUS)


def test_require_role_allows_authorized():
    require_role(_ctx(Role.REVIEWER), UPDATE_STATUS)
