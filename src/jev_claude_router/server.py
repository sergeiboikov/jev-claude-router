"""MCP server: Jev recommends which Claude model and effort level to use for a task.

Only a TypeSafe API key is needed. The candidates are the Claude models available in
the Claude Desktop / Claude Code model picker. The server does not run the task:
it returns a recommendation, and you switch the model and effort in the picker (or /model).

Environment variables:
  JEV_API_KEY    required, a TypeSafe API key from https://console.typesafe.ai/keys
  CLAUDE_MODELS  optional, comma-separated OpenRouter ids to use as candidates
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from mcp.server.mcpserver import MCPServer

from model_router import Limits, NoModelFitsError, Router, RouterError, jev
from model_router._http import request_json

CATALOG_URL = "https://openrouter.ai/api/v1/models"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"

# Effort levels in the Claude model picker, lowest first.
EFFORT_LEVELS: dict[str, str] = {
    "low": "Fastest and cheapest. Short answers, lookups, formatting, simple one-step edits.",
    "medium": "Everyday work. Small features, clear bug fixes, explanations, routine refactors.",
    "high": "Multi-step work that needs care. Features across several files, tricky bugs, reviews.",
    "xhigh": "Hard problems. Architecture changes, subtle concurrency or security bugs, large refactors.",
    "max": "Hardest tasks where quality matters more than time and usage. Deep research, novel algorithms.",
}

# OpenRouter id (where prices and limits come from) -> name in the Claude model picker
DESKTOP_NAMES: dict[str, str] = {
    "anthropic/claude-fable-5.1": "Claude Fable 5.1",
    "anthropic/claude-opus-5.5": "Claude Opus 5.5",
    "anthropic/claude-sonnet-5.5": "Claude Sonnet 5.5",
    "anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
}

mcp = MCPServer("jev-claude-router")
_router: Router | None = None
_candidates: list[str] | None = None


def log(msg: str) -> None:
    print(f"[jev-claude-router] {msg}", file=sys.stderr, flush=True)


def wanted_models() -> list[str]:
    raw = os.environ.get("CLAUDE_MODELS", ",".join(DESKTOP_NAMES))
    return [m.strip() for m in raw.split(",") if m.strip()]


def display_name(model_id: str) -> str:
    return DESKTOP_NAMES.get(model_id, model_id)


def filter_known(wanted: list[str], catalog_ids: set[str] | None) -> list[str]:
    """Keep only ids present in the catalog; model-router-python rejects unknown ids."""
    if catalog_ids is None:
        return wanted
    missing = [m for m in wanted if m not in catalog_ids]
    if missing:
        log(f"not in the OpenRouter catalog, skipped: {missing}")
    return [m for m in wanted if m in catalog_ids]


def fetch_catalog_ids() -> set[str] | None:
    """Public model list, no key required. None if it can't be reached."""
    try:
        with urllib.request.urlopen(CATALOG_URL, timeout=15) as resp:
            return {m["id"] for m in json.load(resp)["data"]}
    except Exception as e:  # noqa: BLE001 - any failure just disables pre-filtering
        log(f"could not load the model catalog: {e}")
        return None


def candidates() -> list[str]:
    global _candidates
    if _candidates is None:
        _candidates = filter_known(wanted_models(), fetch_catalog_ids())
    return _candidates


def router() -> Router:
    global _router
    if _router is None:
        models = candidates()
        if not models:
            raise RouterError("none of the configured models are in the catalog")
        _router = Router(
            jev_api_key=os.environ["JEV_API_KEY"],
            providers=["anthropic"],
            models=models,
            timeout=15,
        )
        _router._choose = choose_model
    return _router


def ask_jev(state: str, instructions: str, criteria: dict[str, str]) -> str:
    """One Jev choice question. Returns a key of `criteria`; raises RouterError otherwise."""
    res = request_json(
        TYPESAFE_URL,
        os.environ["JEV_API_KEY"],
        {
            "model": JEV_MODEL,
            "state": state,
            "questions": {"pick": {"type": "choice", "instructions": instructions, "criteria": criteria}},
        },
        timeout=30,
    )
    picked = ((res.get("answers") or {}).get("pick") or {}).get("choice")
    if picked not in criteria:
        raise RouterError(f"Unexpected Jev response: {res}")
    return picked


def choose_model(task: str, in_tokens: int, candidates: list, limits: Limits) -> str:
    """Router hook: Jev picks one of the models that fit the limits."""
    # Aliases keep criteria keys plain; model ids contain "/" and ".".
    alias = {f"m{i}": m for i, m in enumerate(candidates)}
    picked = ask_jev(
        f"Task {jev._header(in_tokens, limits)}:\n{task[: jev.ROUTING_CHARS]}",
        jev.INSTRUCTIONS,
        {a: jev._describe(m, in_tokens, limits, 200) for a, m in alias.items()},
    )
    return alias[picked].id


def choose_effort(task: str, model: str | None = None) -> str:
    """Ask Jev which effort level fits the task. Raises RouterError if Jev doesn't answer."""
    context = f" (will run on {display_name(model)})" if model else ""
    return ask_jev(
        f"Task{context}:\n{task[: jev.ROUTING_CHARS]}",
        "Which effort level is the most efficient fit for this task? Pick the lowest effort that still "
        "does the task well, and a higher one only when it needs deep reasoning or many careful steps.",
        EFFORT_LEVELS,
    )


@mcp.tool()
def pick_model(task: str, output_tokens: int = 2048) -> str:
    """Ask Jev which Claude model and effort level fit this task best, by difficulty and cost.

    Call this at the start of a new task with a short description of it.
    Returns a recommendation; the user switches the model and effort in the model picker.
    Do not do the task inside this tool.
    """
    try:
        model = router().route(task, Limits(output_tokens=output_tokens))
    except NoModelFitsError as e:
        return f"No model fits these limits: {e}"
    except RouterError as e:
        return f"Jev did not answer ({e}). No recommendation; stay on the current model."
    name = display_name(model)
    out = {"recommended_model": name, "openrouter_id": model}
    try:
        effort = choose_effort(task, model)
    except RouterError as e:  # the model pick still stands without an effort level
        out["effort_error"] = f"Jev did not pick an effort level ({e}). Keep the current effort."
        out["how_to_apply"] = f"Switch the chat model to \"{name}\" and send the task."
    else:
        out["recommended_effort"] = effort
        out["how_to_apply"] = f"Switch the chat model to \"{name}\", set effort to {effort}, and send the task."
    return json.dumps(out, ensure_ascii=False)


@mcp.tool()
def pick_effort(task: str) -> str:
    """Ask Jev which effort level (low, medium, high, xhigh, max) fits this task, for the current model.

    Use this when the model is already chosen. Do not do the task inside this tool.
    """
    try:
        effort = choose_effort(task)
    except RouterError as e:
        return f"Jev did not answer ({e}). No recommendation; keep the current effort."
    return json.dumps(
        {"recommended_effort": effort, "how_to_apply": f"Set effort to {effort} and send the task."},
        ensure_ascii=False,
    )


@mcp.tool()
def list_candidates() -> str:
    """List the Claude models and effort levels Jev chooses between."""
    return json.dumps(
        {"models": [display_name(m) for m in candidates()], "efforts": list(EFFORT_LEVELS)},
        ensure_ascii=False,
    )


def main() -> None:
    if not os.environ.get("JEV_API_KEY"):
        log("JEV_API_KEY is not set")
        sys.exit(1)
    mcp.run()  # stdio transport, which is how Claude Desktop and Claude Code start local servers


if __name__ == "__main__":
    main()
