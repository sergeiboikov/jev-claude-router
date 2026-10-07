# jev-claude-router

Jev MCP for using with Claude Code and Claude Desktop.

An [MCP](https://modelcontextprotocol.io) server that asks [Jev](https://www.jevai.org) which Claude model suits a task, judged by how hard the task is and what each model costs. It picks from the models in the Claude model picker: Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 4.5.

Only a Jev API key is needed. You don't need an OpenRouter or Anthropic key.

## How it works

An MCP tool can't change the model of the chat it runs in, so the server **recommends** a model and doesn't switch it:

1. At the start of a task, Claude calls `pick_model` with a short description of the task.
2. Jev compares the candidate models using live prices, context sizes and output limits, and picks one.
3. The tool returns a recommendation, for example `Claude Sonnet 5.5`. You switch to it in the model picker (or with `/model` in Claude Code) and send the task.

Prices and limits come from OpenRouter's public model list, which needs no key. The routing call goes to Jev's API through [model-router-python](https://pypi.org/project/model-router-python/).

### Tools

| Tool | What it does |
| --- | --- |
| `pick_model(task, output_tokens=2048)` | Returns the recommended model, or explains why there is no recommendation (for example, Jev is rate-limited) |
| `list_candidates()` | Lists the models Jev chooses between |

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/). It downloads Python 3.12+ itself if you don't have it.
- A Jev API key from [TypeSafe AI](https://typesafe.ai/)

## Install

### Claude Code

```bash
claude mcp add jev -e JEV_API_KEY=jev_... -- \
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
      "env": { "JEV_API_KEY": "jev_..." }
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

> At the start of every new task, call `pick_model` with a one-line description of the task and tell me the recommended model before you continue.

## Configuration

| Variable | Required | Default |
| --- | --- | --- |
| `JEV_API_KEY` | yes | none |
| `CLAUDE_MODELS` | no | the four models above, as comma-separated OpenRouter ids |

Example: `CLAUDE_MODELS=anthropic/claude-opus-5.5,anthropic/claude-sonnet-5.5`.

At startup the server skips any model that isn't in OpenRouter's catalog and notes it in the MCP log. At the time of writing, Haiku 4.5 isn't in the catalog.

## Development

```bash
uv sync
uv run pytest          # offline tests, no key needed
uv run jev-claude-router  # runs the server on stdio (needs JEV_API_KEY)
```

To try the tools interactively:

```bash
JEV_API_KEY=jev_... npx @modelcontextprotocol/inspector uv run jev-claude-router
```

## Notes and limits

- Jev ranks models by API price. On a Claude subscription this roughly tracks how fast each model uses up your limits. Opus uses them up faster than Sonnet.
- The model id is the only thing returned. Jev's confidence isn't exposed.
- If Jev can't be reached or rate-limits the call, the tool says so and makes no recommendation. It doesn't guess.
- model-router-python is alpha. Its direct Jev-key mode hasn't been verified against the live API by its author.
