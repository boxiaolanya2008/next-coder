# nextcli

> Next-generation Python AI CLI. **Visualises** Planner / Explorer / Implementer / Reviewer working in parallel, so writing code with AI stops being a black box.

```
+-------------------+--------------------------------+
| AGENTS (1/3)      | CHAT LOG                       |
| > Planner  [OK]   | User: Refactor example.py to   |
| > Explorer [..]   |   use dataclasses + write tests|
|   Implementer[..] |                                |
|   Reviewer    [..]|  Plan: 3 sub-tasks...           |
+-------------------+--------------------------------+
| TOOL TRACE                                           |
| [explorer]    read example.py             -> 412 ch  |
| [implementer] edit example.py (dataclass)...         |
| [reviewer]    shell "pytest -q"           -> 3 pass  |
+-----------------------------------------------------+
| > _                                                  |
+-----------------------------------------------------+
```

## Features

- **Multi-agent by default** — Planner, Explorer, Implementer and Reviewer run in parallel; every agent is live on the Agent Board at all times.
- **Color-coded tool trace** — every file read/write and shell call is attributed to the agent that issued it, with a coloured left border.
- **Works offline** — `NEXTCLI_USE_MOCK=1` runs the full four-agent flow with canned responses, no API key required.
- **Built on Textual** — full-screen TUI, mouse-friendly, scrollable, and tested on Windows Terminal, macOS Terminal and Linux.
- **Multiple LLM providers** — Anthropic, OpenAI, Mock, and any OpenAI-compatible Custom endpoint. Switch via env var, config file or CLI flag.
- **Toolset** — `read_file`, `write_file`, `edit_file`, `run_shell`, `glob_files`, `grep`, and the meta-tool `spawn_agent`.
- **Live context-window meter** — the title bar shows current/peak token usage and a coloured fill rate against the model's window (default 1M tokens).
- **Live cost meter** — input/output tokens × Claude Opus 4-6 pricing, updated as the run progresses.
- **Code-write diff** — every `edit_file` and `write_file` is rendered with syntax-highlighted unified diffs / previews.
- **Slash-command palette** — type `/` to get a ClaudeCode-style command picker with descriptions and aliases (`/resume`, `/config`, `/clear`, `/help`).
- **Session resume** — every run is saved to `~/.next-cli/sessions/<workspace>_<timestamp>.json`; `/resume` opens a bottom drawer to search, pick, and re-enter a past session.
- **Workspace-scoped sessions** — file names include a slug of the current working directory so different projects never collide.
- **Sub-agent detail view** — double-click any agent on the board to open its full message history in a modal.
- **Headless mode** — `nextcli --plain --task "..."` runs without TUI for CI / scripting.
- **Onboarding wizard** — first run captures provider, API key, base URL and model in a 4-step Textual ModalScreen.

## Why nextcli

| Other CLIs | nextcli |
| --- | --- |
| Single agent, serial execution | Four agents running in parallel: Plan / Explore / Implement / Review |
| Tool calls are a black-box log | Tool calls are colour-banded by agent — who did what is obvious |
| API key required from minute one | Mock provider gives you the full demo in 1 second, no key needed |
| TUI *or* CLI, pick one | Both: interactive TUI for humans, `--plain` for CI |
| Lose every session when the process exits | Every run auto-saved, searchable, resumable from `/resume` |
| Hidden context window | Live token / cost / context-window meter in the title bar |

## Installation

### Requirements

- Python **3.11+**
- A virtual environment is recommended

### From source (recommended for development)

