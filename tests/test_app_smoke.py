"""Smoke test for the Textual TUI: launch in headless mode, simulate input,
verify that the AgentBoard grew."""

from __future__ import annotations

import os
import asyncio
from pathlib import Path

import pytest

from nextcli.config import Config, UserConfig
from nextcli.tui.app import NextCliApp


@pytest.mark.asyncio
async def test_app_starts_and_accepts_input(tmp_path: Path, monkeypatch) -> None:
    os.chdir(tmp_path)
    # Pretend the user already onboarded (so the wizard is skipped).
    fake_cfg = tmp_path / "config.json"
    monkeypatch.setattr("nextcli.config.user_config_path", lambda: fake_cfg)
    UserConfig(provider="mock", onboarded=True).save()

    fixtures = tmp_path / "tests" / "fixtures" / "sample_repo"
    fixtures.mkdir(parents=True)
    # The canned script's edit_file targets an old-style `class Point:`
    # with two-arg __init__. Use that exact form so the implementer can match.
    (fixtures / "example.py").write_text(
        "class Point:\n    def __init__(self, x, y):\n        self.x = x\n        self.y = y\n"
    )

    config = Config(
        provider="mock",
        anthropic_api_key=None,
        openai_api_key=None,
        custom_api_key=None,
        custom_base_url=None,
        anthropic_model="claude-sonnet-4-5",
        openai_model="gpt-4o",
        custom_model="",
        use_mock=True,
        cache_dir=tmp_path / "cache",
    )

    app = NextCliApp(config=config)
    async with app.run_test() as pilot:
        # Simulate a user task by calling _run_task directly (bypasses
        # the Input widget, which is harder to focus in run_test).
        from nextcli.tui.panes import AgentBoard

        task = "Refactor example.py to dataclasses and add tests"
        # Start the task in the background and yield
        task_coro = app._run_task(task)
        runner = asyncio.create_task(task_coro)
        await pilot.pause(0.5)
        board = app.query_one("#board", AgentBoard)
        await pilot.pause(3.0)
        n_pills = len(board._pills)
        assert n_pills >= 1, f"expected at least 1 agent pill, got {n_pills}"
        # Wait for the full demo to finish
        try:
            await asyncio.wait_for(runner, timeout=15)
        except asyncio.TimeoutError:
            runner.cancel()
        # In the end, the file should have been refactored
        refactored = (fixtures / "example.py").read_text(encoding="utf-8")
        assert "@dataclass" in refactored, f"expected @dataclass in {refactored!r}"
