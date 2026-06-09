"""spawn_agent tool: when the Planner calls spawn_agent, the child agent
actually runs and its events flow into the same bus."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nextcli.agent.events import AgentRole
from nextcli.llm.mock_provider import MockProvider
from nextcli.orchestrator.runner import Orchestrator
from nextcli.tools import default_registry


@pytest.mark.asyncio
async def test_planner_spawns_explorer_and_explorer_runs_to_completion(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    fixtures = tmp_path / "tests" / "fixtures" / "sample_repo"
    fixtures.mkdir(parents=True)
    (fixtures / "example.py").write_text("# stub\n")

    provider = MockProvider(chunk_delay=0)
    reg = default_registry()
    orch = Orchestrator(provider=provider, registry=reg)

    await orch.run("Survey the repo")

    events = orch.bus.try_drain_now(max_items=5000)
    explorer_done = [e for e in events if e.role == AgentRole.EXPLORER and e.kind == "status" and e.payload.get("state") == "done"]
    assert explorer_done, f"explorer never reached done; got events: {[(e.role, e.kind, e.payload) for e in events if e.role == AgentRole.EXPLORER]}"
    # And the explorer's tool calls should appear
    explorer_tool_calls = [e for e in events if e.role == AgentRole.EXPLORER and e.kind == "tool_call"]
    assert any(e.payload.get("name") in {"glob_files", "read_file"} for e in explorer_tool_calls)
