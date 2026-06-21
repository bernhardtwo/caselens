import pytest
from fastapi import HTTPException

from caselens.agent.loop import AgentResult
from caselens.api.app import AgentRequest, agent_endpoint, get_tenant_context
from caselens.data.models import Role, TenantContext


def test_tenant_context_defaults():
    ctx = get_tenant_context()
    assert ctx.tenant_id == 1 and ctx.user_id == 1 and ctx.role == Role.REVIEWER


def test_tenant_context_from_dev_headers():
    ctx = get_tenant_context(x_tenant_id=5, x_user_id=9, x_role="admin")
    assert ctx.tenant_id == 5 and ctx.user_id == 9 and ctx.role == Role.ADMIN


def test_unknown_role_is_rejected():
    with pytest.raises(HTTPException):
        get_tenant_context(x_role="wizard")


def test_request_body_cannot_carry_tenant():
    body = AgentRequest.model_validate({"message": "x", "tenant_id": 99, "role": "admin"})
    assert body.message == "x"
    assert not hasattr(body, "tenant_id")
    assert not hasattr(body, "role")


def test_endpoint_uses_session_ctx_not_body(monkeypatch):
    captured = {}

    def fake_run_agent(ctx, message, **kwargs):
        captured["ctx"] = ctx
        captured["message"] = message
        return AgentResult(answer="ok", citations=[], sources=[], tool_trace=[], actions_taken=[])

    monkeypatch.setattr("caselens.api.app.run_agent", fake_run_agent)
    ctx = TenantContext(tenant_id=7, user_id=3, role=Role.ADMIN)
    response = agent_endpoint(AgentRequest(message="hola"), ctx)
    assert response["answer"] == "ok"
    assert captured["ctx"].tenant_id == 7
    assert captured["message"] == "hola"
