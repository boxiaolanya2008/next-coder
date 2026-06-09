# read_file tool: reads a file and returns line-numbered content.
# cached in memory so multiple agents reading the same file are fast.

from __future__ import annotations

from pathlib import Path

from nextcli.tools.base import ToolContext, ToolResult
from nextcli.tools.tool_cache import tcache_get, tcache_set
from nextcli.util.paths import resolve_under_root


class ReadFile:
    name = "read_file"
    description = "Read a UTF-8 text file. Returns line-numbered content."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to project root."},
            "limit": {"type": "integer", "description": "Max lines to return (default 2000)."},
        },
        "required": ["path"],
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        # resolve the path and read the file
        path_arg = args.get("path", "")
        limit = int(args.get("limit", 2000))
        # check the in-memory cache first
        cache_key = f"read:{path_arg}:{limit}"
        cached = tcache_get(cache_key)
        if cached is not None:
            return ToolResult(ok=True, output=cached)
        try:
            p = resolve_under_root(path_arg)
        except (PermissionError, ValueError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        if not p.exists():
            return ToolResult(ok=False, output="", error=f"file not found: {p}")
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=f"read error: {exc}")
        # add line numbers
        lines = text.splitlines()
        numbered = "\n".join(f"{i+1:4d}\t{line}" for i, line in enumerate(lines[:limit]))
        if len(lines) > limit:
            numbered += f"\n... ({len(lines) - limit} more lines)"
        # save to cache
        tcache_set(cache_key, numbered)
        return ToolResult(ok=True, output=numbered)
