"""Session persistence: save event logs to ~/.next-cli/sessions/."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nextcli.agent.events import AgentEvent
from nextcli.config import user_config_dir


def workspace_name() -> str:
    """Generate a workspace slug from the current working directory.

    Examples:
        D:/31702/next-ai-cli  ->  D-31702-next-ai-cli
        D:\\123\\3123          ->  D-123-3123
        /home/user/project    ->  home-user-project
    """
    cwd = Path(os.getcwd()).resolve().as_posix()
    # strip leading slash/drive letter, replace separators with dash
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", cwd)
    # collapse multiple dashes
    slug = re.sub(r"-+", "-", slug)
    # strip leading/trailing dash
    slug = slug.strip("-")
    return slug or "workspace"


def list_workspace_sessions() -> list[Path]:
    """Return all session files for the current workspace, newest first."""
    base = user_config_dir() / "sessions"
    if not base.exists():
        return []
    ws = workspace_name()
    files = [p for p in base.iterdir() if p.is_file() and p.name.startswith(f"{ws}_")]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


@dataclass
class Session:
    """One user task session."""

    task: str
    started: float
    events: list[dict[str, Any]] = field(default_factory=list)
    ended: float | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def __post_init__(self) -> None:
        # coerce task to str so we never persist a coroutine / Task object
        if not isinstance(self.task, str):
            try:
                self.task = str(self.task) if self.task is not None else ""
            except Exception:
                self.task = ""
        if not isinstance(self.events, list):
            self.events = []
        try:
            self.total_input_tokens = int(self.total_input_tokens or 0)
        except Exception:
            self.total_input_tokens = 0
        try:
            self.total_output_tokens = int(self.total_output_tokens or 0)
        except Exception:
            self.total_output_tokens = 0

    @classmethod
    def load(cls, path: Path) -> "Session":
        """Safely load a session from a JSON file, coercing any corrupted fields."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        raw_task = data.get("task", "")
        if not isinstance(raw_task, str):
            try:
                raw_task = str(raw_task) if raw_task is not None else ""
            except Exception:
                raw_task = ""
        events = data.get("events", []) or []
        if not isinstance(events, list):
            events = []
        try:
            in_tok = int(data.get("total_input_tokens", 0) or 0)
        except Exception:
            in_tok = 0
        try:
            out_tok = int(data.get("total_output_tokens", 0) or 0)
        except Exception:
            out_tok = 0
        try:
            started = float(data.get("started", 0.0) or 0.0)
        except Exception:
            started = 0.0
        ended = data.get("ended")
        if ended is not None:
            try:
                ended = float(ended)
            except Exception:
                ended = None
        return cls(
            task=raw_task,
            started=started,
            events=events,
            ended=ended,
            total_input_tokens=in_tok,
            total_output_tokens=out_tok,
        )

    def add_event(self, ev: AgentEvent) -> None:
        self.events.append({
            "kind": ev.kind,
            "agent_id": ev.agent_id,
            "role": ev.role.value,
            "ts": ev.ts,
            "payload": ev.payload,
        })

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def finish(self) -> None:
        self.ended = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "started": self.started,
            "ended": self.ended,
            "events": self.events,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
        }

    def save(self) -> Path:
        # save session to ~/.next-cli/sessions/WORKSPACE_YYYY-MM-DD_HH-MM-SS.json
        base = user_config_dir() / "sessions"
        base.mkdir(parents=True, exist_ok=True)
        ws = workspace_name()
        name = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(self.started))
        path = base / f"{ws}_{name}.json"
        counter = 1
        while path.exists():
            path = base / f"{ws}_{name}_{counter}.json"
            counter += 1
        try:
            path.write_text(json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
        except OSError:
            pass
        return path
