# Orchestrator: manages the lifecycle of planner + sub-agents.
# Planner runs first, then sub-agents are spawned dynamically.
# After all sub-agents finish, their results are injected back into the
# planner so it can write a final summary.

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from nextcli.agent.events import AgentEvent, AgentRole, EventBus
from nextcli.agent.loop import Agent
from nextcli.llm.provider import LLMProvider, Message
from nextcli.tools.base import ToolRegistry


@dataclass
class SubTask:
    role: AgentRole
    task: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    subtasks: list[SubTask]
    reasoning: str = ""


class Orchestrator:
    """Coordinates the planner and its sub-agents."""

    def __init__(self, provider: LLMProvider, registry: ToolRegistry) -> None:
        self._provider = provider
        self._registry = registry
        self.bus = EventBus()
        self._pending: dict[str, Agent] = {}
        self._tasks: list[asyncio.Task[str]] = []
        self._cancel = asyncio.Event()
        # expose all agents so the TUI can inspect message history
        self.agents: dict[str, Agent] = {}
        # track sub-agent results for the final planner summary
        self._sub_results: dict[str, str] = {}
        self._planner_agent: Agent | None = None

    async def run(self, user_task: str) -> str:
        # start the planner and wait for all tasks to finish
        planner = self._new_agent(AgentRole.PLANNER)
        self._planner_agent = planner
        planner_task = asyncio.create_task(self._run_one(planner, user_task))
        self._tasks.append(planner_task)

        while True:
            pending = [t for t in self._tasks if not t.done()]
            if not pending:
                break
            await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

        # collect sub-agent results and feed them back to the planner
        sub_summaries = []
        for agent_id, result in self._sub_results.items():
            agent = self.agents.get(agent_id)
            if agent is None or agent.role == AgentRole.PLANNER:
                continue
            sub_summaries.append(
                f"[{agent.role.value}] result:\n{result[:1500]}"
            )

        if sub_summaries and self._planner_agent is not None:
            summary_text = "\n\n".join(sub_summaries)
            self._planner_agent.messages.append(
                Message.user(
                    f"All sub-agents have finished. Here are their results:\n\n"
                    f"{summary_text}\n\n"
                    f"Please provide a final summary for the user based on these results."
                )
            )
            # run planner one more time for the final summary
            final_task = asyncio.create_task(
                self._planner_agent.continue_loop()
            )
            self._tasks.append(final_task)
            await final_task
            return final_task.result() or ""

        # get the original planner result
        planner_result = ""
        for t in self._tasks:
            if t is planner_task and not t.cancelled():
                try:
                    planner_result = t.result() or ""
                except Exception:
                    planner_result = ""
        return planner_result

    async def stream(self, user_task: str) -> AsyncIterator[AgentEvent]:
        # run the orchestrator and stream events
        runner = asyncio.create_task(self.run(user_task))
        try:
            while not (runner.done() and self.bus._all.empty()):
                batch = self.bus.try_drain_now()
                for ev in batch:
                    yield ev
                if not batch:
                    await asyncio.sleep(0.03)
            # drain remaining events
            for ev in self.bus.try_drain_now():
                yield ev
            await runner
        finally:
            if not runner.done():
                runner.cancel()

    def request_cancel(self) -> None:
        # cancel all agents and tasks
        self._cancel.set()
        for a in self._pending.values():
            a.request_cancel()
        for t in self._tasks:
            if not t.done():
                t.cancel()

    def _new_agent(self, role: AgentRole) -> Agent:
        # create a new agent and wire up the spawn handler
        a = Agent(role=role, provider=self._provider, registry=self._registry, bus=self.bus)
        a.spawn_handler = self._spawn_handler
        self._pending[a.agent_id] = a
        self.agents[a.agent_id] = a
        return a

    def _spawn_handler(self, role: AgentRole, task: str, context: dict[str, Any]) -> str:
        # called when the planner uses spawn_agent tool
        agent = self._new_agent(role)
        rich_task = task
        if context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
            rich_task = f"{task}\n\n(context: {ctx_str})"
        t = asyncio.create_task(self._run_one(agent, rich_task))
        self._tasks.append(t)
        # let the TUI know a new agent started
        agent.bus.publish_nowait(AgentEvent(
            kind="status",
            agent_id=agent.agent_id,
            role=role,
            ts=time.time(),
            payload={"state": "starting", "parent": True},
        ))
        return agent.agent_id

    async def _run_one(self, agent: Agent, task: str) -> str:
        # run a single agent and handle errors
        try:
            result = await agent.run(task)
            self._sub_results[agent.agent_id] = result
            return result
        except asyncio.CancelledError:
            return ""
        except Exception as exc:
            self._sub_results[agent.agent_id] = ""
            agent.bus.publish_nowait(AgentEvent(
                kind="error",
                agent_id=agent.agent_id,
                role=agent.role,
                ts=time.time(),
                payload={"error": str(exc)},
            ))
            return ""
