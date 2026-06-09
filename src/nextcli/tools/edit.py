# edit_file tool: replace exact string in a file with uniqueness check.
# clears the tool cache for the edited path so readers get fresh data.

from __future__ import annotations

from pathlib import Path

from nextcli.tools.base import ToolContext, ToolResult
from nextcli.tools.tool_cache import tcache_clear
from nextcli.util.paths import resolve_under_root


class EditFile:
    name = "edit_file"
    description = (
        "Replace an exact substring in a file. By default, `old` must appear "
        "exactly once. Set replace_all=true to replace every occurrence."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string", "description": "Exact substring to find (including whitespace)."},
            "new": {"type": "string", "description": "Replacement text."},
            "replace_all": {"type": "boolean", "default": False},
        },
        "required": ["path", "old", "new"],
    }

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        # find the old string and replace it with the new one
        path_arg = args.get("path", "")
        old = args.get("old", "")
        new = args.get("new", "")
        replace_all = bool(args.get("replace_all", False))
        if not old:
            return ToolResult(ok=False, output="", error="`old` must be non-empty")
        try:
            p = resolve_under_root(path_arg)
        except (PermissionError, ValueError) as exc:
            return ToolResult(ok=False, output="", error=str(exc))
        if not p.exists():
            return ToolResult(ok=False, output="", error=f"file not found: {p}")
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=f"read error: {exc}")

        # make sure the old string is found
        count = text.count(old)
        if count == 0:
            return ToolResult(ok=False, output="", error="`old` substring not found in file")
        if count > 1 and not replace_all:
            return ToolResult(
                ok=False,
                output="",
                error=f"`old` is ambiguous: found {count} occurrences. Pass replace_all=true or narrow `old`.",
            )

        # do the replacement
        if replace_all:
            new_text = text.replace(old, new)
        else:
            new_text = text.replace(old, new, 1)
        try:
            p.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=f"write error: {exc}")
        # file changed, clear cache entries for this path
        tcache_clear(path_arg)
        return ToolResult(ok=True, output=f"replaced {count if replace_all else 1} occurrence(s) in {p}")
