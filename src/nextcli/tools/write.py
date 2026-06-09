# write_file tool: create or overwrite a file.
# clears the tool cache for the written path so readers get fresh data.

from __future__ import annotations

from pathlib import Path

from nextcli.tools.base import ToolContext, ToolResult
from nextcli.tools.tool_cache import tcache_clear
from nextcli.util.paths import resolve_under_root


class WriteFile:
    name = "write_file"
    description = "Create or overwrite a UTF-8 text file. Use edit_file for surgical changes."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        # resolve path and write content
        path_arg = args.get("path", "")
        content = args.get("content", "")
        try:
            p = resolve_under_root(path_arg)
        except (PermissionError, ValueError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=f"write error: {exc}")
        # file changed, clear cache entries for this path
        tcache_clear(path_arg)
        return ToolResult(ok=True, output=f"wrote {len(content)} bytes to {p}")
