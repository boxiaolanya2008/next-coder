# Tool protocol, registry, and per-role filtering.
# Each agent role gets access to a specific set of tools.

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from nextcli.agent.events import AgentEvent, AgentRole


@dataclass(slots=True)
class ToolResult:
    ok: bool
    output: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok, "output": self.output}
        if self.error:
            d["error"] = self.error
        return d


EmitFn = Callable[[AgentEvent], None]


@dataclass
class ToolContext:
    agent_id: str
    role: AgentRole
    emit: EmitFn


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]

    def run(self, args: dict[str, Any], ctx: ToolContext) -> Awaitable[ToolResult]: ...


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)
    # role -> allowed tool names. None means all tools.
    role_allowlist: dict[AgentRole, set[str]] = field(default_factory=dict)

    def register(self, tool: Tool, *, roles: list[AgentRole] | None = None) -> None:
        self.tools[tool.name] = tool
        if roles is not None:
            for r in roles:
                self.role_allowlist.setdefault(r, set()).add(tool.name)

    def for_role(self, role: AgentRole) -> list[Tool]:
        # get tools allowed for a given role
        allowed = self.role_allowlist.get(role)
        if allowed is None:
            return list(self.tools.values())
        return [t for n, t in self.tools.items() if n in allowed]

    def get(self, name: str) -> Tool | None:
        # look up a tool by name
        return self.tools.get(name)

    def schemas_for_role(self, role: AgentRole) -> list[dict[str, Any]]:
        # get tool schemas for the LLM to use
        out: list[dict[str, Any]] = []
        for t in self.for_role(role):
            out.append({
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            })
        return out


def default_registry() -> ToolRegistry:
    # Register all 7 tools with per-role access control.
    from nextcli.tools.edit import EditFile
    from nextcli.tools.glob import GlobFiles
    from nextcli.tools.grep import Grep
    from nextcli.tools.read import ReadFile
    from nextcli.tools.shell import RunShell
    from nextcli.tools.spawn_agent import SpawnAgent
    from nextcli.tools.write import WriteFile

    reg = ToolRegistry()
    planner_only = [AgentRole.PLANNER]
    explorer_only = [AgentRole.EXPLORER]
    impl_only = [AgentRole.IMPLEMENTER]
    reviewer_only = [AgentRole.REVIEWER]
    explorer_and_impl = [AgentRole.EXPLORER, AgentRole.IMPLEMENTER, AgentRole.REVIEWER]
    impl_and_reviewer = [AgentRole.IMPLEMENTER, AgentRole.REVIEWER]
    all_roles = [AgentRole.PLANNER, AgentRole.EXPLORER, AgentRole.IMPLEMENTER, AgentRole.REVIEWER]

    reg.register(ReadFile(), roles=all_roles)
    reg.register(WriteFile(), roles=impl_only)
    reg.register(EditFile(), roles=impl_only)
    reg.register(RunShell(), roles=impl_and_reviewer)
    reg.register(GlobFiles(), roles=explorer_only + impl_only + reviewer_only)
    reg.register(Grep(), roles=explorer_only + impl_only + reviewer_only)
    reg.register(SpawnAgent(), roles=planner_only)
    return reg
