# grep tool: search for patterns in files using regex.
# cached in memory so repeated searches are fast.

from __future__ import annotations

import re
from pathlib import Path

from nextcli.tools.base import ToolContext, ToolResult
from nextcli.tools.tool_cache import tcache_get, tcache_set
from nextcli.util.paths import resolve_under_root


class Grep:
    name = "grep"
    description = "Search for a regex/literal pattern in files under `path`. Returns `path:lineno: line`."
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "default": "."},
            "regex": {"type": "boolean", "default": True},
            "max_results": {"type": "integer", "default": 200},
        },
        "required": ["pattern"],
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        # search files for matching pattern
        pattern = args.get("pattern", "")
        path_arg = args.get("path", ".")
        regex = bool(args.get("regex", True))
        max_results = int(args.get("max_results", 200))
        # check cache
        cache_key = f"grep:{pattern}:{path_arg}:{regex}:{max_results}"
        cached = tcache_get(cache_key)
        if cached is not None:
            return ToolResult(ok=True, output=cached)
        try:
            base = resolve_under_root(path_arg)
        except (PermissionError, ValueError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        try:
            rx = re.compile(pattern) if regex else re.compile(re.escape(pattern))
        except re.error as exc:
            return ToolResult(ok=False, output="", error=f"bad regex: {exc}")

        # walk through files and find matches
        results: list[str] = []
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    rel = p.relative_to(base).as_posix()
                    results.append(f"{rel}:{i}: {line}")
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break
        if not results:
            out = "(no matches)"
        else:
            out = "\n".join(results)
        tcache_set(cache_key, out)
        return ToolResult(ok=True, output=out)
