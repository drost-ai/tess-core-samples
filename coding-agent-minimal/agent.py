#!/usr/bin/env python3
"""A terminal coding agent in one file, built on Tess Core.

    uv run agent.py                      # work in the current directory
    uv run agent.py --cwd ~/my-project   # work somewhere else
    uv run agent.py --resume             # pick up this directory's last conversation
    uv run agent.py -p "fix the tests"   # one request, then exit
    uv run agent.py --provider zai       # any profile from providers.yaml

Everything the runtime does arrives as an event. This file is mostly the part
that prints them: the agent's own work in one colour, its sub-agents' in another.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

from tess_core import ProviderRegistry, SessionOptions, start_runtime

HERE = Path(__file__).resolve().parent
STATE = Path.home() / ".tess-core-samples" / "coding-agent-minimal"  # sessions live here, outside your project


class Style:
    """ANSI colours, off when output is not a terminal or NO_COLOR is set."""

    CODES = {
        "dim": "2", "bold": "1", "red": "31", "green": "32", "yellow": "33", "prompt": "1;32",
        "tool": "1;35",  # the agent's own tool calls
        "child": "36",  # everything a sub-agent does
    }

    def __init__(self) -> None:
        self.on = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    def __getattr__(self, name: str):
        code = self.CODES[name]
        return lambda text: f"\x1b[{code}m{text}\x1b[0m" if self.on and text else text


class Printer:
    """Turns the runtime's events into terminal output."""

    def __init__(self, style: Style) -> None:
        self.style = style
        self.children: dict[str, str] = {}  # task id -> the sub-agent's name
        self.turn_id: str | None = None  # the turn now running, for Ctrl+C
        self.idle = asyncio.Event()  # set while no turn is running
        self.idle.set()
        self.at_prompt = False
        self._line_start = True
        self._thinking = False
        self._started: dict[str, float] = {}
        self._held: list[str] = []  # sub-agent lines waiting for the agent to finish a line of its own
        self._tokens = [0, 0]
        self._tools = 0
        self._asked_at: float | None = None  # when the model was called and has not yet answered

    def handle(self, envelope: dict) -> None:
        event, data = envelope["event"], envelope["data"]
        s = self.style
        if event == "provider.request_started":
            self._asked_at = time.monotonic()
            asyncio.get_running_loop().call_later(5, self._still_waiting, self._asked_at)
        elif event.startswith(("message.assistant", "tool.", "provider.response", "turn.")):
            self._asked_at = None  # the model is answering, or the turn is over
        if event == "turn.started":
            self.turn_id, self._tokens, self._tools = data.get("turn_id"), [0, 0], 0
            self.idle.clear()
            if data.get("origin") == "child_message":
                self._line(s.child("◆ a sub-agent reported back; the agent is reading its result"))
        elif event == "message.assistant.thinking.partial":
            if not self._thinking:
                self._break()
                self._write(s.dim("[thinking] "))
                self._thinking = True
            self._write(s.dim(data.get("thinking_delta") or ""))
        elif event == "message.assistant.partial":
            self._end_thinking()
            self._write(data.get("text_delta") or "")
        elif event == "tool.started":
            self._end_thinking()
            self._tools += 1
            self._started[data.get("tool_use_id") or ""] = time.monotonic()
            self._line("\n" + s.tool(f"● {data.get('name')}"))
            for key, value in (data.get("input") or {}).items():
                self._line(f"    {s.dim(key + ':')} {clip(value, 200)}")
        elif event == "tool.completed":
            took = time.monotonic() - self._started.pop(data.get("tool_use_id") or "", time.monotonic())
            mark = s.red("✗ error") if data.get("error") else s.green("✓")
            size = len(str(data.get("output") or ""))
            self._line(f"  {s.dim('⎿')} {mark} " + s.dim(f"{took:.1f}s · {size:,} chars"))
        elif event == "provider.response_completed":
            usage = data.get("usage") or {}
            self._tokens[0] += usage.get("input_tokens") or 0
            self._tokens[1] += usage.get("output_tokens") or 0
        elif event == "provider.retrying":
            self._line(s.yellow(f"[retry] {data.get('category') or 'provider'} · attempt {data.get('attempt')}"))
        elif event == "subagent.backgrounded":
            self.children[data.get("task_id") or ""] = str(data.get("label") or "sub-agent")
            self._line(s.child(f"◆ sub-agent {data.get('label')} started in the background"))
        elif event == "subagent.trace":
            self._child_step(data)
        elif event == "subagent.message":
            kind = "question" if data.get("kind") == "question" else "result"
            self._child_line(f"  [{self._name(data)}] {kind}: {clip(data.get('preview'), 160)}")
        elif event in ("turn.completed", "turn.failed", "turn.cancelled"):
            self._end_thinking()
            self._break()
            reason = data.get("stop_reason") or event.split(".")[1]
            if event == "turn.failed" and data.get("error"):
                self._line(s.red(clip(data.get("error"), 400)))
            note = f"— {reason} · {self._tokens[0]:,} in / {self._tokens[1]:,} out tok · {self._tools} tool calls"
            self._line((s.red if event == "turn.failed" else s.dim)(note))
            self.turn_id = None
            self.idle.set()
            if self.at_prompt:
                self._write(s.prompt("› "))  # the reader is still waiting on the prompt this output scrolled away

    def _still_waiting(self, asked_at: float) -> None:
        """A model can take a long time to start answering. Say so, so silence is not mistaken for a hang."""
        if self._asked_at != asked_at:
            return
        self._line(self.style.dim(f"… waiting for the model ({time.monotonic() - asked_at:.0f}s)"))
        asyncio.get_running_loop().call_later(15, self._still_waiting, asked_at)

    def _child_step(self, data: dict) -> None:
        """One line per thing a sub-agent does, in the sub-agent colour."""
        step, name = data.get("trace_event"), self._name(data)
        if step == "tool.started":
            text = f"● {data.get('tool')} {clip(data.get('input_preview'), 110)}"
        elif step == "tool.completed":
            text = f"⎿ {'✗' if data.get('error') else '✓'} {data.get('output_chars') or 0:,} chars"
        elif step == "message.assistant":
            text = f"says: {clip(data.get('text_preview'), 200)}"
        else:
            return
        self._child_line(f"  [{name}] {text}")

    def _child_line(self, text: str) -> None:
        """A sub-agent works while the agent is writing: hold its line until the agent ends its own."""
        if self._line_start:
            self._line(self.style.child(text))
        else:
            self._held.append(text)

    def _name(self, data: dict) -> str:
        task = str(data.get("task_id") or "")
        return self.children.get(task) or f"sub-agent {task[:8]}"

    def _end_thinking(self) -> None:
        if self._thinking:
            self._break()
            self._thinking = False

    def _line(self, text: str) -> None:
        self._break()
        self._write(text + "\n")

    def _break(self) -> None:
        if self.at_prompt and self._line_start:
            self._write("\n")  # leave the prompt line before printing under it
        elif not self._line_start:
            self._write("\n")

    def _write(self, text: str) -> None:
        if text:
            sys.stdout.write(text)
            self._line_start = text.endswith("\n")
            if self._line_start and self._held:
                held, self._held = self._held, []
                sys.stdout.write("".join(self.style.child(line) + "\n" for line in held))
            sys.stdout.flush()


