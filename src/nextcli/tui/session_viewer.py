"""Session viewer: replay a saved session's events into the panes."""

from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from nextcli.agent.events import AgentEvent, AgentRole
from nextcli.tui.panes import AgentBoard, ChatLog, ToolTrace
from nextcli.tui.session_save import Session


class SessionViewerScreen(ModalScreen[None]):
    """Read-only viewer for a saved session."""

    DEFAULT_CSS = """
    SessionViewerScreen {
        align: center middle;
        background: #0d1117 80%;
    }
    #viewer_card {
        width: 92%;
        height: 92%;
        border: round #30363d;
        background: #161b22;
        padding: 1 2;
    }
    #viewer_header {
        height: auto;
        color: #58a6ff;
        text-style: bold;
    }
    #viewer_body {
        height: 1fr;
    }
    #viewer_nav {
        dock: bottom;
        height: 3;
        align-horizontal: right;
    }
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._task = ""
        self._input_tokens = 0
        self._output_tokens = 0
        self._events: list[dict] = []
        self._load(path)

    def _load(self, path: Path) -> None:
        # use the safe Session.load that coerces bad fields
        s = Session.load(path)
        self._task = s.task
        self._input_tokens = s.total_input_tokens
        self._output_tokens = s.total_output_tokens
        self._events = list(s.events)

    def compose(self) -> ComposeResult:
        with Vertical(id="viewer_card"):
            yield Static(
                f"Session: {self._path.name}  ·  in={self._input_tokens}  out={self._output_tokens}",
                id="viewer_header",
            )
            body = Vertical(id="viewer_body")
            yield body
            with Vertical(id="viewer_nav"):
                yield Button("Close", id="close_btn", variant="primary")

    def on_mount(self) -> None:
        body = self.query_one("#viewer_body", Vertical)
        # mount transient panes into the body so we can reuse their handlers
        board = AgentBoard()
        chat = ChatLog()
        trace = ToolTrace()
        body.mount(board)
        body.mount(chat)
        body.mount(trace)

        # first render task prompt
        task_text = self._task
        if not isinstance(task_text, str):
            try:
                task_text = str(task_text) if task_text is not None else ""
            except Exception:
                task_text = ""
        if task_text:
            from rich.text import Text as _Text
            chat.write(_Text("> ", style="bold rgb(88,166,255)"))
            chat.write(_Text(task_text + "\n", style="white bold"))

        # replay events
        for ev in self._events:
            kind = ev.get("kind", "")
            role_val = ev.get("role", "system")
            try:
                role = AgentRole(role_val)
            except ValueError:
                continue
            event = AgentEvent(
                kind=kind,  # type: ignore[arg-type]
                agent_id=ev.get("agent_id", ""),
                role=role,
                ts=float(ev.get("ts", 0.0)),
                payload=ev.get("payload", {}),
            )
            board.handle_event(event)
            trace.handle_event(event)
            # main chat shows planner text only
            if kind == "text" and role == AgentRole.PLANNER:
                chat.handle_event(event)
            elif kind != "text":
                chat.handle_event(event)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close_btn":
            self.dismiss(None)
