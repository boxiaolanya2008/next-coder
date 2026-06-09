"""Onboarding wizard: 4-step form to configure provider / API key / model.

Renders as a Textual ModalScreen on top of the main app. Each step shows
a header, a brief instruction, and the appropriate input widget. Arrow keys
navigate steps; Enter confirms the current step; Esc goes back.

Steps:
  1. Provider       — radio: anthropic / openai / mock (offline)
  2. API Key        — text input (masked, hidden for mock)
  3. Model          — selection list of preset models
  4. Save & Launch  — preview; Enter writes ~/.next-cli/config.json and exits
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, RadioButton, RadioSet, Static

from nextcli.config import UserConfig, user_config_path


# Preset models per provider. The user can also type a custom model on the
# "model" step.
_PRESETS: dict[str, list[str]] = {
    "anthropic": [
        "claude-sonnet-4-5",
        "claude-opus-4-1",
        "claude-haiku-4-5",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o1",
        "o3-mini",
    ],
    "custom": [
        # Common third-party presets — users can also type any model id.
        "anthropic/claude-sonnet-4-5",   # OpenRouter
        "openai/gpt-4o",                  # OpenRouter
        "deepseek-chat",                  # DeepSeek
        "moonshot-v1-128k",               # Moonshot
    ],
    "mock": [
        "mock",
    ],
}

# Default base URLs per third-party provider. Empty string means user must
# type it.
_CUSTOM_URL_PRESETS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek":   "https://api.deepseek.com/v1",
    "moonshot":   "https://api.moonshot.cn/v1",
    "ollama":     "http://localhost:11434/v1",
    "custom":     "",
}

_STEP_TITLES = [
    "① Choose provider",
    "② Enter API key",
    "③ Endpoint & model",
    "④ Save & launch",
]

_STEP_HINTS = [
    "Which LLM backend do you want? Use ↑/↓ then Space/Enter.",
    "Paste your key. It is stored locally with 0600 permissions.",
    "Pick a model preset or type a custom id. For 'Custom' choose a base URL too.",
    "Review and press Enter to save and start the main app.",
]


class _StepHeader(Static):
    DEFAULT_CSS = """
    _StepHeader {
        height: auto;
        padding: 1 0 0 0;
    }
    """

    def __init__(self, step: int, total: int, title: str, hint: str) -> None:
        super().__init__()
        self._step = step
        self._total = total
        self._title = title
        self._hint = hint

    def render(self) -> Text:
        # progress bar: filled blocks for done, dim for remaining
        bar = Text()
        for i in range(self._total):
            if i < self._step:
                bar.append("━", style="cyan bold")
            elif i == self._step:
                bar.append("●", style="cyan bold")
            else:
                bar.append("─", style="grey35")
            if i < self._total - 1:
                bar.append(" ")
        t = Text()
        t.append_text(bar)
        t.append("\n")
        t.append(self._title, style="white bold")
        t.append("\n")
        t.append(self._hint, style="grey70")
        return t


class OnboardingScreen(ModalScreen[UserConfig | None]):
    """Modal 4-step wizard. Returns the saved UserConfig (or None on cancel)."""

    BINDINGS = [
        Binding("escape", "prev", "Back", show=True),
        Binding("enter", "next", "Next", show=True),
        Binding("right", "next", "Next", show=False),
        Binding("left", "prev", "Back", show=False),
    ]

    DEFAULT_CSS = """
    OnboardingScreen {
        align: center middle;
        background: #0d1117 80%;
    }
    #onboard_card {
        width: 72;
        height: auto;
        max-height: 90%;
        border: round #30363d;
        background: #161b22;
        padding: 1 2;
    }
    #step_body {
        height: auto;
        max-height: 18;
        padding: 0 0;
        overflow-y: auto;
    }
    #nav {
        dock: bottom;
        height: 3;
        align-horizontal: right;
    }
    Button {
        margin-left: 1;
    }
    .hint {
        color: #6e7681;
    }
    Input {
        margin-top: 0;
        margin-bottom: 1;
    }
    ListView {
        height: 6;
        margin-top: 0;
        margin-bottom: 1;
        border: round #30363d;
    }
    ListView > ListItem {
        padding: 0 1;
    }
    """

    TOTAL_STEPS: ClassVar[int] = 4

    def __init__(self) -> None:
        super().__init__()
        self._step = 0
        self._draft = UserConfig.load()
        if not self._draft.anthropic_model:
            self._draft.anthropic_model = "claude-sonnet-4-5"
        if not self._draft.openai_model:
            self._draft.openai_model = "gpt-4o"

    def compose(self) -> ComposeResult:
        with Vertical(id="onboard_card"):
            yield _StepHeader(
                self._step,
                self.TOTAL_STEPS,
                _STEP_TITLES[self._step],
                _STEP_HINTS[self._step],
            )
            with VerticalScroll(id="step_body"):
                yield from self._build_step()
            with Horizontal(id="nav"):
                yield Button("Cancel", id="cancel_btn", variant="default")
                yield Button("Back", id="back_btn", variant="default")
                yield Button("Next →", id="next_btn", variant="primary")

    def _build_step(self):
        """Yield the input widgets for the current step."""
        if self._step == 0:
            yield RadioSet(
                RadioButton("Anthropic (Claude)", id="prov_anthropic"),
                RadioButton("OpenAI (GPT / o-series)", id="prov_openai"),
                RadioButton(
                    "Custom (any OpenAI-compatible endpoint: OpenRouter, "
                    "DeepSeek, Moonshot, Ollama…)",
                    id="prov_custom",
                ),
                RadioButton("Mock (offline demo, no key needed)", id="prov_mock"),
                id="provider_radio",
            )
        elif self._step == 1:
            yield Input(
                placeholder="sk-ant-...  or  sk-...  (leave empty for some local servers)",
                password=True,
                id="api_key_input",
            )
        elif self._step == 2:
            # For custom: also ask for base URL preset + free text
            if self._draft.provider == "custom":
                yield Static("Base URL  (pick a preset or type below):", classes="hint")
                url_items = [
                    ListItem(Label(label), id=f"url_{key}")
                    for key, label in [
                        ("openrouter", "OpenRouter  ·  openrouter.ai/api/v1"),
                        ("deepseek",   "DeepSeek    ·  api.deepseek.com/v1"),
                        ("moonshot",   "Moonshot    ·  api.moonshot.cn/v1"),
                        ("ollama",     "Ollama      ·  localhost:11434/v1"),
                        ("custom",     "Custom URL  ·  (type below)"),
                    ]
                ]
                yield ListView(*url_items, id="url_list")
                yield Input(
                    placeholder="https://…/v1",
                    id="base_url_input",
                )
            yield Static("Model id  (type a custom id or pick a preset):", classes="hint")
            yield Input(placeholder="e.g. gpt-4o, claude-sonnet-4-5, deepseek-chat, …", id="model_input")
            items = [
                ListItem(Label(m), id=f"model_{i}")
                for i, m in enumerate(self._presets())
            ]
            yield ListView(*items, id="model_list")
        elif self._step == 3:
            yield Static(self._summary(), id="summary")

    def _presets(self) -> list[str]:
        return _PRESETS.get(self._draft.provider, ["mock"])

    def _summary(self) -> Text:
        u = self._draft
        t = Text()
        t.append("Provider:  ", style="grey70")
        t.append(u.provider or "(not set)", style="cyan bold")
        t.append("\n")
        if u.provider == "anthropic":
            t.append("API Key:   ", style="grey70")
            t.append(self._mask(u.anthropic_api_key) or "(not set)", style="green")
            t.append("\n")
            t.append("Model:     ", style="grey70")
            t.append(u.anthropic_model, style="green")
        elif u.provider == "openai":
            t.append("API Key:   ", style="grey70")
            t.append(self._mask(u.openai_api_key) or "(not set)", style="green")
            t.append("\n")
            t.append("Model:     ", style="grey70")
            t.append(u.openai_model, style="green")
        elif u.provider == "custom":
            t.append("API Key:   ", style="grey70")
            t.append(self._mask(u.custom_api_key) or "(empty — some local servers don't need one)", style="green")
            t.append("\n")
            t.append("Base URL:  ", style="grey70")
            t.append(u.custom_base_url or "(not set)", style="green")
            t.append("\n")
            t.append("Model:     ", style="grey70")
            t.append(u.custom_model or "(not set)", style="green")
        else:
            t.append("Mode:      ", style="grey70")
            t.append("offline mock — no network calls", style="yellow")
        t.append("\n\n")
        t.append(f"Saved to:  {user_config_path()}", style="grey50")
        return t

    @staticmethod
    def _mask(s: str) -> str:
        if not s:
            return ""
        if len(s) <= 8:
            return "•" * len(s)
        return s[:4] + "•" * (len(s) - 8) + s[-4:]

    # ---- event handling ----

    def on_mount(self) -> None:
        self._refresh_selection()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Pressing Enter inside an Input advances to the next step,
        # just like clicking the Next button.
        self.action_next()

    def _pull_widgets_to_draft(self) -> None:
        """Read the current Input widget values back into the draft.

        `on_input_changed` is only fired by user typing — not by our own
        `inp.value = "…"` in `_refresh_selection`. This method makes sure
        whatever is in the widgets right now ends up in the draft before
        we validate / commit.
        """
        try:
            if self._step == 1:
                inp = self.query_one("#api_key_input", Input)
                v = inp.value
                if self._draft.provider == "anthropic":
                    self._draft.anthropic_api_key = v
                elif self._draft.provider == "openai":
                    self._draft.openai_api_key = v
                elif self._draft.provider == "custom":
                    self._draft.custom_api_key = v
            elif self._step == 2:
                if self._draft.provider == "custom":
                    try:
                        self._draft.custom_base_url = self.query_one("#base_url_input", Input).value
                    except Exception:
                        pass
                try:
                    mv = self.query_one("#model_input", Input).value
                    if self._draft.provider == "anthropic":
                        self._draft.anthropic_model = mv
                    elif self._draft.provider == "openai":
                        self._draft.openai_model = mv
                    elif self._draft.provider == "custom":
                        self._draft.custom_model = mv
                except Exception:
                    pass
        except Exception:
            pass

    def _refresh_selection(self) -> None:
        """Apply the draft to the freshly-built widgets."""
        try:
            if self._step == 0:
                rs = self.query_one("#provider_radio", RadioSet)
                mapping = {
                    "anthropic": "prov_anthropic",
                    "openai":    "prov_openai",
                    "custom":    "prov_custom",
                    "mock":      "prov_mock",
                }
                bid = mapping.get(self._draft.provider)
                if bid:
                    btn = self.query_one(f"#{bid}", RadioButton)
                    btn.value = True
            elif self._step == 1:
                inp = self.query_one("#api_key_input", Input)
                if self._draft.provider == "anthropic" and self._draft.anthropic_api_key:
                    inp.value = self._draft.anthropic_api_key
                elif self._draft.provider == "openai" and self._draft.openai_api_key:
                    inp.value = self._draft.openai_api_key
                elif self._draft.provider == "custom" and self._draft.custom_api_key:
                    inp.value = self._draft.custom_api_key
            elif self._step == 2:
                if self._draft.provider == "custom" and self._draft.custom_base_url:
                    try:
                        self.query_one("#base_url_input", Input).value = self._draft.custom_base_url
                    except Exception:
                        pass
                inp = self.query_one("#model_input", Input)
                if self._draft.provider == "openai":
                    inp.value = self._draft.openai_model or "gpt-4o"
                elif self._draft.provider == "anthropic":
                    inp.value = self._draft.anthropic_model or "claude-sonnet-4-5"
                elif self._draft.provider == "custom":
                    inp.value = self._draft.custom_model
                else:
                    inp.value = "mock"
        except Exception:
            pass

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        bid = event.pressed.id or ""
        if bid == "prov_anthropic":
            self._draft.provider = "anthropic"
        elif bid == "prov_openai":
            self._draft.provider = "openai"
        elif bid == "prov_custom":
            self._draft.provider = "custom"
        elif bid == "prov_mock":
            self._draft.provider = "mock"

    def on_input_changed(self, event: Input.Changed) -> None:
        wid = event.input.id
        if wid == "api_key_input":
            if self._draft.provider == "anthropic":
                self._draft.anthropic_api_key = event.value
            elif self._draft.provider == "openai":
                self._draft.openai_api_key = event.value
            elif self._draft.provider == "custom":
                self._draft.custom_api_key = event.value
        elif wid == "model_input":
            if self._draft.provider == "anthropic":
                self._draft.anthropic_model = event.value
            elif self._draft.provider == "openai":
                self._draft.openai_model = event.value
            elif self._draft.provider == "custom":
                self._draft.custom_model = event.value
        elif wid == "base_url_input":
            self._draft.custom_base_url = event.value

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        try:
            label_widget = event.item.query_one(Label)
            label_text = str(label_widget.renderable)
        except Exception:
            return
        if not label_text:
            return
        list_id = event.list_view.id if event.list_view else ""
        if list_id == "model_list":
            m = label_text
            if self._draft.provider == "anthropic":
                self._draft.anthropic_model = m
            elif self._draft.provider == "openai":
                self._draft.openai_model = m
            elif self._draft.provider == "custom":
                self._draft.custom_model = m
            try:
                self.query_one("#model_input", Input).value = m
            except Exception:
                pass
        elif list_id == "url_list":
            # Map the chosen label back to a preset key by prefix match
            for key, full_label in [
                ("openrouter", "OpenRouter"),
                ("deepseek",   "DeepSeek"),
                ("moonshot",   "Moonshot"),
                ("ollama",     "Ollama"),
                ("custom",     "Custom URL"),
            ]:
                if label_text.startswith(full_label):
                    url = _CUSTOM_URL_PRESETS[key]
                    if url:
                        self._draft.custom_base_url = url
                        try:
                            self.query_one("#base_url_input", Input).value = url
                        except Exception:
                            pass
                    break

    # ---- navigation ----

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "cancel_btn":
            self.dismiss(None)
        elif bid == "back_btn":
            self.action_prev()
        elif bid == "next_btn":
            self.action_next()

    def action_prev(self) -> None:
        if self._step == 0:
            self.dismiss(None)
            return
        self._step -= 1
        self._rebuild()

    def action_next(self) -> None:
        # Pull the latest values from the input widgets into the draft so
        # that programmatic .value = … (refresh) AND user-typed values are
        # both reflected, even if the Changed event did not fire.
        self._pull_widgets_to_draft()

        # Validate current step
        if self._step == 0 and not self._draft.provider:
            self._flash("Please pick a provider first.")
            return
        if self._step == 1:
            if self._draft.provider not in {"mock", "custom"} and not self._has_key():
                self._flash("Please enter an API key (or go back and pick Mock).")
                return
        if self._step == 2:
            if self._draft.provider == "custom" and not self._draft.custom_base_url:
                self._flash("Please choose a base URL or type one below.")
                return
            if not self._has_model():
                self._flash("Please pick or type a model id.")
                return
        if self._step == self.TOTAL_STEPS - 1:
            self._commit()
            return
        self._step += 1
        self._rebuild()

    def _has_key(self) -> bool:
        if self._draft.provider == "anthropic":
            return bool(self._draft.anthropic_api_key)
        if self._draft.provider == "openai":
            return bool(self._draft.openai_api_key)
        return True

    def _has_model(self) -> bool:
        if self._draft.provider == "anthropic":
            return bool(self._draft.anthropic_model)
        if self._draft.provider == "openai":
            return bool(self._draft.openai_model)
        if self._draft.provider == "custom":
            return bool(self._draft.custom_model)
        return True

    def _commit(self) -> None:
        self._draft.onboarded = True
        try:
            self._draft.save()
        except OSError as exc:
            self._flash(f"Save failed: {exc}")
            return
        self.dismiss(self._draft)

    def _flash(self, msg: str) -> None:
        try:
            nav = self.query_one("#nav")
            nav.border_title = msg
        except Exception:
            pass

    async def _rebuild_async(self) -> None:
        body = self.query_one("#step_body", VerticalScroll)
        for child in list(body.children):
            child.remove()
        for w in self._build_step():
            await body.mount(w)
        # Update the header in place. Calling .update(Text) makes the
        # widget re-render with the new content.
        try:
            header = self.query_one(_StepHeader)
            header._step = self._step
            header._title = _STEP_TITLES[self._step]
            header._hint = _STEP_HINTS[self._step]
            header.refresh()
        except Exception:
            pass
        self._refresh_selection()
        # Auto-focus the right input so the user can just start typing.
        self._focus_current_step()

    def _focus_current_step(self) -> None:
        try:
            if self._step == 1:
                self.query_one("#api_key_input", Input).focus()
            elif self._step == 2:
                if self._draft.provider == "custom":
                    try:
                        self.query_one("#base_url_input", Input).focus()
                        return
                    except Exception:
                        pass
                self.query_one("#model_input", Input).focus()
        except Exception:
            pass

    def _rebuild(self) -> None:
        # Wrap the async rebuild so callers (sync) can fire-and-forget.
        asyncio.create_task(self._rebuild_async())
