from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from caselens.agent.loop import AgentResult
from caselens.api import app as app_module
from caselens.api.app import app, require_access


def _request(path: str = "/agent", headers: dict | None = None, cookies: dict | None = None):
    return SimpleNamespace(
        url=SimpleNamespace(path=path), headers=headers or {}, cookies=cookies or {}
    )


def test_gate_off_allows_without_token(monkeypatch):
    monkeypatch.setattr(app_module.get_settings(), "access_token", None)
    require_access(_request(headers={}))  # no raise


def test_gate_on_rejects_missing_token(monkeypatch):
    monkeypatch.setattr(app_module.get_settings(), "access_token", "s3cret")
    with pytest.raises(HTTPException) as exc:
        require_access(_request(headers={}))
    assert exc.value.status_code == 401


def test_gate_on_accepts_header_token(monkeypatch):
    monkeypatch.setattr(app_module.get_settings(), "access_token", "s3cret")
    require_access(_request(headers={"X-Access-Token": "s3cret"}))


def test_gate_on_accepts_cookie_token(monkeypatch):
    monkeypatch.setattr(app_module.get_settings(), "access_token", "s3cret")
    require_access(_request(cookies={"access_token": "s3cret"}))


def test_health_exempt_when_gated(monkeypatch):
    monkeypatch.setattr(app_module.get_settings(), "access_token", "s3cret")
    require_access(_request(path="/health", headers={}))  # no raise


def test_endpoint_gate_end_to_end(monkeypatch):
    def fake_run_agent(ctx, message, **kwargs):
        return AgentResult(answer="ok", citations=[], sources=[], tool_trace=[], actions_taken=[])

    monkeypatch.setattr(app_module, "run_agent", fake_run_agent)
    client = TestClient(app)

    monkeypatch.setattr(app_module.get_settings(), "access_token", "s3cret")
    assert client.post("/agent", json={"message": "hi"}).status_code == 401
    ok = client.post("/agent", json={"message": "hi"}, headers={"X-Access-Token": "s3cret"})
    assert ok.status_code == 200 and ok.json()["answer"] == "ok"
    assert client.get("/health").status_code == 200  # exempt even when gated

    monkeypatch.setattr(app_module.get_settings(), "access_token", None)
    assert client.post("/agent", json={"message": "hi"}).status_code == 200
