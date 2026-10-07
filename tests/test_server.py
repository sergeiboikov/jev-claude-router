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


def test_pick_model_returns_desktop_name(monkeypatch):
    monkeypatch.setattr(server, "_router", FakeRouter(result="anthropic/claude-sonnet-5.5"))
    out = json.loads(server.pick_model("Translate 'hello' into French"))
    assert out["recommended_model"] == "Claude Sonnet 5.5"
    assert out["openrouter_id"] == "anthropic/claude-sonnet-5.5"


def test_pick_model_handles_jev_error(monkeypatch):
    monkeypatch.setattr(server, "_router", FakeRouter(error=RouterError("HTTP 429")))
    assert "HTTP 429" in server.pick_model("anything")


def test_list_candidates(monkeypatch):
    monkeypatch.setattr(server, "_candidates", ["anthropic/claude-opus-5.5", "custom/model"])
    assert json.loads(server.list_candidates()) == ["Claude Opus 5.5", "custom/model"]
