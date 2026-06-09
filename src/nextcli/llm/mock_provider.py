# Mock provider for tests and offline demos.
# Reads canned scripts and streams them as Deltas. No network needed.

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nextcli.llm.provider import Delta, Message, ToolCallSpec
from nextcli.util.paths import project_root

# types for the canned script format
TextChunk = str
ToolChunk = tuple[str, str, str, dict[str, Any]]  # ("tool_call", id, name, args)
DoneChunk = tuple[str, str]                       # ("done", finish_reason)
Turn = list[TextChunk | ToolChunk | DoneChunk]
Script = dict[str, list[Turn]]                    # role.value -> list[Turn]


@dataclass
class MockProvider:
    """Canned-response provider keyed by AgentRole value."""

    name: str = "mock"
    model: str = "mock-model"
    script: Script = field(default_factory=dict)
    # delay between chunks to simulate real network latency
    chunk_delay: float = 0.05
    # path to find the canned response file
    default_script_path: str = "tests/fixtures/canned_llm_responses.py"

    def __post_init__(self) -> None:
        # load the default script if none was given
        if not self.script:
            self.script = self._load_default_script()

    def _load_default_script(self) -> Script:
        # try to find the canned responses file in the project
        import importlib.util

        here = Path(__file__).resolve()
        candidates = [
            here.parents[3] / "tests" / "fixtures" / "canned_llm_responses.py",
            project_root() / "tests" / "fixtures" / "canned_llm_responses.py",
            project_root() / self.default_script_path,
        ]
        for path in candidates:
            if not path.exists():
                continue
            spec = importlib.util.spec_from_file_location("canned_llm_responses", path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
            except Exception:
                continue
            return getattr(mod, "SCRIPT", _FALLBACK_SCRIPT)
        return _FALLBACK_SCRIPT

    def get_script_for(self, role_value: str) -> list[Turn]:
        # look up the script for a given role
        return self.script.get(role_value, [])

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Delta]:
        # find which role this is from the system prompt marker
        role_value = self._infer_role(messages)
        script = self.get_script_for(role_value)
        turn_index = self._consume_turn_counter(messages, role_value)
        if not script or turn_index >= len(script):
            yield Delta(text=f"(mock: no more scripted turns for role={role_value})", finish_reason="end_turn")
            return

        # play back the canned chunks for this turn
        turn = script[turn_index]
        for chunk in turn:
            if self.chunk_delay:
                await asyncio.sleep(self.chunk_delay)
            if isinstance(chunk, str):
                yield Delta(text=chunk)
            elif chunk[0] == "tool_call":
                _, tid, tname, targs = chunk
                yield Delta(tool_call=ToolCallSpec(id=tid, name=tname, arguments=targs))
            elif chunk[0] == "done":
                _, reason = chunk
                yield Delta(finish_reason=reason)
            else:
                # unknown chunk, just emit as text
                yield Delta(text=json.dumps(chunk))

    def tool_to_schema(self, tool: Any) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    @staticmethod
    def _infer_role(messages: list[Message]) -> str:
        # find the role marker in the most recent system message
        for m in reversed(messages):
            if m.role == "system" and m.content.startswith("[role:"):
                return m.content.split("]")[0].split(":")[1].strip()
        return "default"

    @staticmethod
    def _consume_turn_counter(messages: list[Message], role_value: str) -> int:
        # count how many assistant turns this role already produced
        n = 0
        in_role = False
        for m in messages:
            if m.role == "system" and m.content.startswith(f"[role:{role_value}]"):
                in_role = True
                continue
            if m.role == "system" and m.content.startswith("[role:") and in_role:
                # a different role starts, stop counting this one
                in_role = False
            if in_role and m.role == "assistant":
                n += 1
        return n


# fallback script if no fixture file exists
_FALLBACK_SCRIPT: Script = {
    "planner": [
        [
            "I'll decompose this task into subtasks.\n",
            ("tool_call", "t1", "spawn_agent", {"role": "explorer", "task": "Survey the repo"}),
            ("tool_call", "t2", "spawn_agent", {"role": "implementer", "task": "Apply the refactor"}),
            ("tool_call", "t3", "spawn_agent", {"role": "reviewer", "task": "Run tests"}),
            ("done", "tool_use"),
        ]
    ],
    "explorer": [
        ["Survey complete: 3 Python files found.\n", ("done", "end_turn")],
    ],
    "implementer": [
        ["Refactor applied.\n", ("done", "end_turn")],
    ],
    "reviewer": [
        ["Tests pass: 3/3.\n", ("done", "end_turn")],
    ],
}
