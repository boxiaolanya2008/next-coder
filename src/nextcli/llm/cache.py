# Response cache for LLM provider calls.
# Two-tier: in-memory LRU + disk file with TTL.

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from nextcli.llm.provider import Delta, LLMProvider, Message, ToolCallSpec


class ResponseCache:
    """Cache for LLM responses. Memory + disk with configurable TTL."""

    def __init__(self, cache_dir, ttl=3600, max_mem=256):
        self._dir = cache_dir / "llm_cache"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl
        self._max_mem = max_mem
        self._mem = {}
        self._order = []
        self.hits = 0
        self.misses = 0

    def _normalize(self, messages, tools):
        # flatten messages into a hashable form
        msg_list = []
        for m in messages:
            tc_list = []
            for tc in (m.tool_calls or []):
                tc_list.append((tc.id, tc.name, tc.arguments))
            msg_list.append((m.role, m.content, m.tool_call_id, m.name, tc_list))
        return {"messages": msg_list, "tools": tools or []}

    def _key(self, model, messages, tools):
        data = {"model": model, "norm": self._normalize(messages, tools)}
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _to_dicts(self, deltas):
        out = []
        for d in deltas:
            entry = {"text": d.text, "finish_reason": d.finish_reason, "usage": d.usage}
            if d.tool_call:
                entry["tool_call"] = {
                    "id": d.tool_call.id,
                    "name": d.tool_call.name,
                    "arguments": d.tool_call.arguments,
                }
            else:
                entry["tool_call"] = None
            out.append(entry)
        return out

    def _from_dicts(self, data):
        out = []
        for entry in data:
            tc = entry.get("tool_call")
            out.append(Delta(
                text=entry.get("text"),
                tool_call=ToolCallSpec(**tc) if tc else None,
                finish_reason=entry.get("finish_reason"),
                usage=entry.get("usage"),
            ))
        return out

    def lookup(self, model, messages, tools):
        key = self._key(model, messages, tools)
        # fast memory check
        if key in self._mem:
            self.hits += 1
            self._touch(key)
            return self._from_dicts(self._mem[key])
        # disk check
        path = self._dir / f"{key}.json"
        if path.exists():
            try:
                age = time.time() - path.stat().st_mtime
                if age < self._ttl:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    self._add_mem(key, raw)
                    self.hits += 1
                    return self._from_dicts(raw)
                else:
                    path.unlink(missing_ok=True)
            except (OSError, json.JSONDecodeError):
                pass
        self.misses += 1
        return None

    def store(self, model, messages, tools, deltas):
        key = self._key(model, messages, tools)
        serialized = self._to_dicts(deltas)
        self._add_mem(key, serialized)
        path = self._dir / f"{key}.json"
        try:
            path.write_text(json.dumps(serialized), encoding="utf-8")
        except OSError:
            pass

    def _add_mem(self, key, data):
        self._mem[key] = data
        self._order.append(key)
        if len(self._order) > self._max_mem:
            old = self._order.pop(0)
            self._mem.pop(old, None)

    def _touch(self, key):
        if key in self._order:
            self._order.remove(key)
            self._order.append(key)

    def clear_expired(self):
        # remove expired cache files from disk
        now = time.time()
        removed = 0
        for path in self._dir.glob("*.json"):
            try:
                if now - path.stat().st_mtime > self._ttl:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    @property
    def hit_rate(self):
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class CachedProvider:
    """Wraps any LLMProvider with transparent response caching."""

    name: str
    model: str

    def __init__(self, inner, cache):
        self._inner = inner
        self._cache = cache
        self.name = inner.name
        self.model = inner.model

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Delta]:
        # check cache first
        cached = self._cache.lookup(self.model, messages, tools)
        if cached is not None:
            for d in cached:
                yield d
            return
        # collect from real provider
        collected = []
        async for d in self._inner.stream(messages, tools):
            collected.append(d)
            yield d
        # save to cache
        self._cache.store(self.model, messages, tools, collected)

    def tool_to_schema(self, tool):
        return self._inner.tool_to_schema(tool)
