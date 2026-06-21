from unittest.mock import MagicMock

from caselens.agent.tools import ALLOWED_TRANSITIONS, build_tools, can_transition
from caselens.data.models import ClaimStatus, Role, TenantContext


def _tools():
    ctx = TenantContext(tenant_id=1, user_id=1, role=Role.REVIEWER)
    return build_tools(ctx, conn=MagicMock(), co=MagicMock())


def test_tool_schemas_never_expose_tenant_id():
    # The load-bearing security property: tenant_id is bound in the closure, never in a schema.
    for tool in _tools():
        params = tool.schema()["function"]["parameters"]
        assert params["type"] == "object"
        assert "tenant_id" not in params.get("properties", {})


def test_expected_tools_present():
    assert {tool.name for tool in _tools()} == {
        "rag_search",
        "query_claims",
        "get_claim",
        "update_claim_status",
    }


def test_state_machine_allows_valid_and_blocks_invalid():
    assert can_transition(ClaimStatus.OPEN, ClaimStatus.IN_REVIEW)
    assert can_transition(ClaimStatus.IN_REVIEW, ClaimStatus.APPROVED)
    assert not can_transition(ClaimStatus.OPEN, ClaimStatus.APPROVED)
    assert not can_transition(ClaimStatus.CLOSED, ClaimStatus.OPEN)


def test_closed_is_terminal():
    assert ALLOWED_TRANSITIONS[ClaimStatus.CLOSED] == frozenset()
