# OpenAI provider: adapts the official SDK to our LLMProvider protocol.
# Lazy import so tests work without openai installed.

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from nextcli.llm.provider import Delta, Message, ToolCallSpec


class OpenAIProvider:
    name = "openai"
    model: str

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        # need a key to talk to openai
        if not api_key:
            raise ValueError("OpenAIProvider requires a non-empty api_key")
        self.model = model
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        # create the client on first use
        if self._client is None:
            try:
                from openai import AsyncOpenAI  # type: ignore
            except ImportError as exc:
                raise RuntimeError("openai SDK not installed. `pip install openai>=1.40`") from exc
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    def tool_to_schema(self, tool: Any) -> dict[str, Any]:
        # convert tool to openai function format
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Delta]:
        # convert our message format to openai chat format
        client = self._get_client()
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                api_messages.append({"role": "system", "content": m.content})
            elif m.role == "user":
                api_messages.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                msg: dict[str, Any] = {"role": "assistant"}
                if m.content:
                    msg["content"] = m.content
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in m.tool_calls
                    ]
                api_messages.append(msg)
            elif m.role == "tool":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or "",
                    "content": m.content,
                })

        # build request params
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        # buffer for collecting tool call fragments across chunks
        accum: dict[int, dict[str, str]] = {}

        # stream the response and yield chunks
        async for chunk in await client.chat.completions.create(**kwargs):
            if not chunk.choices:
                continue
            ch = chunk.choices[0]
            d = ch.delta
            if getattr(d, "content", None):
                yield Delta(text=d.content)
            tcs = getattr(d, "tool_calls", None) or []
            for tc in tcs:
                idx = getattr(tc, "index", 0) or 0
                slot = accum.setdefault(idx, {"id": "", "name": "", "args": ""})
                if getattr(tc, "id", None):
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        slot["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        slot["args"] += fn.arguments
            if getattr(ch, "finish_reason", None):
                # flush accumulated tool calls
                for idx, slot in accum.items():
                    if slot["name"]:
                        try:
                            args = json.loads(slot["args"]) if slot["args"] else {}
                        except json.JSONDecodeError:
                            args = {"_raw": slot["args"]}
                        yield Delta(tool_call=ToolCallSpec(
                            id=slot["id"] or f"tc-{idx}",
                            name=slot["name"],
                            arguments=args,
                        ))
                accum.clear()
                yield Delta(finish_reason=str(ch.finish_reason))
