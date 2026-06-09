"""The four TUI panes: AgentBoard, ChatLog, ToolTrace, InputBar.

Modern minimal dark theme: thin gray borders, uppercase section titles with
a left bar, monospace alignment. No emoji or heavy glyphs.
"""

from __future__ import annotations

import difflib
import time
from collections.abc import Iterable
from pathlib import Path

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Input, Static

from nextcli.agent.events import AgentEvent, AgentRole
from nextcli.tui.widgets import StatusPill

# Inline-text color names accepted by Rich. The CSS classes above are for
# widget-level styling; inline Text needs real color names.
_ROLE_COLOR = {
    "planner":     "rgb(210,168,255)",  # soft purple
    "explorer":    "rgb(121,192,255)",  # sky blue
    "implementer": "rgb(86,163,100)",   # green
    "reviewer":    "rgb(255,166,87)",   # warm orange
    "user":        "rgb(240,246,252)",  # near-white
    "system":      "rgb(110,118,129)",  # grey
}

_STATE_GLYPH = {
    "starting":   ("◌", "state-starting"),
    "thinking":   ("◐", "state-thinking"),
    "tooling":    ("◑", "state-tooling"),
    "done":       ("●", "state-done"),
    "error":      ("✕", "state-error"),
    "cancelled":  ("⊘", "state-cancelled"),
}


def _role_color(role: str) -> str:
    return _ROLE_COLOR.get(role, "white")


def _state_glyph(state: str) -> tuple[str, str]:
    return _STATE_GLYPH.get(state, ("?", "white"))


def _trunc(s: object, n: int) -> str:
    txt = repr(s) if not isinstance(s, str) else s
    txt = txt.replace("\n", " ⏎ ")
    if len(txt) > n:
        txt = txt[: n - 1] + "…"
    return txt


def _mount_trace(parent: Widget, content, classes: str = "trace-row") -> None:
    """Mount a Static row with the given content."""
    row = Static(classes=classes)
    parent.mount(row)
    row.update(content)


def _markdown_heavy(text: str) -> bool:
    # check if the text looks like markdown
    markers = ["# ", "## ", "### ", "**", "```", "`", "- ", "* ", "| ", "> "]
    return any(m in text for m in markers)


# ---------- AgentBoard ----------


