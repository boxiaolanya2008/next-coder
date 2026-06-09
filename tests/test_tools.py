"""Tests for the tool implementations."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from nextcli.agent.events import AgentRole
from nextcli.tools import default_registry
from nextcli.tools.base import ToolContext, ToolResult


def _ctx() -> ToolContext:
    return ToolContext(agent_id="test", role=AgentRole.IMPLEMENTER, emit=lambda _ev: None)


@pytest.mark.asyncio
async def test_read_file_returns_numbered_lines(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    reg = default_registry()
    res = await reg.get("read_file").run({"path": "a.txt", "limit": 10}, _ctx())
    assert res.ok
    assert "1\talpha" in res.output
    assert "2\tbeta" in res.output
    assert "3\tgamma" in res.output


@pytest.mark.asyncio
async def test_read_file_missing(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    reg = default_registry()
    res = await reg.get("read_file").run({"path": "nope.txt"}, _ctx())
    assert not res.ok
    assert "not found" in (res.error or "")


@pytest.mark.asyncio
async def test_edit_file_unique_replacement(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    p = tmp_path / "a.py"
    p.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    reg = default_registry()
    res = await reg.get("edit_file").run(
        {"path": "a.py", "old": "y = 2", "new": "y = 99", "replace_all": False}, _ctx()
    )
    assert res.ok
    assert p.read_text(encoding="utf-8") == "x = 1\ny = 99\nz = 3\n"


@pytest.mark.asyncio
async def test_edit_file_ambiguous_rejected(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    p = tmp_path / "a.py"
    p.write_text("x = 1\ny = 2\nx = 1\n", encoding="utf-8")
    reg = default_registry()
    res = await reg.get("edit_file").run(
        {"path": "a.py", "old": "x = 1", "new": "x = 99"}, _ctx()
    )
    assert not res.ok
    assert "ambiguous" in (res.error or "")


@pytest.mark.asyncio
async def test_edit_file_replace_all(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    p = tmp_path / "a.py"
    p.write_text("x = 1\ny = 2\nx = 1\n", encoding="utf-8")
    reg = default_registry()
    res = await reg.get("edit_file").run(
        {"path": "a.py", "old": "x = 1", "new": "x = 99", "replace_all": True}, _ctx()
    )
    assert res.ok
    assert p.read_text(encoding="utf-8") == "x = 99\ny = 2\nx = 99\n"


@pytest.mark.asyncio
async def test_shell_runs_command(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    reg = default_registry()
    res = await reg.get("run_shell").run({"cmd": "python -c \"print('hi')\"", "timeout": 10}, _ctx())
    assert res.ok
    assert "hi" in res.output


@pytest.mark.asyncio
async def test_shell_timeout(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    reg = default_registry()
    res = await reg.get("run_shell").run(
        {"cmd": "python -c \"import time; time.sleep(2)\"", "timeout": 1}, _ctx()
    )
    assert not res.ok
    assert "timeout" in (res.error or "")


@pytest.mark.asyncio
async def test_glob_finds_python_files(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("")
    reg = default_registry()
    res = await reg.get("glob_files").run({"pattern": "**/*.py", "root": "."}, _ctx())
    assert res.ok
    assert "a.py" in res.output
    assert "sub/c.py" in res.output
    assert "b.txt" not in res.output


@pytest.mark.asyncio
async def test_grep_finds_pattern(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    (tmp_path / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    reg = default_registry()
    res = await reg.get("grep").run({"pattern": "hello", "path": "."}, _ctx())
    assert res.ok
    assert "hello" in res.output


@pytest.mark.asyncio
async def test_role_allowlist_blocks_write_for_explorer() -> None:
    reg = default_registry()
    explorer_tools = {t.name for t in reg.for_role(AgentRole.EXPLORER)}
    assert "write_file" not in explorer_tools
    assert "edit_file" not in explorer_tools
    assert "read_file" in explorer_tools

    reviewer_tools = {t.name for t in reg.for_role(AgentRole.REVIEWER)}
    assert "write_file" not in reviewer_tools
    assert "edit_file" not in reviewer_tools
    assert "run_shell" in reviewer_tools

    impl_tools = {t.name for t in reg.for_role(AgentRole.IMPLEMENTER)}
    assert "write_file" in impl_tools
    assert "edit_file" in impl_tools
    assert "read_file" in impl_tools
