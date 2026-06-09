"""Agent detail screen: shows full message history for one agent."""

from __future__ import annotations

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from nextcli.llm.provider import Message


class AgentDetailScreen(ModalScreen[None]):
    """Modal screen showing one agent's full conversation."""

    DEFAULT_CSS = """
    AgentDetailScreen {
        align: center middle;
        background: #0d1117 80%;
    }
    #detail_card {
        width: 90%;
        height: 90%;
        border: round #30363d;
        background: #161b22;
        padding: 1 2;
    }
    #detail_header {
        height: auto;
        color: #58a6ff;
        text-style: bold;
    }
    #detail_body {
        height: 1fr;
        overflow-y: auto;
    }
    .msg-system { color: #8b949e; }
    .msg-user   { color: #f0f6fc; }
    .msg-assistant { color: #d2a8ff; }
    .msg-tool   { color: #79c0ff; }
    """

    def __init__(self, agent_id: str, role: str, messages: list[Message]) -> None:
        super().__init__()
        self._agent_id = agent_id
        self._role = role
        self._messages = messages

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="detail_card"):
            yield Static(f"Agent: {self._agent_id}  ·  Role: {self._role}", id="detail_header")
            body = VerticalScroll(id="detail_body")
            yield body
            yield Button("Close", id="close_btn", variant="primary")

    def on_mount(self) -> None:
        body = self.query_one("#detail_body", VerticalScroll)
        for msg in self._messages:
            row = Static()
            body.mount(row)
            row.update(self._render_message(msg))

    def _render_message(self, msg: Message) -> Panel:
        role = msg.role
        content = msg.content or ""
        title = role.upper()
        if role == "system":
            style = "grey50"
            border = "#30363d"
        elif role == "user":
            style = "white"
            border = "#58a6ff"
        elif role == "assistant":
            style = "rgb(210,168,255)"
            border = "#d2a8ff"
        else:
            style = "rgb(121,192,255)"
            border = "#79c0ff"
        text = Text(content, style=style)
        return Panel(text, title=f"[bold]{title}[/]", border_style=border, padding=(0, 1))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close_btn":
            self.dismiss(None)
