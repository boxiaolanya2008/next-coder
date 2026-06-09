"""The Textual App: wires the EventBus drain loop, the four panes, and the
input bar together. Runs the Orchestrator on Enter.

First run: shows the OnboardingScreen (4-step wizard) to capture
provider / API key / model. The result is persisted to
~/.next-cli/config.json and the main app boots.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from nextcli.agent.events import AgentEvent, AgentRole
from nextcli.config import Config, UserConfig
from nextcli.llm.mock_provider import MockProvider
from nextcli.orchestrator.runner import Orchestrator
from nextcli.tui.agent_detail import AgentDetailScreen
from nextcli.tui.onboarding import OnboardingScreen
from nextcli.tui.panes import (
    AgentBoard,
    ChatLog,
    InputBar,
    ToolTrace,
    _AgentDetailRequested,
)
from nextcli.tui.command_palette import CommandPalette
from nextcli.tui.resume_screen import ResumeChoice, ResumeScreen
from nextcli.tui.session_save import Session
from nextcli.tui.session_viewer import SessionViewerScreen
from nextcli.tools import default_registry
from nextcli.util.log import log_event

_TCSS_PATH = Path(__file__).parent / "styles.tcss"

# Pricing for claude-opus-4-6 (per 1M tokens)
_PRICE_INPUT = 15.0
_PRICE_OUTPUT = 75.0

# Default context window per provider/model (in tokens)
_DEFAULT_CONTEXT_WINDOW = 1_000_000

_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-8": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-5": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-haiku-4-5": 200_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "o1": 200_000,
    "o3-mini": 200_000,
}


def _resolve_context_window(config) -> int:
    # try to detect context window from the selected model name
    model = ""
    if config.provider == "anthropic":
        model = config.anthropic_model
    elif config.provider == "openai":
        model = config.openai_model
    elif config.provider == "custom":
        model = config.custom_model
    if not model:
        return _DEFAULT_CONTEXT_WINDOW
    model_l = model.lower()
    # exact match first
    if model_l in _CONTEXT_WINDOWS:
        return _CONTEXT_WINDOWS[model_l]
    # prefix match: e.g. "claude-opus-4-6-20260101" matches "claude-opus-4-6"
    for key, size in _CONTEXT_WINDOWS.items():
        if model_l.startswith(key):
            return size
    return _DEFAULT_CONTEXT_WINDOW


def _format_tokens(n: int) -> str:
    # render a token count compactly: 1234 -> "1.2K", 1_500_000 -> "1.5M"
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}K"
    return f"{n / 1_000_000:.2f}M"


class _PromptMark(Static):
    """Left-aligned prompt glyph in front of the input bar."""

    DEFAULT_CSS = """
    _PromptMark {
        width: 3;
        height: 100%;
        content-align: right middle;
        color: rgb(88,166,255);
        text-style: bold;
    }
    """

    def render(self) -> Text:
        return Text(">", style="bold rgb(88,166,255)")


class _TitleBar(Static):
    """Top bar showing brand, context usage, token stats, and cost."""

    DEFAULT_CSS = """
    _TitleBar {
        dock: top;
        height: 1;
        background: #010409;
        color: #58a6ff;
        text-style: bold;
        padding: 0 1;
    }
    """

    def __init__(self, context_window: int = _DEFAULT_CONTEXT_WINDOW, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._input_tokens = 0
        self._output_tokens = 0
        self._context_window = context_window
        self._context_peak = 0

    def set_context_window(self, size: int) -> None:
        self._context_window = max(size, 1)
        self._refresh()

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        peak = self._input_tokens + self._output_tokens
        if peak > self._context_peak:
            self._context_peak = peak
        self._refresh()

    def reset_stats(self) -> None:
        self._input_tokens = 0
        self._output_tokens = 0
        self._context_peak = 0
        self._refresh()

    def _refresh(self) -> None:
        self.update(self.render())

    def render(self) -> Text:
        t = Text()
        t.append(" nextcli  ·  parallel multi-agent CLI", style="bold rgb(88,166,255)")
        # context window usage
        used = max(self._input_tokens + self._output_tokens, self._context_peak)
        ratio = used / self._context_window if self._context_window else 0
        if ratio >= 0.9:
            ctx_color = "rgb(248,81,73)"
        elif ratio >= 0.7:
            ctx_color = "rgb(255,166,87)"
        else:
            ctx_color = "rgb(86,163,100)"
        used_str = _format_tokens(used)
        limit_str = _format_tokens(self._context_window)
        t.append("  ·  ctx ", style="grey50")
        t.append(f"{used_str}/{limit_str}", style=f"bold {ctx_color}")
        t.append(f" ({ratio*100:.0f}%)", style="grey50")
        # token stats
        if self._input_tokens or self._output_tokens:
            t.append("  ·  ", style="grey50")
            t.append(f"in={_format_tokens(self._input_tokens)}", style="rgb(121,192,255)")
            t.append("  ", style="grey50")
            t.append(f"out={_format_tokens(self._output_tokens)}", style="rgb(121,192,255)")
            cost = (
                self._input_tokens * _PRICE_INPUT / 1_000_000
                + self._output_tokens * _PRICE_OUTPUT / 1_000_000
            )
            t.append("  ", style="grey50")
            t.append(f"${cost:.4f}", style="rgb(86,163,100)")
        return t


class NextCliApp(App):
    CSS = _TCSS_PATH.read_text(encoding="utf-8")

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+r", "rerun_setup", "Reconfigure", show=True),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._orch: Orchestrator | None = None
        self._task_busy = False
        self._run_tasks: set[asyncio.Task] = set()
        self._session: Session | None = None
        self._title_bar: _TitleBar | None = None
        self._palette: CommandPalette | None = None

    # ---- layout ----

    def compose(self) -> ComposeResult:
        ctx = _resolve_context_window(self._config)
        self._title_bar = _TitleBar(context_window=ctx, id="title")
        yield self._title_bar
        with Vertical(id="main_grid"):
            yield AgentBoard(id="board")
            yield ChatLog(id="chat")
            yield ToolTrace(id="trace")
        self._palette = CommandPalette(id="palette")
        yield self._palette
        with Horizontal(id="input_row"):
            yield _PromptMark(id="prompt_mark")
            yield InputBar(id="input")
            yield Button("Send ▶", id="send_btn", variant="primary")

    # ---- lifecycle ----

    def on_mount(self) -> None:
        user_cfg = UserConfig.load()
        try:
            self.query_one("#input", InputBar).focus()
        except Exception:
            pass
        if not user_cfg.onboarded:
            self._show_onboarding()
        else:
            self._post_onboarding_greet()

    def _show_onboarding(self) -> None:
        def _on_done(saved: UserConfig | None) -> None:
            if saved is None:
                self._config = Config(
                    provider="mock",
                    anthropic_api_key=None,
                    openai_api_key=None,
                    custom_api_key=None,
                    custom_base_url=None,
                    anthropic_model="claude-sonnet-4-5",
                    openai_model="gpt-4o",
                    custom_model="",
                    use_mock=True,
                    cache_dir=self._config.cache_dir,
                )
                chat = self.query_one("#chat", ChatLog)
                chat.write(Text(
                    "Onboarding cancelled — running in offline mock mode.\n"
                    "Run :config in-app or edit ~/.next-cli/config.json to change later.",
                    style="grey70",
                ))
            else:
                self._config = Config.load()
                self._post_onboarding_greet()

        self.push_screen(OnboardingScreen(), _on_done)

    def _post_onboarding_greet(self) -> None:
        chat = self.query_one("#chat", ChatLog)
        provider = self._config.provider
        if self._config.use_mock or provider == "mock":
            chat.write(Text("ready · ", style="grey50"))
            chat.write(Text("mock mode", style="rgb(255,166,87) bold"))
            chat.write(Text("  (no API key needed)\n", style="grey50"))
        else:
            if provider == "anthropic":
                model = self._config.anthropic_model
            elif provider == "openai":
                model = self._config.openai_model
            elif provider == "custom":
                model = self._config.custom_model
            else:
                model = ""
            chat.write(Text("ready · ", style="grey50"))
            chat.write(Text(provider, style=f"rgb(121,192,255) bold"))
            chat.write(Text("  ·  ", style="grey50"))
            chat.write(Text(model, style="white"))
            chat.write(Text("\n", style="grey50"))
        chat.write(Text("type a task and press Enter.\n", style="grey50"))

    # ---- input handling ----

    def on_button_pressed(self, event) -> None:
        if event.button.id == "send_btn":
            self.action_submit_input()

    def on_input_submitted(self, event) -> None:
        from nextcli.tui.onboarding import OnboardingScreen
        if isinstance(self.app.screen, OnboardingScreen):
            return
        log_event("input_submitted", value=getattr(event, "value", None))
        # If palette is showing and a command is highlighted, run that command.
        if self._palette is not None and self._palette.is_visible():
            current = self._palette.current()
            self._palette.hide()
            try:
                self.query_one("#input", InputBar).value = ""
            except Exception:
                pass
            if current is not None:
                self._run_command(current.name)
                return
        self.action_submit_input()

    def on_key(self, event) -> None:
        if self._palette is None:
            return
        if not self._palette.is_visible():
            return
        key = getattr(event, "key", "")
        if key == "up":
            self._palette.move_up()
            event.prevent_default()
        elif key == "down":
            self._palette.move_down()
            event.prevent_default()
        elif key == "escape":
            self._palette.hide()
            try:
                self.query_one("#input", InputBar).value = ""
            except Exception:
                pass
            event.prevent_default()
        elif key == "tab":
            # Tab completes the current command name into the input
            current = self._palette.current()
            if current is not None:
                try:
                    self.query_one("#input", InputBar).value = current.name
                except Exception:
                    pass
            event.prevent_default()

    def _run_command(self, name: str) -> None:
        # dispatch by command name (alias is normalized to the canonical one)
        if name in {"/resume", "/sessions"}:
            self._show_resume()
        elif name in {"/config", "/setup", "/onboard"}:
            self._show_onboarding()
        elif name == "/clear":
            self._clear_chat()
        elif name == "/help":
            self._show_help()
        else:
            try:
                chat = self.query_one("#chat", ChatLog)
                chat.write(Text(f"unknown command: {name}\n", style="rgb(248,81,73)"))
            except Exception:
                pass

    def _clear_chat(self) -> None:
        try:
            chat = self.query_one("#chat", ChatLog)
            board = self.query_one("#board", AgentBoard)
            trace = self.query_one("#trace", ToolTrace)
            for w in list(chat.children):
                w.remove()
            for w in list(board.children):
                w.remove()
            for w in list(trace.children):
                w.remove()
            chat._rows.clear()
            chat._texts.clear()
            board._pills.clear()
            trace._rows.clear()
        except Exception:
            pass

    def _show_help(self) -> None:
        try:
            chat = self.query_one("#chat", ChatLog)
            from nextcli.tui.command_palette import COMMANDS
            t = Text()
            t.append("\nAvailable commands:\n", style="bold rgb(88,166,255)")
            for cmd in COMMANDS:
                t.append(f"  {cmd.name:<14}", style="bold rgb(88,166,255)")
                t.append(f"  {cmd.description}\n", style="white")
                if cmd.aliases:
                    t.append(f"  {' ' * 14}", style="white")
                    t.append(f"aliases: {', '.join(cmd.aliases)}\n", style="grey50")
            t.append("\nKeybindings: Ctrl-C quit, Ctrl-R reconfigure, double-click agent pill to view.\n", style="grey50")
            chat.write(t)
        except Exception:
            pass

    def on_input_changed(self, event) -> None:
        try:
            log_event("input_changed", widget_id=getattr(event.input, "id", None),
                      length=len(event.value or ""))
        except Exception:
            pass
        if self._palette is None:
            return
        value = getattr(event, "value", "") or ""
        if value.startswith("/"):
            if not self._palette.is_visible():
                self._palette.show()
            self._palette.update_filter(value)
        else:
            if self._palette.is_visible():
                self._palette.hide()

    def action_submit_input(self) -> None:
        from nextcli.tui.onboarding import OnboardingScreen
        if isinstance(self.app.screen, OnboardingScreen):
            try:
                focused = self.app.focused
                if focused is not None and hasattr(focused, "action_submit"):
                    focused.action_submit()
            except Exception:
                pass
            return
        try:
            inp = self.query_one("#input", InputBar)
            value = inp.value
        except Exception:
            return
        log_event("action_submit_input", value=value)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(self._handle_submit(value))
        else:
            self.call_later(lambda: asyncio.ensure_future(self._handle_submit(value)))

    async def _handle_submit(self, value: str) -> None:
        text = (value or "").strip()
        if not text:
            return
        if text in {":config", ":setup", ":onboard"}:
            try:
                self.query_one("#input", InputBar).value = ""
            except Exception:
                pass
            self._show_onboarding()
            return
        if text in {"/resume", ":resume", "/sessions", ":sessions"}:
            try:
                self.query_one("#input", InputBar).value = ""
            except Exception:
                pass
            self._show_resume()
            return
        if self._task_busy:
            pending = [t for t in self._run_tasks if not t.done()]
            if not pending:
                self._task_busy = False
            else:
                return
        try:
            self.query_one("#input", InputBar).value = ""
        except Exception:
            pass
        t = asyncio.create_task(self._run_task(text))
        self._run_tasks.add(t)
        t.add_done_callback(self._run_tasks.discard)

    def _show_resume(self) -> None:
        def _on_picked(choice: ResumeChoice | None) -> None:
            if choice is None:
                return
            if choice.action == "view":
                # read-only viewer over the saved events
                self.push_screen(SessionViewerScreen(choice.path))
            else:
                # resume: replay events into the chat, then continue the task
                self._resume_session(choice.path)
        self.push_screen(ResumeScreen(), _on_picked)

    def _resume_session(self, path) -> None:
        # load the saved session and replay its events into the live panes
        s = Session.load(path)
        try:
            chat = self.query_one("#chat", ChatLog)
            board = self.query_one("#board", AgentBoard)
            trace = self.query_one("#trace", ToolTrace)
        except Exception:
            return

        # banner
        chat.write(Text(
            f"\n↺ resumed session · {path.name}\n",
            style="bold rgb(255,166,87)",
        ))

        # replay historical events into the live panes immediately so the
        # user can see the prior conversation appear right after clicking
        # Resume (not only when they hit Enter on a new prompt)
        self._replay_into_panes(s)

        # remember the resumed session so the next _run_task picks it up
        self._resumed_session = s
        self._resumed_replayed = True

        # auto-pop the input bar with a continuation hint
        try:
            inp = self.query_one("#input", InputBar)
            inp.value = f"continue: {s.task[:60]}" if s.task else "continue the previous task"
            inp.focus()
        except Exception:
            pass

    def _consume_resumed_session(self) -> Session | None:
        """Return the pending resumed session and clear the buffer."""
        s = getattr(self, "_resumed_session", None)
        self._resumed_session = None
        return s

    # ---- task execution ----

    async def _run_task(self, task: str) -> None:
        chat = self.query_one("#chat", ChatLog)
        self._task_busy = True
        if self._title_bar is not None:
            self._title_bar.reset_stats()

        # if a resumed session is pending, the events were already replayed
        # at selection time — just preserve its task + events for context
        resumed = self._consume_resumed_session()
        prior_task = None
        if resumed is not None:
            prior_task = resumed.task

        self._session = Session(task=task, started=time.time())
        if resumed is not None:
            self._session.events = list(getattr(resumed, "events", []) or [])
        try:
            chat.write(Text())
            chat.write(Text("> ", style="bold rgb(88,166,255)"))
            chat.write(Text(task + "\n", style="white bold"))
            if prior_task:
                chat.write(Text(
                    f"(continuation of: {prior_task[:60]}{'…' if len(prior_task) > 60 else ''})\n",
                    style="grey50",
                ))
            chat.write(Text("(running…)\n", style="grey50"))

            provider = self._build_provider()
            if provider is None:
                chat.write(Text(
                    "no API key + no mock — opening setup…\n",
                    style="rgb(248,81,73)",
                ))
                self._show_onboarding()
                return

            registry = default_registry()
            orch = Orchestrator(provider=provider, registry=registry)
            self._orch = orch

            runner = asyncio.create_task(orch.run(task))
            try:
                while not runner.done() or not orch.bus._all.empty():
                    batch = orch.bus.try_drain_now()
                    # process in small chunks to keep UI responsive
                    for ev in batch[:64]:
                        self._dispatch(ev)
                        if self._session is not None:
                            self._session.add_event(ev)
                    if not batch:
                        await asyncio.sleep(0.03)
                    else:
                        # yield control back to the event loop for rendering
                        await asyncio.sleep(0)
                for ev in orch.bus.try_drain_now():
                    self._dispatch(ev)
                    if self._session is not None:
                        self._session.add_event(ev)
                try:
                    await asyncio.wait_for(runner, timeout=2.0)
                except asyncio.TimeoutError:
                    runner.cancel()
                    chat.write(Text("(orchestrator timed out)\n", style="rgb(248,81,73)"))
            finally:
                if not runner.done():
                    runner.cancel()
            chat.write(Text("\n", style="grey50"))
            chat.write(Text("done.", style="rgb(86,163,100)"))
        finally:
            self._task_busy = False
            if self._session is not None:
                self._session.finish()
                path = self._session.save()
                chat.write(Text(f"\nsession saved to {path}\n", style="grey50"))
                self._session = None

    def _dispatch(self, ev: AgentEvent) -> None:
        self.query_one("#board", AgentBoard).handle_event(ev)
        self.query_one("#trace", ToolTrace).handle_event(ev)
        # Main chat only shows planner text; sub-agents are viewed via detail screen.
        if ev.kind == "text" and ev.role == AgentRole.PLANNER:
            self.query_one("#chat", ChatLog).handle_event(ev)
        elif ev.kind != "text":
            self.query_one("#chat", ChatLog).handle_event(ev)
        # update token stats from usage events
        if ev.kind == "status" and ev.payload.get("state") == "usage":
            it = ev.payload.get("input_tokens", 0)
            ot = ev.payload.get("output_tokens", 0)
            if self._title_bar is not None:
                self._title_bar.record_usage(it, ot)
            if self._session is not None:
                self._session.record_usage(it, ot)
        log_event("event", kind=ev.kind, agent_id=ev.agent_id, role=ev.role.value)

    def _replay_into_panes(self, session: Session) -> None:
        """Replay a saved session's events into the live panes so the user
        sees the prior conversation reappear before the new task starts."""
        try:
            chat = self.query_one("#chat", ChatLog)
            board = self.query_one("#board", AgentBoard)
            trace = self.query_one("#trace", ToolTrace)
        except Exception:
            return
        if session.task:
            chat.write(Text("> ", style="bold rgb(88,166,255)"))
            chat.write(Text(session.task + "\n", style="white bold"))
        for ev in session.events:
            kind = ev.get("kind", "")
            role_val = ev.get("role", "system")
            try:
                role = AgentRole(role_val)
            except ValueError:
                continue
            event = AgentEvent(
                kind=kind,  # type: ignore[arg-type]
                agent_id=str(ev.get("agent_id", "")),
                role=role,
                ts=float(ev.get("ts", 0.0) or 0.0),
                payload=ev.get("payload", {}) or {},
            )
            try:
                board.handle_event(event)
                trace.handle_event(event)
            except Exception:
                pass
            if kind == "text" and role == AgentRole.PLANNER:
                chat.handle_event(event)
            elif kind != "text":
                chat.handle_event(event)

    def _build_provider(self):
        from nextcli.llm.anthropic_provider import AnthropicProvider
        from nextcli.llm.custom_provider import CustomProvider
        from nextcli.llm.openai_provider import OpenAIProvider

        if self._config.use_mock or self._config.provider == "mock":
            return MockProvider(model="mock")
        elif self._config.provider == "openai" and self._config.openai_api_key:
            return OpenAIProvider(api_key=self._config.openai_api_key, model=self._config.openai_model)
        elif self._config.provider == "anthropic" and self._config.anthropic_api_key:
            return AnthropicProvider(api_key=self._config.anthropic_api_key, model=self._config.anthropic_model)
        elif self._config.provider == "custom" and self._config.custom_base_url and self._config.custom_model:
            return CustomProvider(
                api_key=self._config.custom_api_key or "EMPTY",
                base_url=self._config.custom_base_url,
                model=self._config.custom_model,
            )
        else:
            return None

    # ---- agent detail screen ----

    def on__agent_detail_requested(self, event: _AgentDetailRequested) -> None:
        if self._orch is None:
            return
        agent = self._orch.agents.get(event.detail_agent_id)
        if agent is None:
            return
        self.push_screen(AgentDetailScreen(
            agent_id=agent.agent_id,
            role=agent.role.value,
            messages=agent.messages,
        ))

    # ---- bindings ----

    async def action_quit(self) -> None:
        if self._orch is not None:
            self._orch.request_cancel()
        self.exit()

    def action_rerun_setup(self) -> None:
        self._show_onboarding()
