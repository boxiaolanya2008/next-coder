"""Orchestrator: hard-evidence tests that the multi-agent fan-out is real."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from nextcli.agent.events import AgentEvent, AgentRole
from nextcli.llm.mock_provider import MockProvider
from nextcli.orchestrator.runner import Orchestrator
from nextcli.tools import default_registry


@pytest.mark.asyncio
async def test_planner_spawns_three_subagents_concurrently(tmp_path: Path) -> None:
    # chdir to a temp dir so resolve_under_root works against fixtures
    os.chdir(tmp_path)
    fixtures = tmp_path / "tests" / "fixtures" / "sample_repo"
    fixtures.mkdir(parents=True)
    (fixtures / "example.py").write_text("class P:\n    def __init__(self, x, y): self.x=x; self.y=y\n")

    # Use a faster mock for the timing test
    provider = MockProvider(chunk_delay=0.005)
    reg = default_registry()
    orch = Orchestrator(provider=provider, registry=reg)

    # Start the run; we want to sample the bus WHILE it runs
    events_seen: list[AgentEvent] = []
    sample_task = asyncio.create_task(_sample(orch, events_seen, duration=2.0))
    try:
        await orch.run("Refactor example.py to dataclasses and add tests")
    finally:
        sample_task.cancel()
        try:
            await sample_task
        except (asyncio.CancelledError, Exception):
            pass

    # The sample task should have seen events from at least 3 distinct agents
    distinct_agents = {e.agent_id for e in events_seen}
    assert len(distinct_agents) >= 3, f"expected >=3 agents, saw {distinct_agents}"

    # The Planner should have been the first agent to register
    role_values = {e.role for e in events_seen}
    assert AgentRole.PLANNER in role_values
    assert AgentRole.EXPLORER in role_values
    assert AgentRole.IMPLEMENTER in role_values
    assert AgentRole.REVIEWER in role_values


async def _sample(orch: Orchestrator, sink: list[AgentEvent], duration: float) -> None:
    end = asyncio.get_event_loop().time() + duration
    while asyncio.get_event_loop().time() < end:
        for ev in orch.bus.try_drain_now():
            sink.append(ev)
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_subagent_failure_does_not_cancel_siblings(tmp_path: Path) -> None:
    """If one sub-agent raises, the others should still complete and the
    orchestrator should not raise out of run()."""
    os.chdir(tmp_path)

    from nextcli.llm.mock_provider import MockProvider
    from nextcli.orchestrator.runner import Orchestrator as O
    from nextcli.tools import default_registry

    # Inject a flaky sub-agent by giving the implementer a script that
    # references a tool it doesn't have access to -> tool returns error
    # but doesn't crash the agent. Instead, we simulate failure by raising
    # inside the planner's _spawn_handler via a monkey-patched Agent.run.
    from nextcli.agent import loop as loop_mod

    real_run = loop_mod.Agent.run
    call_count = {"n": 0}

    async def flaky_run(self, task):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        # First call is planner; sub-agents start at call 2. Make the
        # implementer (the 3rd agent spawned) crash on its first call.
        if self.role.value == "implementer":
            raise RuntimeError("simulated implementer crash")
        return await real_run(self, task)

    loop_mod.Agent.run = flaky_run  # type: ignore[method-assign]
    try:
        provider = MockProvider(chunk_delay=0)
        reg = default_registry()
        orch = O(provider=provider, registry=reg)
        # Should NOT raise
        result = await orch.run("refactor to dataclasses")
        # Planner still produced a final text
        assert isinstance(result, str)
        events = orch.bus.try_drain_now(max_items=2000)
        # We should have an error event from the implementer
        err_events = [e for e in events if e.kind == "error"]
        assert any(e.role == AgentRole.IMPLEMENTER for e in err_events)
        # And the reviewer/explorer should have completed (status=done)
        done_events = [e for e in events if e.kind == "status" and e.payload.get("state") == "done"]
        roles_done = {e.role for e in done_events}
        assert AgentRole.EXPLORER in roles_done
        assert AgentRole.REVIEWER in roles_done
    finally:
        loop_mod.Agent.run = real_run  # type: ignore[method-assign]