class AgentBoard(VerticalScroll):
    """Top-left: a compact list of agents with status glyphs."""

    DEFAULT_CSS = """
    AgentBoard {
        height: 100%;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.border_title = "AGENTS"
        self._pills: dict[str, StatusPill] = {}
        self._get_agent_messages = None

    def handle_event(self, ev: AgentEvent) -> None:
        if ev.kind != "status":
            return
        pill = self._pills.get(ev.agent_id)
        if pill is None:
            pill = StatusPill(ev.agent_id, ev.role.value)
            self._pills[ev.agent_id] = pill
            self.mount(pill)
        pill.update_state(ev.payload.get("state", "starting"))

    def on_status_pill_double_clicked(self, event: StatusPill.DoubleClicked) -> None:
        # delegate to the app
        self.app.post_message(
            _AgentDetailRequested(event.agent_id, event.role)
        )


class _AgentDetailRequested(AgentEvent):
    """Internal TUI message to request opening an agent detail screen."""

    def __init__(self, agent_id: str, role: str) -> None:
        super().__init__(
            kind="status",
            agent_id=agent_id,
            role=AgentRole(role) if role in {r.value for r in AgentRole} else AgentRole.PLANNER,
            payload={"state": "detail_requested"},
        )
        self.detail_agent_id = agent_id
        self.detail_role = role


# ---------- ChatLog ----------


class ChatLog(VerticalScroll):
    """Top-right (or main column on narrow screens): streamed text."""

    DEFAULT_CSS = """
    ChatLog {
        height: 100%;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.border_title = "CHAT"
        self._rows: dict[str, Static] = {}
        self._texts: dict[str, Text] = {}
        self._last_scroll = 0.0

    def write(self, content: RenderableType) -> None:
        # add a normal chat row
        row = Static()
        self.mount(row)
        row.update(content)
        self._maybe_scroll()

    def _maybe_scroll(self) -> None:
        # throttle scroll to avoid blocking the UI
        now = time.time()
        if now - self._last_scroll > 0.15:
            self.scroll_end(animate=False)
            self._last_scroll = now

    def handle_event(self, ev: AgentEvent) -> None:
        if ev.kind == "status":
            self._handle_status(ev)
        elif ev.kind == "text":
            self._append_text(ev)
        elif ev.kind in {"done", "error"}:
            self._finish_role(ev.role.value)

    def _handle_status(self, ev: AgentEvent) -> None:
        state = str(ev.payload.get("state", ""))
        role = ev.role.value
        if state == "thinking":
            self._ensure_row(role)
        elif state == "tooling":
            self._append_line(role, "\n[using tools...]", "grey50")
        elif state in {"done", "cancelled", "error"}:
            self._finish_role(role)

    def _ensure_row(self, role: str) -> Static:
        row = self._rows.get(role)
        if row is not None:
            return row
        color = _role_color(role)
        row = Static()
        self._rows[role] = row
        self.mount(row)
        text = Text()
        text.append("\n")
        text.append("▌ ", style=color)
        text.append(f"{role:<12}", style=f"bold {color}")
        text.append("thinking...", style="grey50")
        self._texts[role] = text
        row.update(text)
        self._maybe_scroll()
        return row

    def _append_text(self, ev: AgentEvent) -> None:
        role = ev.role.value
        row = self._ensure_row(role)
        text = self._texts.get(role)
        if text is None:
            text = Text()
            self._texts[role] = text
        if "thinking..." in text.plain:
            text = Text()
            text.append("\n")
            text.append("▌ ", style=_role_color(role))
            text.append(f"{role:<12}", style=f"bold {_role_color(role)}")
            text.append("\n")
            self._texts[role] = text
        delta = str(ev.payload.get("delta", ""))
        if delta:
            text.append(delta, style=_role_color(role))
            row.update(text)
            row.refresh()
            self.scroll_end(animate=False)

    def _append_line(self, role: str, value: str, style: str) -> None:
        row = self._ensure_row(role)
        text = self._texts.get(role)
        if text is None:
            text = Text()
            self._texts[role] = text
        if value not in text.plain:
            text.append(value, style=style)
            row.update(text)
            self._maybe_scroll()

    def _finish_role(self, role: str) -> None:
        # when done, re-render with markdown if applicable
        text = self._texts.pop(role, None)
        row = self._rows.pop(role, None)
        if row is None or text is None:
            return
        full = text.plain.strip()
        if _markdown_heavy(full):
            row.update(Markdown(full))
        self._maybe_scroll()


# ---------- ToolTrace ----------


class ToolTrace(VerticalScroll):
    """Bottom: tool calls and their results, attributed to the agent."""

    DEFAULT_CSS = """
    ToolTrace {
        height: 100%;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.border_title = "TOOL TRACE"
        self._rows: list[Static] = []
        self._last_write_content: dict[str, str] = {}  # path -> content for diff
        self._last_scroll = 0.0

    def _maybe_scroll(self) -> None:
        now = time.time()
        if now - self._last_scroll > 0.15:
            self.scroll_end(animate=False)
            self._last_scroll = now

    def handle_event(self, ev: AgentEvent) -> None:
        if ev.kind == "tool_call":
            self._handle_tool_call(ev)
        elif ev.kind == "tool_result":
            self._handle_tool_result(ev)
        elif ev.kind == "error":
            self._handle_error(ev)

    def _handle_tool_call(self, ev: AgentEvent) -> None:
        role = ev.role.value
        color = _role_color(role)
        name = ev.payload.get("name", "?")
        args = ev.payload.get("arguments", {})
        if name == "spawn_agent":
            child_role = args.get("role", "?")
            child_task = _trunc(args.get("task", ""), 60)
            t = Text()
            t.append("▌ ", style="rgb(210,168,255)")
            t.append(f"{role:<11}", style=color)
            t.append(" spawn → ", style="grey70")
            t.append(f"{child_role:<11}", style=_role_color(child_role))
            t.append(f"  {child_task}", style="grey70")
            _mount_trace(self, t)
        elif name == "edit_file":
            self._show_edit_diff(ev, role, color, args)
        elif name == "write_file":
            self._show_write_preview(ev, role, color, args)
        else:
            arg_repr = _trunc(args, 80)
            t = Text()
            t.append("▌ ", style=color)
            t.append(f"{role:<11}", style=color)
            t.append(f" {name}({arg_repr})", style="white")
            _mount_trace(self, t)
        self._maybe_scroll()

    def _show_edit_diff(self, ev: AgentEvent, role: str, color: str, args: dict) -> None:
        path = args.get("path", "")
        old = args.get("old", "")
        new = args.get("new", "")
        diff = list(difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        ))
        if not diff:
            diff = ["(no changes)"]
        diff_text = "".join(diff)
        syntax = Syntax(diff_text, "diff", theme="monokai", background_color="#0d1117")
        panel = Panel(
            syntax,
            title=f"[bold {color}]{role}[/]  edit_file  {path}",
            border_style=color,
            padding=(0, 1),
        )
        _mount_trace(self, panel)
        self._maybe_scroll()

    def _show_write_preview(self, ev: AgentEvent, role: str, color: str, args: dict) -> None:
        path = args.get("path", "")
        content = args.get("content", "")
        ext = Path(path).suffix.lstrip(".") or "text"
        lines = content.splitlines()
        preview = "\n".join(lines[:20])
        if len(lines) > 20:
            preview += f"\n... ({len(lines) - 20} more lines)"
        syntax = Syntax(preview, ext, theme="monokai", background_color="#0d1117")
        panel = Panel(
            syntax,
            title=f"[bold {color}]{role}[/]  write_file  {path}",
            border_style=color,
            padding=(0, 1),
        )
        _mount_trace(self, panel)
        self._maybe_scroll()

    def _handle_tool_result(self, ev: AgentEvent) -> None:
        role = ev.role.value
        color = _role_color(role)
        ok = ev.payload.get("ok", False)
        out = _trunc(ev.payload.get("output", ""), 100)
        t = Text()
        t.append("    ")
        if ok:
            t.append("✓ ", style="rgb(86,163,100)")
        else:
            t.append("✕ ", style="rgb(248,81,73)")
        t.append(out, style="rgb(110,118,129)")
        _mount_trace(self, t)
        self._maybe_scroll()

    def _handle_error(self, ev: AgentEvent) -> None:
        role = ev.role.value
        err_text = str(ev.payload.get("error", ""))
        panel = Panel(
            Text(err_text, style="rgb(248,81,73)"),
            title=f"[bold rgb(248,81,73)]{role} error[/]",
            border_style="rgb(248,81,73)",
            padding=(0, 1),
        )
        _mount_trace(self, panel, classes="trace-error")
        self._maybe_scroll()


# ---------- InputBar ----------


class InputBar(Input):
    """Single-line user prompt at the bottom."""

    DEFAULT_CSS = """
    InputBar {
        height: 100%;
        background: #010409;
        border: none;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(
            placeholder="Describe a task…  (type / for commands, Enter to run, Ctrl-C to quit)",
            **kwargs,
        )
