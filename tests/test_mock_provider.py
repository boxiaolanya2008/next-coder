"""Mock provider end-to-end test: an agent driven by canned responses produces
the expected sequence of AgentEvents on the bus."""

from __future__ import annotations

import asyncio

import pytest

from nextcli.agent.events import AgentEvent, AgentRole, EventBus
from nextcli.agent.loop import Agent
from nextcli.llm.mock_provider import MockProvider
from nextcli.tools import default_registry


@pytest.mark.asyncio
async def test_mock_provider_streams_text_and_done() -> None:
    provider = MockProvider(chunk_delay=0)
    saw_text = False
    saw_done = False
    async for delta in provider.stream([]):
        if delta.text:
            saw_text = True
        if delta.finish_reason:
            saw_done = True
    assert saw_text and saw_done


@pytest.mark.asyncio
async def test_planner_agent_emits_spawn_agent_tool_calls() -> None:
    bus = EventBus()
    provider = MockProvider(chunk_delay=0)
    reg = default_registry()
    agent = Agent(role=AgentRole.PLANNER, provider=provider, registry=reg, bus=bus)
    final = await agent.run("Refactor example.py to dataclasses")
    assert "Plan" in final or "plan" in final.lower() or len(final) > 0
    # Inspect the bus: should have a tool_call for spawn_agent
    events = bus.try_drain_now(max_items=1000)
    tool_calls = [e for e in events if e.kind == "tool_call"]
    assert any(e.payload.get("name") == "spawn_agent" for e in tool_calls), \
        f"expected spawn_agent call, got {[e.payload for e in tool_calls]}"


@pytest.mark.asyncio
async def test_tool_call_event_contains_arguments() -> None:
    bus = EventBus()
    provider = MockProvider(chunk_delay=0)
    reg = default_registry()
    agent = Agent(role=AgentRole.EXPLORER, provider=provider, registry=reg, bus=bus)
    await agent.run("Survey the repo")
    events = bus.try_drain_now(max_items=1000)
    glob_calls = [
        e for e in events
        if e.kind == "tool_call" and e.payload.get("name") == "glob_files"
    ]
    assert glob_calls, f"expected a glob_files call from EXPLORER, got {[e.payload.get('name') for e in events if e.kind == 'tool_call']}"
    assert glob_calls[0].payload.get("arguments", {}).get("pattern", "").endswith(".py")
