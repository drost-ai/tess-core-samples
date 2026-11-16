<div align="center">

<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/drost-ai/tess-core/main/docs/assets/tess-core-dark.svg">
    <img src="https://raw.githubusercontent.com/drost-ai/tess-core/main/docs/assets/tess-core-light.svg" alt="Tess Core" height="64">
  </picture>
</h1>

**Samples. Real agents you can run in a minute and read in a sitting.**

[Tess Core](https://github.com/drost-ai/tess-core) · [Documentation](https://continuityresearch.ai/tess-core/docs) · [The first sample](coding-agent-minimal/)

</div>

---

```
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
```

That is a coding agent with tools, a sub-agent working in the background, and a parent that
is woken when the result arrives. It is one Python file, and its only dependency is
[Tess Core](https://github.com/drost-ai/tess-core), which has none of its own.

## Why these exist

Tess Core is an agent runtime for Python: sessions, tools, permissions, sub-agents, MCP,
scheduling and durable state in one package with zero dependencies. A runtime is easiest to
judge by what it takes to build something on it. These samples are that evidence. Each one
is a complete program, short enough to read from top to bottom, that you can run against
your own model in a few commands and then change.

## The samples

| Sample | What you get | Size |
|---|---|---|
| [**coding-agent-minimal**](coding-agent-minimal/) | A terminal coding agent. Multi-turn chat, live tool calls, sub-agents that report back while you type, and `--resume` to pick up yesterday's conversation. | One file, about 290 lines |

More are on the way. Each new sample gets its own folder and its own row here.

## Run one

```sh
git clone https://github.com/drost-ai/tess-core-samples.git
cd tess-core-samples/coding-agent-minimal
uv sync
cp .env.example .env        # keep the line your model needs
uv run agent.py --cwd ~/path/to/your/project
```

Every sample works the same way: its own folder, its own `pyproject.toml`, and `uv sync` as
the whole setup. Nothing is shared between them, so you can copy one folder out and start
your own project from it.

## Any model

Each sample reads its models from a `providers.yaml` beside it. The ones included cover a
ChatGPT account signed in with Codex, the OpenAI and Anthropic APIs, Kimi, Z.ai, DeepSeek,
and a model on your own machine. Switching is one flag:

```sh
uv run agent.py --provider claude
```

## What a sample is made of

The agent in every sample is three calls:

```python
runtime = await start_runtime(home, cwd=project, provider_registry="providers.yaml",
                              session_options=lambda session_id, reason: SessionOptions(provider="claude"))
session = await runtime.sessions.open()
result = await session.run_turn("Find the bug in src/calc.py and fix it.")
```

The rest of each file is what makes it that sample: how it shows the agent's work, what it
lets the agent do, and how you talk to it. The
[Tess Core documentation](https://continuityresearch.ai/tess-core/docs) covers the runtime
underneath.

## License

Apache-2.0. See [LICENSE](LICENSE).

Created by Migel Tissera at [Continuity Research](https://continuityresearch.ai).
