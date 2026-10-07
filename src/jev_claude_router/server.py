"""MCP server: Jev recommends which Claude model to use for a task.

Only a Jev API key is needed. The candidates are the Claude models available in
the Claude Desktop / Claude Code model picker. The server does not run the task:
it returns a recommendation, and you switch the model in the picker (or /model).

Environment variables:
  JEV_API_KEY    required, from https://www.jevai.org/agent/keys
  CLAUDE_MODELS  optional, comma-separated OpenRouter ids to use as candidates
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

from model_router import Limits, NoModelFitsError, Router, RouterError

CATALOG_URL = "https://openrouter.ai/api/v1/models"

# OpenRouter id (where prices and limits come from) -> name in the Claude model picker
DESKTOP_NAMES: dict[str, str] = {
    "anthropic/claude-fable-5.1": "Claude Fable 5.1",
    "anthropic/claude-opus-5.5": "Claude Opus 5.5",
    "anthropic/claude-sonnet-5.5": "Claude Sonnet 5.5",
    "anthropic/claude-haiku-4.5": "Claude Haiku 4.5",
}

mcp = FastMCP("jev-claude-router")
_router: Router | None = None
_candidates: list[str] | None = None


def log(msg: str) -> None:
    # stdout carries the MCP protocol, so diagnostics go to stderr (shown in the client's MCP logs)
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
            providers=["anthropic"],  # provider name only: no Anthropic key is needed
            models=models,
            timeout=15,
        )
    return _router


@mcp.tool()
def pick_model(task: str, output_tokens: int = 2048) -> str:
    """Ask Jev which Claude model fits this task best, by difficulty and cost.

    Call this at the start of a new task with a short description of it.
    Returns a recommendation; the user switches the model in the model picker.
    Do not do the task inside this tool.
    """
    try:
        model = router().route(task, Limits(output_tokens=output_tokens))
    except NoModelFitsError as e:
        return f"No model fits these limits: {e}"
    except RouterError as e:
        return f"Jev did not answer ({e}). No recommendation; stay on the current model."
    name = display_name(model)
    return json.dumps(
        {
            "recommended_model": name,
            "openrouter_id": model,
            "how_to_apply": f"Switch the chat model to \"{name}\" and send the task.",
        },
        ensure_ascii=False,
    )


@mcp.tool()
def list_candidates() -> str:
    """List the Claude models Jev chooses between."""
    return json.dumps([display_name(m) for m in candidates()], ensure_ascii=False)


def main() -> None:
    if not os.environ.get("JEV_API_KEY"):
        log("JEV_API_KEY is not set")
        sys.exit(1)
    mcp.run()  # stdio transport, which is how Claude Desktop and Claude Code start local servers


if __name__ == "__main__":
    main()
