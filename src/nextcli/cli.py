"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys

from nextcli.config import Config


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="nextcli",
        description="Next-generation Python AI CLI with parallel multi-agent visualization",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "openai", "mock"],
        help="Override NEXTCLI_PROVIDER env var",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Run without TUI (print events to stdout, useful for CI / piping)",
    )
    parser.add_argument(
        "--task",
        type=str,
        help="(plain mode only) Run a single task and print the result, then exit",
    )
    return parser.parse_args(argv)


async def _run_plain(config: Config, task: str) -> int:
    """Headless mode: run one task with mock or real provider, print events."""
    from nextcli.llm.mock_provider import MockProvider
    from nextcli.llm.provider import LLMProvider
    from nextcli.orchestrator.runner import Orchestrator
    from nextcli.tools import default_registry

    registry = default_registry()
    provider: LLMProvider = MockProvider(model="mock")
    orch = Orchestrator(provider=provider, registry=registry)

    print(f"[nextcli] task: {task}")
    async for ev in orch.stream(task):
        role = ev.role.value
        if ev.kind == "text":
            print(f"[{role}] {ev.payload.get('delta', '')}", end="", flush=True)
        elif ev.kind == "status":
            print(f"\n[{role}] status={ev.payload.get('state')}")
        elif ev.kind == "tool_call":
            name = ev.payload.get('name', '?')
            args = ev.payload.get('arguments', {})
            if name == "spawn_agent":
                print(f"[{role}] tool=spawn_agent -> {args.get('role', '?')} task={args.get('task','')[:80]!r}")
            else:
                print(f"[{role}] tool={name} args={args}")
        elif ev.kind == "tool_result":
            ok = ev.payload.get("ok")
            out = ev.payload.get("output", "")[:200]
            print(f"[{role}] -> ok={ok} {out}")
        elif ev.kind == "done":
            print(f"\n[{role}] done")
    print("\n[nextcli] all agents done")
    return 0


async def _run_tui(config: Config) -> int:
    """Launch the Textual TUI."""
    from nextcli.tui.app import NextCliApp

    app = NextCliApp(config=config)
    await app.run_async()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = Config.load()
    if args.provider:
        # rebuild with override
        import os
        os.environ["NEXTCLI_PROVIDER"] = args.provider
        config = Config.load()

    if args.plain:
        if not args.task:
            print("error: --plain requires --task '...'", file=sys.stderr)
            return 2
        return asyncio.run(_run_plain(config, args.task))
    return asyncio.run(_run_tui(config))


if __name__ == "__main__":
    raise SystemExit(main())
