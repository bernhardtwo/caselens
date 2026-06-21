from caselens.data.generators import generate
from caselens.data.models import ClaimStatus, Role


def test_generate_is_deterministic_and_shaped():
    a = generate(3, 3, 5, seed=0)
    b = generate(3, 3, 5, seed=0)
    assert a == b
    assert len(a) == 3
    assert all(len(t.users) == 3 for t in a)
    assert all(len(t.claims) == 5 for t in a)
    assert len({t.name for t in a}) == 3


def test_each_tenant_has_admin_and_reviewer():
    for tenant in generate(2, 3, 4, seed=1):
        roles = {u.role for u in tenant.users}
        assert Role.ADMIN in roles and Role.REVIEWER in roles


def test_costs_are_int_cents_and_statuses_valid():
    valid = {s.value for s in ClaimStatus}
    for tenant in generate(2, 2, 30, seed=2):
        for claim in tenant.claims:
            assert claim.cost_cents is None or (
                isinstance(claim.cost_cents, int) and not isinstance(claim.cost_cents, bool)
            )
            assert claim.status in valid
