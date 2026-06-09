# Event types and the shared event bus for agent communication.
# Agents push events, TUI drains them asynchronously.

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class AgentRole(str, Enum):
    # the four roles in the multi-agent system
    PLANNER = "planner"
    EXPLORER = "explorer"
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"


EventKind = Literal["status", "text", "tool_call", "tool_result", "error", "done"]


@dataclass(slots=True)
class AgentEvent:
    # a single event emitted by an agent during execution
    kind: EventKind
    agent_id: str
    role: AgentRole
    ts: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Shared event bus with a unified queue for all agents."""

    def __init__(self) -> None:
        self._per_agent: dict[str, asyncio.Queue[AgentEvent]] = {}
        self._all: asyncio.Queue[AgentEvent] = asyncio.Queue()

    def queue_for(self, agent_id: str) -> asyncio.Queue[AgentEvent]:
        if agent_id not in self._per_agent:
            self._per_agent[agent_id] = asyncio.Queue()
        return self._per_agent[agent_id]

    def publish_nowait(self, ev: AgentEvent) -> None:
        # push event without blocking
        self._all.put_nowait(ev)
        q = self.queue_for(ev.agent_id)
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            pass

    async def publish(self, ev: AgentEvent) -> None:
        # same as publish_nowait
        self.publish_nowait(ev)

    async def drain(self) -> AsyncIterator[AgentEvent]:
        # pull events one by one, blocks when empty
        while True:
            ev = await self._all.get()
            yield ev

    def try_drain_now(self, max_items: int = 256) -> list[AgentEvent]:
        # pull available events without blocking
        out: list[AgentEvent] = []
        for _ in range(max_items):
            try:
                out.append(self._all.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out
