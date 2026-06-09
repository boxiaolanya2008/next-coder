# run_shell tool: run a shell command with timeout.

from __future__ import annotations

import asyncio
import shlex

from nextcli.tools.base import ToolContext, ToolResult


class RunShell:
    name = "run_shell"
    description = (
        "Run a shell command and return (exit_code, stdout, stderr). "
        "Truncates combined output at ~20k chars."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "Command string passed to the system shell."},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 300)."},
        },
        "required": ["cmd"],
    }

    _MAX_OUT = 20_000

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        # run the command and capture output
        cmd = args.get("cmd", "")
        timeout = max(1, min(int(args.get("timeout", 30)), 300))
        if not cmd.strip():
            return ToolResult(ok=False, output="", error="empty command")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(ok=False, output="", error=f"timeout after {timeout}s")
        except OSError as exc:
            return ToolResult(ok=False, output="", error=f"shell error: {exc}")

        # decode and combine output
        stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
        stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
        combined = stdout + (("\n[stderr]\n" + stderr) if stderr else "")
        if len(combined) > self._MAX_OUT:
            combined = combined[: self._MAX_OUT] + "\n... (truncated)"
        ok = proc.returncode == 0
        return ToolResult(
            ok=ok,
            output=combined,
            error=None if ok else f"exit code {proc.returncode}",
        )
