# glob_files tool: find files matching a glob pattern.
# cached in memory to avoid repeated filesystem walks.

from __future__ import annotations

import fnmatch
from pathlib import Path

from nextcli.tools.base import ToolContext, ToolResult
from nextcli.tools.tool_cache import tcache_get, tcache_set
from nextcli.util.paths import project_root, resolve_under_root


class GlobFiles:
    name = "glob_files"
    description = "List files under `root` matching a glob pattern (recursive, ** supported)."
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "examples": ["**/*.py", "src/**/*.ts"]},
            "root": {"type": "string", "default": "."},
        },
        "required": ["pattern"],
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        # find files that match the pattern
        pattern = args.get("pattern", "")
        root_arg = args.get("root", ".")
        # check cache
        cache_key = f"glob:{pattern}:{root_arg}"
        cached = tcache_get(cache_key)
        if cached is not None:
            return ToolResult(ok=True, output=cached)
        try:
            root = resolve_under_root(root_arg)
        except (PermissionError, ValueError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        if not root.exists():
            return ToolResult(ok=False, output="", error=f"root not found: {root}")
        matches: list[str] = []
        for p in root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                if _match(rel, pattern):
                    matches.append(rel)
        matches.sort()
        if not matches:
            out = "(no matches)"
        else:
            out = "\n".join(matches[:500])
        tcache_set(cache_key, out)
        return ToolResult(ok=True, output=out)


def _match(path: str, pattern: str) -> bool:
    # check if a path matches a glob pattern
    if "**" in pattern:
        regex = _glob_to_regex(pattern)
        import re
        return re.fullmatch(regex, path) is not None
    return fnmatch.fnmatch(path, pattern)


def _glob_to_regex(pattern: str) -> str:
    # convert a glob pattern to a regex
    import re

    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                out.append(".*")
                i += 2
                if i < len(pattern) and pattern[i] == "/":
                    i += 1
                    out.append("(.*/)?")
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == ".":
            out.append(r"\.")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return "^" + "".join(out) + "$"