def clip(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_env(path: Path) -> None:
    """Read KEY=VALUE lines from .env beside this file into the environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, found, value = line.strip().partition("=")
        if found and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def session_options(registry: ProviderRegistry, provider: str) -> SessionOptions:
    profile = registry.profiles[provider]
    codex_file = os.environ.get("CODEX_AUTH_PATH") if profile["auth"]["kind"] == "openai_api_key_or_codex" else None
    return SessionOptions(provider=provider, permission_mode="bypassPermissions", provider_auth_path=codex_file)


def stdin_lines(loop: asyncio.AbstractEventLoop) -> asyncio.Queue:
    """Lines typed at the terminal, read on a thread so events keep printing while you think."""
    queue: asyncio.Queue = asyncio.Queue()

    def read() -> None:
        for line in sys.stdin:
            loop.call_soon_threadsafe(queue.put_nowait, line.rstrip("\n"))
        loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=read, daemon=True).start()
    return queue


async def main() -> int:
    parser = argparse.ArgumentParser(description="A terminal coding agent built on Tess Core.")
    parser.add_argument("-p", "--prompt", help="run one request and exit")
    parser.add_argument("--cwd", default=os.getcwd(), help="the project to work in (default: here)")
    parser.add_argument("--provider", help="a profile from providers.yaml (default: the first)")
    parser.add_argument("--resume", action="store_true", help="continue this project's last conversation")
    args = parser.parse_args()

    load_env(HERE / ".env")
    registry = ProviderRegistry(HERE / "providers.yaml")
    provider = args.provider or next(iter(registry.profiles))
    if provider not in registry.profiles:
        parser.error(f"no profile named {provider!r}; providers.yaml has: {', '.join(registry.profiles)}")
    cwd = Path(args.cwd).expanduser().resolve()
    home = STATE / hashlib.sha256(str(cwd).encode()).hexdigest()[:12]  # one runtime home per project
    last_session = home / "last-session"

    style, loop = Style(), asyncio.get_running_loop()
    printer = Printer(style)
    runtime = await start_runtime(
        home, cwd=cwd, provider_registry=registry,
        session_options=lambda session_id, reason: session_options(registry, provider),
    )
    try:
        resumed = args.resume and last_session.is_file()
        session = await runtime.sessions.open(last_session.read_text().strip() if resumed else None)
        session.subscribe(printer.handle)
        last_session.write_text(session.id)
        print(style.bold("coding-agent-minimal") + style.dim(f"  {session.model} · {session.permission_mode} · {cwd}"))
        print(style.dim(f"session {session.id}{' (resumed)' if resumed else ''} · saved under {home}"))

        def interrupt() -> None:  # Ctrl+C stops the turn that is running; at the prompt it quits
            if printer.turn_id:
                loop.create_task(session.cancel_turn(printer.turn_id))
            else:
                lines.put_nowait(None)

        lines = stdin_lines(loop) if not args.prompt else asyncio.Queue()
        loop.add_signal_handler(signal.SIGINT, interrupt)

        while True:
            if args.prompt:
                request = args.prompt
            else:
                await printer.idle.wait()
                printer.at_prompt = True
                sys.stdout.write(style.prompt("› "))
                sys.stdout.flush()
                request = await lines.get()
                printer.at_prompt = False
                if request is None or request.strip() in ("/exit", "/quit"):
                    break
                if not request.strip():
                    continue
            await session.run_turn(request)
            if args.prompt:
                # Sub-agents outlive the turn that started them, and stopping the runtime
                # stops them too: wait until each has reported and the agent has answered.
                await runtime.wait_until_idle()
                break
    finally:
        await runtime.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
