"""LLM provider protocol and shared data types.

The provider layer is the contract every higher-level component talks to.
`Agent.run()` consumes `AsyncIterator[Delta]`. Providers translate vendor
specifics (Anthropic Messages / OpenAI Chat Completions) into the same shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class ToolCallSpec:
    """A tool invocation decided by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class Message:
    """One entry in the conversation log."""

    role: Role
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: list[ToolCallSpec] = field(default_factory=list)
    name: str | None = None  # for role="tool", the tool's name

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: list[ToolCallSpec] | None = None) -> "Message":
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool_result(cls, tool_call_id: str, name: str, content: str) -> "Message":
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)


@dataclass(slots=True)
class Delta:
    """A streaming chunk from the provider.

    `text` is a string fragment; `tool_call` is the FULL spec once arguments
    have finished streaming (we coalesce partial args internally); the last
    delta in a turn carries `finish_reason`; `usage` is best-effort token
    accounting from the provider.
    """

    text: str | None = None
    tool_call: ToolCallSpec | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """The single contract every LLM backend must satisfy."""

    name: str
    model: str

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Delta]:
        """Yield streaming deltas for one model turn."""
        ...

    def tool_to_schema(self, tool: Any) -> dict[str, Any]:
        """Translate a Tool object into the provider's tool-call schema."""
        ...
