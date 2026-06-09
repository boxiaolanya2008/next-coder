"""Custom Textual widgets: StatusPill."""

from __future__ import annotations

from rich.text import Text
from textual.message import Message
from textual.widgets import Static

_STATE_GLYPH = {
    "starting":  "◌",
    "thinking":  "◐",
    "tooling":   "◑",
    "done":      "●",
    "error":     "✕",
    "cancelled": "⊘",
}

_ROLE_COLOR = {
    "planner":     "rgb(210,168,255)",
    "explorer":    "rgb(121,192,255)",
    "implementer": "rgb(86,163,100)",
    "reviewer":    "rgb(255,166,87)",
}

_STATE_COLOR = {
    "starting":  "rgb(210,153,34)",
    "thinking":  "rgb(88,166,255)",
    "tooling":   "rgb(255,166,87)",
    "done":      "rgb(86,163,100)",
    "error":     "rgb(248,81,73)",
    "cancelled": "rgb(110,118,129)",
}


class StatusPill(Static):
    """A single-agent status row, color-coded by role + state.

    Layout (12 + 3 + 12 columns):
      [role          ]  [glyph] [state     ]
    """

    DEFAULT_CSS = """
    StatusPill {
        height: 1;
        padding: 0 1;
    }
    """

    class DoubleClicked(Message):
        """Emitted when the pill is double-clicked."""
        def __init__(self, agent_id: str, role: str) -> None:
            super().__init__()
            self.agent_id = agent_id
            self.role = role

    def __init__(self, agent_id: str, role: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._agent_id = agent_id
        self._role = role
        self._state = "starting"

    def update_state(self, state: str) -> None:
        self._state = state
        self.refresh()

    def render(self) -> Text:  # Textual's hook
        state = self._state
        role = self._role
        glyph = _STATE_GLYPH.get(state, "?")
        state_color = _STATE_COLOR.get(state, "white")
        role_color = _ROLE_COLOR.get(role, "white")
        t = Text()
        t.append(f"{role:<12}", style=f"bold {role_color}")
        t.append("  ")
        t.append(glyph, style=state_color)
        t.append("  ")
        t.append(state, style=state_color)
        return t

    def on_click(self, event) -> None:
        if getattr(event, "click_count", 1) >= 2:
            self.post_message(self.DoubleClicked(self._agent_id, self._role))
