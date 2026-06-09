# spawn_agent tool: the meta-tool that creates sub-agents.
# The orchestrator handles the actual scheduling.

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from nextcli.agent.events import AgentEvent, AgentRole
from nextcli.tools.base import ToolContext, ToolResult

if TYPE_CHECKING:
    from nextcli.orchestrator.runner import Orchestrator


class SpawnAgent:
    name = "spawn_agent"
    description = (
        "Spawn a sub-agent in parallel. role in "
        "{explorer, implementer, reviewer, planner}. Returns the spawned "
        "agent's id immediately; the orchestrator will inject the result "
        "into this conversation when the sub-agent finishes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": [r.value for r in AgentRole],
            },
            "task": {"type": "string"},
            "context": {"type": "object", "default": {}},
        },
        "required": ["role", "task"],
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        # validate and delegate to the orchestrator's spawn handler
        role_str = args.get("role", "")
        task = args.get("task", "")
        context = args.get("context") or {}
        try:
            role = AgentRole(role_str)
        except ValueError:
            return ToolResult(ok=False, output="", error=f"unknown role: {role_str}")
        if not task:
            return ToolResult(ok=False, output="", error="`task` must be non-empty")

        # use the spawn handler stashed on the context by the orchestrator
        handler = getattr(ctx, "spawn_handler", None)
        if handler is None:
            return ToolResult(ok=False, output="", error="spawn_agent not bound to an orchestrator")
        new_id = handler(role, task, context)
        return ToolResult(ok=True, output=f"spawned agent {new_id} (role={role.value})")
