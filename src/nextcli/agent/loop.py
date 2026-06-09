# Agent event loop: streams LLM responses, dispatches tool calls.
# Each agent publishes events to the shared bus for the TUI to render.

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from nextcli.agent.events import AgentEvent, AgentRole, EventBus
from nextcli.agent.prompts import prompt_for
from nextcli.llm.provider import LLMProvider, Message, ToolCallSpec
from nextcli.tools.base import ToolContext, ToolRegistry, ToolResult
from nextcli.util.log import log_event

SpawnHandler = Callable[[AgentRole, str, dict[str, Any]], str]


@dataclass
class Agent:
    role: AgentRole
    provider: LLMProvider
    registry: ToolRegistry
    bus: EventBus
    agent_id: str = field(default_factory=lambda: f"ag-{uuid.uuid4().hex[:8]}")
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    messages: list[Message] = field(default_factory=list)
    # handler for spawning child agents
    spawn_handler: SpawnHandler | None = None
    # max turns to prevent infinite loops
    max_turns: int = 8

    async def run(self, task: str) -> str:
        """Run the agent loop and return the final assistant text."""
        self._emit_status("starting")
        self.messages = [Message.system(prompt_for(self.role, task)), Message.user(task)]
        try:
            final = await self._loop()
        except asyncio.CancelledError:
            self._emit_status("cancelled")
            raise
        except Exception as exc:
            self._emit_status("error", error=str(exc))
            log_event("agent_error", agent_id=self.agent_id, role=self.role.value, error=str(exc))
            raise
        self._emit_status("done")
        return final

    async def continue_loop(self) -> str:
        """Continue the agent loop from the current message state.

        Used by the orchestrator to run the planner again after sub-agents
        finish so it can synthesize a final summary.
        """
        self._emit_status("starting")
        try:
            final = await self._loop()
        except asyncio.CancelledError:
            self._emit_status("cancelled")
            raise
        except Exception as exc:
            self._emit_status("error", error=str(exc))
            log_event("agent_error", agent_id=self.agent_id, role=self.role.value, error=str(exc))
            raise
        self._emit_status("done")
        return final

    def request_cancel(self) -> None:
        # signal cancellation to the agent loop
        self.cancel.set()

    def _emit_status(self, state: str, **extra: Any) -> None:
        # publish a status event to the bus
        self.bus.publish_nowait(AgentEvent(
            kind="status",
            agent_id=self.agent_id,
            role=self.role,
            ts=time.time(),
            payload={"state": state, **extra},
        ))

    async def _loop(self) -> str:
        # main agent loop: stream -> collect -> dispatch tools -> repeat
        last_text = ""
        for turn_idx in range(self.max_turns):
            if self.cancel.is_set():
                break
            self._emit_status("thinking")
            text_buf = ""
            tool_calls: list[ToolCallSpec] = []
            finish_reason: str | None = None
            tools = [self.provider.tool_to_schema(tool) for tool in self.registry.for_role(self.role)]
            async for delta in self.provider.stream(self.messages, tools=tools or None):
                if self.cancel.is_set():
                    break
                if delta.text:
                    text_buf += delta.text
                    self._emit_text(delta.text)
                if delta.tool_call:
                    tool_calls.append(delta.tool_call)
                if delta.finish_reason:
                    finish_reason = delta.finish_reason
                if delta.usage:
                    self.bus.publish_nowait(AgentEvent(
                        kind="status", agent_id=self.agent_id, role=self.role,
                        payload={"state": "usage", **delta.usage},
                    ))

            last_text = text_buf
            # save the assistant response to message history
            self.messages.append(Message.assistant(content=text_buf, tool_calls=tool_calls))

            if not tool_calls:
                # no more tool calls, we are done
                break

            # run each tool call one at a time
            self._emit_status("tooling", count=len(tool_calls))
            for tc in tool_calls:
                if self.cancel.is_set():
                    break
                result = await self._dispatch_tool(tc)
                # save the tool result back into the conversation
                self.messages.append(Message.tool_result(
                    tool_call_id=tc.id, name=tc.name, content=result.output or result.error or "",
                ))

        return last_text

    def _emit_text(self, delta: str) -> None:
        # publish a text delta to the bus
        self.bus.publish_nowait(AgentEvent(
            kind="text",
            agent_id=self.agent_id,
            role=self.role,
            ts=time.time(),
            payload={"delta": delta},
        ))

    async def _dispatch_tool(self, tc: ToolCallSpec) -> ToolResult:
        # find the tool and run it
        tool = self.registry.get(tc.name)
        ctx = ToolContext(
            agent_id=self.agent_id,
            role=self.role,
            emit=lambda ev: self.bus.publish_nowait(ev),
        )
        # pass the spawn handler so child agents can be created
        if self.spawn_handler is not None:
            setattr(ctx, "spawn_handler", self.spawn_handler)

        self.bus.publish_nowait(AgentEvent(
            kind="tool_call",
            agent_id=self.agent_id,
            role=self.role,
            ts=time.time(),
            payload={"id": tc.id, "name": tc.name, "arguments": tc.arguments},
        ))
        if tool is None:
            result = ToolResult(ok=False, output="", error=f"unknown tool: {tc.name}")
        else:
            try:
                result = await tool.run(tc.arguments, ctx)
            except Exception as exc:
                result = ToolResult(ok=False, output="", error=f"tool crashed: {exc}")
        self.bus.publish_nowait(AgentEvent(
            kind="tool_result",
            agent_id=self.agent_id,
            role=self.role,
            ts=time.time(),
            payload={"id": tc.id, "name": tc.name, **result.to_dict()},
        ))
        return result