```bash
git clone <your-repo-url> nextcli
cd nextcli
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### From PyPI (when published)

```bash
pip install nextcli
```

## Quick start

### 1. Try it offline (no API key)

```bash
NEXTCLI_USE_MOCK=1 nextcli
```

Type a task when prompted, for example:

```
Refactor tests/fixtures/sample_repo/example.py to use dataclasses and add tests
```

Within ~1 second you will see four agents spin up, colour-coded tool traces, and a final answer streamed into the chat log.

### 2. Use a real LLM

```bash
export NEXTCLI_ANTHROPIC_API_KEY=sk-ant-...
nextcli
```

On first launch the 4-step onboarding wizard will offer to save the key to `~/.next-cli/config.json`.

### 3. Custom (OpenAI-compatible) provider

```bash
export NEXTCLI_PROVIDER=custom
export NEXTCLI_CUSTOM_API_KEY=sk-...
export NEXTCLI_CUSTOM_BASE_URL=https://openrouter.ai/api/v1
export NEXTCLI_CUSTOM_MODEL=anthropic/claude-sonnet-4-5
nextcli
```

## Usage

```bash
nextcli                       # use the default provider (env / .env / config.json)
nextcli --provider mock       # override to mock for this run
NEXTCLI_USE_MOCK=1 nextcli    # same as above
```

### Slash commands

Type `/` in the input bar to open the command palette. Use ↑/↓ to navigate, Enter to run, Tab to complete.

| Command | Description | Aliases |
| --- | --- | --- |
| `/resume` | Browse and resume a past session for this workspace | `/sessions` |
| `/config` | Reconfigure provider, API key, or model | `/setup`, `/onboard` |
| `/clear` | Clear chat, board and trace panes | |
| `/help` | List all commands and keybindings | |

### Keybindings

| Key | Action |
| --- | --- |
| `Enter` (input bar) | Submit the current task |
| `Ctrl+C` | Quit |
| `Ctrl+R` | Reopen the configuration wizard |
| `Esc` (while palette is open) | Close the palette |
| Double-click an agent pill | Open that agent's full message history |

### Headless mode

```bash
nextcli --plain --task "add docstrings and run pytest"
```

Events are printed to stdout, one per line, suitable for piping and CI logs.

## Architecture

```
src/nextcli/
├── agent/          # agent event loop, role prompts, event bus
├── llm/            # LLMProvider protocol + Anthropic / OpenAI / Mock / Custom
├── tools/          # tool base + read / write / edit / shell / glob / grep / spawn_agent
├── orchestrator/   # Planner, fan-out / gather / merge, Runner
├── tui/            # Textual app, panes, command palette, resume drawer
├── util/           # logging, paths
├── cli.py          # CLI entry point
├── config.py       # env / .env / config.json three-layer merge
└── __main__.py     # `python -m nextcli` entry
```

| Module | Responsibility |
| --- | --- |
| `agent/` | `AgentEvent` / `EventBus` / `Agent.run()` loop and one system prompt per role. |
| `llm/` | Single `LLMProvider` protocol with a streaming `stream()` method; concrete adapters translate vendor-specific tool schemas. |
| `tools/` | `Tool` protocol, `ToolRegistry` with per-role allowlists, and the seven built-in tools. |
| `orchestrator/` | Spawns sub-agents from the planner's tool calls, gathers their final outputs, then re-invokes the planner with a summary prompt so it can write a final answer. |
| `tui/` | `NextCliApp`, `AgentBoard`, `ChatLog`, `ToolTrace`, `InputBar`, `CommandPalette`, `ResumeScreen`, `SessionViewerScreen`, `AgentDetailScreen`, `OnboardingScreen`. |
| `util/` | `paths.py` (workspace slug, project-root resolution), `log.py`. |

### Context window

The title bar's `ctx` segment is driven by `_CONTEXT_WINDOWS` in `tui/app.py`:

| Model | Window |
| --- | --- |
| `claude-opus-4-8`, `claude-opus-4-6`, `claude-sonnet-4-5`, `claude-sonnet-4-6` | 1,000,000 |
| `claude-haiku-4-5`, `o1`, `o3-mini` | 200,000 |
| `gpt-4o`, `gpt-4o-mini` | 128,000 |
| Anything else | 1,000,000 (default) |

The cost is computed at Opus 4-6 list price: **$15 / 1M input tokens**, **$75 / 1M output tokens**.

## Configuration

Configuration is merged with the following precedence (higher wins):

1. Environment variables
2. Project-root `.env` (loaded by `python-dotenv`)
3. `~/.next-cli/config.json` (persisted by the onboarding wizard)

### Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `NEXTCLI_PROVIDER` | `anthropic` / `openai` / `mock` / `custom` | `anthropic` |
| `NEXTCLI_USE_MOCK` | Truthy values (`1` / `true` / `yes` / `on`) force mock mode | `0` |
| `NEXTCLI_ANTHROPIC_API_KEY` | Anthropic API key | — |
| `NEXTCLI_OPENAI_API_KEY` | OpenAI API key | — |
| `NEXTCLI_CUSTOM_API_KEY` | Custom (OpenAI-compatible) provider key | — |
| `NEXTCLI_CUSTOM_BASE_URL` | Custom provider base URL | — |
| `NEXTCLI_ANTHROPIC_MODEL` | Anthropic model name | `claude-sonnet-4-5` |
| `NEXTCLI_OPENAI_MODEL` | OpenAI model name | `gpt-4o` |
| `NEXTCLI_CUSTOM_MODEL` | Custom provider model name | — |

See `.env.example` for a complete template.

### Session files

Every completed run writes one JSON file:

```
~/.next-cli/sessions/<workspace-slug>_<YYYY-MM-DD_HH-MM-SS>.json
```

Where `<workspace-slug>` is the working-directory path with non-alphanumeric characters replaced by `-` (e.g. `D:/31702/next-ai-cli` → `D-31702-next-ai-cli`). This keeps projects isolated.

## Running tests

```bash
pip install -e ".[dev]"
pytest -q
```

All tests use the mock provider, so no API key is required. `pyproject.toml` already sets `asyncio_mode = auto`.

## Contributing

1. Fork the repo and create a feature branch: `git checkout -b feat/your-feature`
2. Install dev dependencies: `pip install -e ".[dev]"`
3. Make your change and add tests
4. Make sure `pytest -q` is green before pushing
5. Open a Pull Request describing motivation and behaviour changes

Larger changes should be discussed in an issue first. Match the existing module layout and type-hint style.

## License

MIT. See `pyproject.toml` for the SPDX identifier.

---

🌐 Other languages: [简体中文](README-zh-CN.md)
