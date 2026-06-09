# Anthropic provider: adapts the official SDK to our LLMProvider protocol.
# Lazy import so the package works without anthropic installed.

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from nextcli.llm.provider import Delta, Message, ToolCallSpec


class AnthropicProvider:
    # provider name and model id
    name = "anthropic"
    model: str

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5") -> None:
        # make sure we have a key
        if not api_key:
            raise ValueError("AnthropicProvider requires a non-empty api_key")
        self.model = model
        self._api_key = api_key
        self._client: Any = None  # lazy init

    def _get_client(self) -> Any:
        # create the client if not already done
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic SDK not installed. `pip install anthropic>=0.39`"
                ) from exc
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    def tool_to_schema(self, tool: Any) -> dict[str, Any]:
        # convert a tool to the format anthropic expects
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Delta]:
        # convert our messages to anthropic format and stream
        client = self._get_client()
        system_text = ""
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            elif m.role == "user":
                api_messages.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                api_messages.append({"role": "assistant", "content": blocks or m.content})
            elif m.role == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "",
                        "content": m.content,
                    }],
                })

        # build the request params
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": api_messages,
        }
        if system_text:
            kwargs["system"] = system_text.strip()
        if tools:
            kwargs["tools"] = tools

        # buffers for collecting tool call data from stream chunks
        tool_input_buf: dict[int, str] = {}
        tool_meta: dict[int, tuple[str, str]] = {}

        # stream the response and yield deltas
        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                et = getattr(event, "type", "")
                if et == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if block is not None and getattr(block, "type", "") == "tool_use":
                        idx = getattr(event, "index", 0)
                        tool_meta[idx] = (block.id, block.name)
                        tool_input_buf[idx] = ""
                elif et == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta is None:
                        continue
                    dtype = getattr(delta, "type", "")
                    if dtype == "text_delta":
                        text = getattr(delta, "text", "")
                        if text:
                            yield Delta(text=text)
                    elif dtype == "input_json_delta":
                        idx = getattr(event, "index", 0)
                        tool_input_buf[idx] = (tool_input_buf.get(idx, "") + getattr(delta, "partial_json", ""))
                elif et == "content_block_stop":
                    # tool call finished, emit it
                    idx = getattr(event, "index", 0)
                    if idx in tool_meta and idx in tool_input_buf:
                        tid, tname = tool_meta[idx]
                        raw = tool_input_buf[idx]
                        try:
                            args = json.loads(raw) if raw else {}
                        except json.JSONDecodeError:
                            args = {"_raw": raw}
                        yield Delta(tool_call=ToolCallSpec(id=tid, name=tname, arguments=args))
                        tool_input_buf.pop(idx, None)
                        tool_meta.pop(idx, None)
                elif et == "message_delta":
                    mr = getattr(event, "delta", None)
                    if mr is not None and getattr(mr, "stop_reason", None):
                        yield Delta(finish_reason=str(mr.stop_reason))
                elif et == "message_stop":
                    # final usage info
                    msg = getattr(stream, "current_message_snapshot", None)
                    if msg is not None and getattr(msg, "usage", None):
                        u = msg.usage
                        yield Delta(usage={
                            "input_tokens": getattr(u, "input_tokens", 0),
                            "output_tokens": getattr(u, "output_tokens", 0),
                        })
                    return
