"""Resume screen (ClaudeCode-style): bottom drawer that lists past sessions
for the current workspace with search, relative timestamps, task summary
preview, and Resume / View / Cancel actions.

Key UX differences from a plain modal:
  - docked at the bottom so the main TUI stays visible behind
  - top search bar filters as you type
  - rows show relative time + task summary + token summary
  - Enter pops a small inline action row: Resume / View / Cancel
  - Esc dismisses the whole drawer
"""

from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Static

from nextcli.tui.session_save import (
    Session,
    list_workspace_sessions,
    workspace_name,
)


def _relative_time(ts: float) -> str:
    if not ts:
        return "?"
    diff = max(0.0, _time.time() - ts)
    if diff < 60:
        return "just now"
    if diff < 3600:
        m = int(diff // 60)
        return f"{m}m ago"
    if diff < 86400:
        h = int(diff // 3600)
        return f"{h}h ago"
    if diff < 86400 * 7:
        d = int(diff // 86400)
        return f"{d}d ago"
    return _time.strftime("%Y-%m-%d", _time.localtime(ts))


@dataclass
class _SessionEntry:
    path: Path
    task: str
    started: float
    ended: float | None
    input_tokens: int
    output_tokens: int
    events: int

    @classmethod
    def from_path(cls, path: Path) -> "_SessionEntry":
        s = Session.load(path)
        task = s.task.strip() or "(no task text)"
        return cls(
            path=path,
            task=task,
            started=s.started,
            ended=s.ended,
            input_tokens=s.total_input_tokens,
            output_tokens=s.total_output_tokens,
            events=len(s.events),
        )

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        return needle.lower() in self.task.lower()


@dataclass
class ResumeChoice:
    """Returned to the app: which path + which action the user chose."""

    path: Path
    action: str  # "resume" | "view"


class ResumeScreen(ModalScreen[ResumeChoice | None]):
    """Bottom-docked drawer showing the workspace's past sessions."""

    DEFAULT_CSS = """
    ResumeScreen {
        align: center bottom;
        background: transparent;
    }
    #resume_drawer {
        width: 100%;
        height: 60%;
        max-height: 28;
        background: #161b22;
        border: round #30363d;
        padding: 0 1;
    }
    #resume_header {
        height: 1;
        color: #58a6ff;
        text-style: bold;
        padding: 0 1;
    }
    #resume_search {
        height: 3;
        margin: 0 0 1 0;
    }
    #resume_search > Input {
        background: #0d1117;
        border: round #30363d;
    }
    #resume_list {
        height: 1fr;
        background: #0d1117;
        border: round #21262d;
    }
    #resume_list > ListItem {
        padding: 0 1;
    }
    #resume_list > ListItem.--highlight {
        background: #1f6feb;
    }
    .resume-row-time  { color: rgb(88,166,255);  text-style: bold; }
    .resume-row-task  { color: white; }
    .resume-row-meta  { color: rgb(110,118,129); }
    .resume-empty     { color: #6e7681; padding: 1 2; }
    .resume-row-rel   { color: rgb(255,166,87); }
    #resume_actions {
        height: 3;
        dock: bottom;
        align-horizontal: right;
    }
    #resume_actions Button {
        margin-left: 1;
    }
    """

    BINDINGS: ClassVar[list] = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+r", "do_resume", "Resume", show=False),
        Binding("ctrl+v", "do_view", "View", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[_SessionEntry] = []
        self._filtered: list[_SessionEntry] = []
        self._load_all()

    def _load_all(self) -> None:
        self._entries = [_SessionEntry.from_path(p) for p in list_workspace_sessions()]
        self._filtered = list(self._entries)

    def compose(self) -> ComposeResult:
        with Vertical(id="resume_drawer"):
            yield Static(
                f"Resume session · workspace: {workspace_name()}  ·  {len(self._entries)} session(s)",
                id="resume_header",
            )
            yield Input(
                placeholder="Search past sessions by task text…",
                id="resume_search",
            )
            if not self._filtered:
                yield Static("(no sessions in this workspace)", classes="resume-empty", id="resume_list_placeholder")
            else:
                items = [ListItem(self._render_row(i, e), id=f"resume_{i}") for i, e in enumerate(self._filtered)]
                yield ListView(*items, id="resume_list")
            with Horizontal(id="resume_actions"):
                yield Button("Cancel", id="cancel_btn", variant="default")
                yield Button("View", id="view_btn", variant="default")
                yield Button("Resume ▶", id="resume_btn", variant="primary")

    def on_mount(self) -> None:
        # focus the search input so the user can immediately type to filter
        try:
            self.query_one("#resume_search", Input).focus()
        except Exception:
            pass

    def _render_row(self, index: int, entry: _SessionEntry) -> Static:
        row = Static(classes="resume-row")
        t = Text()
        rel = _relative_time(entry.started)
        abs_ts = _time.strftime("%Y-%m-%d %H:%M", _time.localtime(entry.started))
        t.append(f"  {rel:<10}", style="rgb(255,166,87)")
        t.append(f"  {abs_ts}  ", style="rgb(110,118,129)")
        summary = entry.task
        if len(summary) > 70:
            summary = summary[:70] + "…"
        t.append(summary, style="white")
        t.append("\n", style="rgb(110,118,129)")
        meta_parts: list[str] = []
        if entry.input_tokens:
            meta_parts.append(f"in={entry.input_tokens}")
        if entry.output_tokens:
            meta_parts.append(f"out={entry.output_tokens}")
        if entry.events:
            meta_parts.append(f"events={entry.events}")
        if entry.ended and entry.started:
            secs = int(entry.ended - entry.started)
            meta_parts.append(f"{secs}s")
        t.append("           ", style="rgb(110,118,129)")
        t.append("  ".join(meta_parts), style="rgb(110,118,129)")
        row.update(t)
        return row

    def _current_entry(self) -> _SessionEntry | None:
        if not self._filtered:
            return None
        try:
            lv = self.query_one("#resume_list", ListView)
        except Exception:
            return None
        idx = lv.index if lv.index is not None else 0
        if 0 <= idx < len(self._filtered):
            return self._filtered[idx]
        return None

    # ---- event handlers ----

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "resume_search":
            return
        needle = event.value.strip()
        self._filtered = [e for e in self._entries if e.matches(needle)]
        # rebuild list widget
        try:
            old = self.query_one("#resume_list", ListView)
            old.remove()
        except Exception:
            pass
        # remove placeholder if present
        try:
            ph = self.query_one("#resume_list_placeholder", Static)
            ph.remove()
        except Exception:
            pass
        container = self.query_one("#resume_drawer", Vertical)
        if not self._filtered:
            container.mount(Static("(no matching sessions)", classes="resume-empty", id="resume_list_placeholder"))
            return
        items = [ListItem(self._render_row(i, e), id=f"resume_{i}") for i, e in enumerate(self._filtered)]
        new_lv = ListView(*items, id="resume_list")
        container.mount(new_lv)
        new_lv.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Enter on a row: default to Resume
        self._dismiss_with("resume")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "cancel_btn":
            self.dismiss(None)
        elif bid == "view_btn":
            self._dismiss_with("view")
        elif bid == "resume_btn":
            self._dismiss_with("resume")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_do_resume(self) -> None:
        self._dismiss_with("resume")

    def action_do_view(self) -> None:
        self._dismiss_with("view")

    def _dismiss_with(self, action: str) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        self.dismiss(ResumeChoice(path=entry.path, action=action))
