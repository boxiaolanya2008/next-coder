"""Command palette: shows when the user types "/" in the input bar.

Renders a floating list of commands with descriptions, filtered as the user
keeps typing. Up/Down to navigate, Enter to insert, Escape to dismiss.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    aliases: tuple[str, ...] = ()


COMMANDS: list[Command] = [
    Command(
        "/resume",
        "Browse and view past sessions for this workspace",
        aliases=("/sessions",),
    ),
    Command(
        "/config",
        "Reconfigure provider, API key, or model",
        aliases=("/setup", "/onboard"),
    ),
    Command(
        "/clear",
        "Clear the chat log and agent board",
    ),
    Command(
        "/help",
        "Show available commands and keybindings",
    ),
]


class CommandPalette(Vertical):
    """Floating command palette anchored above the input bar."""

    DEFAULT_CSS = """
    CommandPalette {
        dock: bottom;
        height: auto;
        max-height: 12;
        margin: 0 1 0 1;
        background: #161b22;
        border: round #30363d;
        padding: 0 1;
        display: none;
    }
    CommandPalette.active {
        display: block;
    }
    .cmd-row {
        height: 1;
        padding: 0 1;
    }
    .cmd-row.selected {
        background: #1f6feb;
    }
    .cmd-empty {
        color: #6e7681;
        padding: 1 1;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._filter: str = ""
        self._matches: list[Command] = list(COMMANDS)
        self._selected: int = 0

    def show(self) -> None:
        self._filter = ""
        self._matches = list(COMMANDS)
        self._selected = 0
        self.add_class("active")
        self._render_rows()

    def hide(self) -> None:
        self.remove_class("active")

    def is_visible(self) -> bool:
        return self.has_class("active")

    def update_filter(self, text: str) -> None:
        # text is the raw user input, may include the leading "/"
        self._filter = text.strip()
        if not self._filter.startswith("/"):
            self._matches = list(COMMANDS)
        else:
            needle = self._filter.lower()
            self._matches = [
                c for c in COMMANDS
                if needle in c.name.lower()
                or any(needle in a.lower() for a in c.aliases)
            ]
        self._selected = 0
        self._render_rows()

    def move_up(self) -> None:
        if self._matches:
            self._selected = (self._selected - 1) % len(self._matches)
            self._render_rows()

    def move_down(self) -> None:
        if self._matches:
            self._selected = (self._selected + 1) % len(self._matches)
            self._render_rows()

    def current(self) -> Command | None:
        if not self._matches:
            return None
        return self._matches[self._selected]

    def _render_rows(self) -> None:
        # remove old rows
        for child in list(self.children):
            child.remove()
        if not self._matches:
            self.mount(Static("(no matching commands)", classes="cmd-empty"))
            return
        for i, cmd in enumerate(self._matches):
            row = Static(classes="cmd-row")
            t = Text()
            t.append(f"  {cmd.name:<14}", style="bold rgb(88,166,255)")
            t.append("  ")
            t.append(cmd.description, style="white")
            if cmd.aliases:
                t.append("  ")
                t.append(", ".join(cmd.aliases), style="grey50")
            if i == self._selected:
                row.set_class(i == self._selected, "selected")
                t.stylize("on rgb(31,111,235)")
            row.update(t)
            self.mount(row)
