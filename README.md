# jev-claude-router

Jev MCP for using with Claude Code and Claude Desktop.

An [MCP](https://modelcontextprotocol.io) server that asks [Jev](https://www.jevai.org) which Claude model and effort level suit a task, judged by how hard the task is and what each model costs. It picks from the models in the Claude model picker (Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 4.5) and from the effort levels `low`, `medium`, `high`, `xhigh` and `max`.

Only a TypeSafe API key for Jev is needed. You don't need an OpenRouter or Anthropic key.

## How it works

An MCP tool can't change the model or effort of the chat it runs in, so the server **recommends** them and doesn't switch anything:

1. At the start of a task, Claude calls `pick_model` with a short description of the task.
2. Jev compares the candidate models using live prices, context sizes and output limits, and picks one.
3. Jev is asked a second time to pick an effort level for the task on that model.
4. The tool returns a recommendation, for example `Claude Sonnet 5.5` at `medium` effort. You switch to it in the model picker (or with `/model` in Claude Code) and send the task.

If the effort call fails, the model recommendation still comes back, with `effort_error` in place of `recommended_effort`.

Prices, limits and fit checks come from OpenRouter's public model list (which needs no key) through [model-router-python](https://pypi.org/project/model-router-python/). Both Jev questions go to TypeSafe's API at `https://api.typesafe.ai/v1/systemone` with the `jev-latest` model.

### Tools

| Tool | What it does |
| --- | --- |
| `pick_model(task, output_tokens=2048)` | Returns the recommended model and effort level, or explains why there is no recommendation (for example, Jev is rate-limited) |
| `pick_effort(task)` | Returns only the recommended effort level, for when the model is already chosen |
| `list_candidates()` | Lists the models and effort levels Jev chooses between |

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/). It downloads Python 3.12+ itself if you don't have it.
- A TypeSafe API key from [console.typesafe.ai/keys](https://console.typesafe.ai/keys)

## Install

### Claude Code

```bash
claude mcp add jev -e JEV_API_KEY=... -- \
  uvx --from git+https://github.com/sergeiboikov/jev-claude-router jev-claude-router
```

### Claude Desktop

Open **Settings → Developer → Edit Config** and add the server to `claude_desktop_config.json` (see [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json)):

```json
{
  "mcpServers": {
    "jev": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/sergeiboikov/jev-claude-router", "jev-claude-router"],
      "env": { "JEV_API_KEY": "..." }
    }
  }
}
```

Fully quit Claude Desktop and start it again.

> On macOS, Claude Desktop doesn't load your shell `PATH`. If the server fails with "spawn uvx ENOENT", use the full path from `which uvx` (usually `~/.local/bin/uvx`, written out in full) as `command`.

### From a local clone

Use this while developing. Changes take effect after restarting the client.

```json
"command": "uv",
"args": ["run", "--directory", "/Users/sergeiboikov/GitHub/sergeiboikov/jev-claude-router", "jev-claude-router"]
```

## Make Claude use it

Add this to your project instructions, your profile preferences, or `CLAUDE.md`:

```markdown
## Model routing

At the start of every new task, call `pick_model` (the `jev` MCP server, tool `mcp__jev__pick_model`) with a one-line description of the task, tell me the recommended model and effort, and then **stop and end your turn**. Do not start the task, search, or answer until I reply (I'll switch the model first).
```

## Configuration

| Variable | Required | Default |
| --- | --- | --- |
| `JEV_API_KEY` | yes | none. A TypeSafe console key; `jev_` keys from jevai.org don't work with this API |
| `CLAUDE_MODELS` | no | the four models above, as comma-separated OpenRouter ids |

Example: `CLAUDE_MODELS=anthropic/claude-opus-5.5,anthropic/claude-sonnet-5.5`.

At startup the server skips any model that isn't in OpenRouter's catalog and notes it in the MCP log.

## Development

```bash
uv sync
uv run pytest          # offline tests, no key needed
uv run jev-claude-router  # runs the server on stdio (needs JEV_API_KEY)
```

To try the tools interactively:

```bash
JEV_API_KEY=... npx @modelcontextprotocol/inspector uv run jev-claude-router
```

## Notes and limits

- Jev ranks models by API price. On a Claude subscription this roughly tracks how fast each model uses up your limits. Opus uses them up faster than Sonnet.
- The model id and effort level are the only things returned. Jev's confidence isn't exposed.
- Effort is picked from fixed descriptions of each level (`EFFORT_LEVELS` in `server.py`), not from prices. A recommendation costs two Jev calls.
- If Jev can't be reached or rate-limits the call, the tool says so and makes no recommendation. It doesn't guess.
- model-router-python is alpha. Its own Jev call goes to jevai.org, which only takes `jev_` keys, so the server replaces that call with one to TypeSafe's API and uses the library only for the catalog and limits.
- On python.org builds of Python for macOS, run `Install Certificates.command` once (in `/Applications/Python 3.x/`), or every HTTPS call fails with `CERTIFICATE_VERIFY_FAILED`.
- If you push some changes to GitHub, uvx may keep its cached copy until you run `uv cache clean`.