"""Offline tests: no network, no Jev key."""

import json

import pytest

from jev_claude_router import server
from model_router import RouterError


class FakeRouter:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def route(self, task, limits=None):
        if self.error:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(server, "_router", None)
    monkeypatch.setattr(server, "_candidates", None)


def test_wanted_models_default(monkeypatch):
    monkeypatch.delenv("CLAUDE_MODELS", raising=False)
    assert server.wanted_models() == list(server.DESKTOP_NAMES)


def test_wanted_models_override(monkeypatch):
    monkeypatch.setenv("CLAUDE_MODELS", " anthropic/claude-opus-5.5 , ,anthropic/claude-sonnet-5.5")
    assert server.wanted_models() == ["anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5"]


def test_filter_known_drops_missing():
    wanted = ["anthropic/claude-opus-5.5", "anthropic/claude-haiku-4.5"]
    assert server.filter_known(wanted, {"anthropic/claude-opus-5.5"}) == ["anthropic/claude-opus-5.5"]


def test_filter_known_without_catalog_keeps_all():
    wanted = ["anthropic/claude-opus-5.5"]
    assert server.filter_known(wanted, None) == wanted


def fake_jev(decision=None, error=None):
    def request_json(url, api_key, body, timeout):
        fake_jev.body = body
        if error:
            raise error
        return {"answers": {"pick": {"type": "choice", "choice": decision}}}

    return request_json


def test_pick_model_returns_desktop_name_and_effort(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test")
    monkeypatch.setattr(server, "_router", FakeRouter(result="anthropic/claude-sonnet-5.5"))
    monkeypatch.setattr(server, "request_json", fake_jev("low"))
    out = json.loads(server.pick_model("Translate 'hello' into French"))
    assert out["recommended_model"] == "Claude Sonnet 5.5"
    assert out["openrouter_id"] == "anthropic/claude-sonnet-5.5"
    assert out["recommended_effort"] == "low"
    assert "Claude Sonnet 5.5" in fake_jev.body["state"]
    assert fake_jev.body["questions"]["pick"]["criteria"] == server.EFFORT_LEVELS


def test_pick_model_keeps_model_when_effort_fails(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test")
    monkeypatch.setattr(server, "_router", FakeRouter(result="anthropic/claude-opus-5.5"))
    monkeypatch.setattr(server, "request_json", fake_jev(error=RouterError("HTTP 429")))
    out = json.loads(server.pick_model("anything"))
    assert out["recommended_model"] == "Claude Opus 5.5"
    assert "recommended_effort" not in out
    assert "HTTP 429" in out["effort_error"]


def test_pick_effort(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test")
    monkeypatch.setattr(server, "request_json", fake_jev("xhigh"))
    assert json.loads(server.pick_effort("Redesign the storage layer"))["recommended_effort"] == "xhigh"


def test_pick_effort_rejects_unknown_level(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test")
    monkeypatch.setattr(server, "request_json", fake_jev("ultra"))
    assert "Unexpected Jev response" in server.pick_effort("anything")


def test_choose_model_maps_alias_to_model_id(monkeypatch):
    from model_router import Limits
    from model_router.models import ModelInfo

    models = [ModelInfo(id=f"anthropic/m{i}", context_length=200_000, max_output_tokens=None,
                        prompt_price=1e-6, completion_price=5e-6) for i in range(2)]
    monkeypatch.setenv("JEV_API_KEY", "test")
    monkeypatch.setattr(server, "request_json", fake_jev("m1"))
    assert server.choose_model("task", 10, models, Limits()) == "anthropic/m1"
    assert set(fake_jev.body["questions"]["pick"]["criteria"]) == {"m0", "m1"}


def test_pick_model_handles_jev_error(monkeypatch):
    monkeypatch.setattr(server, "_router", FakeRouter(error=RouterError("HTTP 429")))
    assert "HTTP 429" in server.pick_model("anything")


def test_list_candidates(monkeypatch):
    monkeypatch.setattr(server, "_candidates", ["anthropic/claude-opus-5.5", "custom/model"])
    out = json.loads(server.list_candidates())
    assert out["models"] == ["Claude Opus 5.5", "custom/model"]
    assert out["efforts"] == ["low", "medium", "high", "xhigh", "max"]
