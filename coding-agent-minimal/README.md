# coding-agent-minimal

A terminal coding agent in one file. You type a request; it reads and edits your project,
runs commands, delegates to sub-agents, and shows every step as it happens.

`agent.py` is about 280 lines, and most of them print. The agent itself is three calls into
[Tess Core](https://github.com/drost-ai/tess-core): start a runtime, open a session, run a
turn.

## Run it

```sh
git clone https://github.com/drost-ai/tess-core-samples.git
cd tess-core-samples/coding-agent-minimal
uv sync
cp .env.example .env        # then edit .env: keep the line your model needs
uv run agent.py --cwd ~/path/to/your/project
```

The default model is the first profile in `providers.yaml`, a ChatGPT account signed in
with the Codex CLI. To use another, name it:

```sh
uv run agent.py --provider claude --cwd ~/path/to/your/project
```

`providers.yaml` has profiles for Codex, the OpenAI and Anthropic APIs, Kimi, Z.ai and a
local server. Edit the model names to ones your account serves.

## What you see

```
coding-agent-minimal  GLM-5.3 · bypassPermissions · /Users/you/project
session 7d09522381cc4e3daf4f4c5d0808cfcc · saved under ~/.tess-core-samples/coding-agent-minimal/b2f2a8104342
› Start a sub-agent to count the lines in data.txt. Meanwhile, is there a bug in src/calc.py?
[thinking] Spawn the sub-agent and read the file in parallel.

● Agent
    description: Count lines in data.txt
● Read
    file_path: src/calc.py
  ⎿ ✓ 0.0s · 747 chars
◆ sub-agent Count lines in data.txt started in the background
Yes: `add` returns `a - b`. It should return `a + b`.
  [Count lines in data.txt] ● Bash {"command": "wc -l data.txt"}
  [Count lines in data.txt] ⎿ ✓ 1,230 chars
— end_turn · 8,162 in / 506 out tok · 2 tool calls
  [Count lines in data.txt] result: 41
◆ a sub-agent reported back; the agent is reading its result
The sub-agent has reported back: data.txt contains 41 lines.
— end_turn · 4,710 in / 168 out tok · 0 tool calls
›
```

In a terminal the agent's own tool calls are magenta, everything a sub-agent does is cyan,
and reasoning is dim.

## Options

| Option | Meaning |
|---|---|
| `--cwd PATH` | The project to work in. Default: the current directory. |
| `--provider NAME` | A profile from `providers.yaml`. Default: the first. |
| `--resume` | Continue this project's last conversation. |
| `-p "..."` | Run one request and exit, after any sub-agents have reported. |

At the prompt, `/exit` or Ctrl+C quits. While the agent is working, Ctrl+C stops the
current turn and returns you to the prompt.

## How it works

- **The runtime.** `start_runtime(home, cwd=..., provider_registry=...)` starts everything:
  sessions, tools, the daemon that runs sub-agents and background commands.
- **The session.** `runtime.sessions.open()` starts a conversation, or reopens one by id.
  That is all `--resume` does: the id of the last session is kept in a file.
- **The turn.** `session.run_turn(text)` runs the agent until it stops calling tools.
- **The display.** `session.subscribe(printer.handle)` delivers every event. `Printer` turns
  them into the output above: `message.assistant.partial` is streamed text, `tool.started`
  and `tool.completed` are a tool call, `subagent.trace` is a step a sub-agent took.
- **Sub-agents.** A sub-agent keeps working after the turn that started it. When it reports,
  the runtime wakes the agent with a new turn, which is why output can appear while you are
  sitting at the prompt.

State is kept under `~/.tess-core-samples/coding-agent-minimal/`, one folder per project,
outside the project itself so the agent does not read its own session files while it works.

## Permissions

The agent runs in `bypassPermissions`: it edits files and runs shell commands without
asking. Use it in a project you have under version control. To be asked first, change
`permission_mode` in `session_options()` and give the runtime a listener with an
`ask_question` method; the
[security guide](https://continuityresearch.ai/tess-core/docs/security) shows how.

## Make it yours

- Give it a tool of your own: pass `host_tools=(...)` in `session_options()`.
- Change its character: pass `system_prompt="..."`.
- Connect an MCP server: pass `mcp_servers=(...)`.

Each is one argument. The [embedding guide](https://continuityresearch.ai/tess-core/docs/embedding)
has the details.
