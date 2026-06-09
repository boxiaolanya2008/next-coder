# nextcli

> 下一代 Python 多 Agent 编码助手 CLI。**实时可视化** Planner / Explorer / Implementer / Reviewer 并行协作，让 AI 写代码的过程从"黑盒"变成"白盒"。

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

## 特性

- **多 Agent 协同**：Planner / Explorer / Implementer / Reviewer 等角色并行工作，全程在 Agent Board 中可见。
- **彩色 trace 输出**：每个文件读写、shell 命令都按发起 Agent 的角色着色（左侧色条），一眼看清谁在做什么。
- **离线 mock 模式**：无需任何 API key 即可体验完整的 4 Agent 协作流程，方便快速预览与测试。
- **Textual TUI 界面**：全屏终端 UI，支持鼠标、键盘、可滚动，Windows Terminal / macOS Terminal / Linux 终端开箱即用。
- **多 LLM provider**：内置 Anthropic、OpenAI、Mock、自定义（OpenAI 兼容）四种 provider，可通过环境变量、配置文件或 CLI 参数切换。
- **工具集完备**：`read_file` / `write_file` / `edit_file` / `run_shell` / `glob_files` / `grep` / `spawn_agent`，覆盖日常编码场景。
- **顶部上下文窗口计量**：标题栏实时显示当前 / 峰值 token 用量，按模型窗口大小（默认 100 万）显示带颜色的填充率。
- **实时费用计量**：按 Claude Opus 4-6 价格（$15 / 1M 输入、$75 / 1M 输出）实时累计本次任务的费用。
- **代码写入对比**：`edit_file` 渲染 unified diff 面板，`write_file` 渲染语法高亮预览。
- **斜杠命令面板**：输入 `/` 弹出 ClaudeCode 风格的命令选择器，带描述与别名（`/resume`、`/config`、`/clear`、`/help`）。
- **会话恢复**：每次任务自动保存到 `~/.next-cli/sessions/<workspace>_<时间戳>.json`；`/resume` 打开底部抽屉搜索并续作历史会话。
- **工作区隔离的会话文件**：文件名包含工作目录的 slug（路径非字母数字字符替换为 `-`），不同项目互不冲突。
- **子 Agent 详情视图**：双击 Agent Board 上的任意 pill 弹出该 Agent 的完整 message 历史。
- **headless 模式**：`--plain` + `--task` 可在 CI / 脚本中无 TUI 运行。
- **Onboarding 向导**：首次运行通过 4 步 Textual ModalScreen 录入 provider、API key、Base URL、模型并保存到 `~/.next-cli/config.json`。

## 为什么选择 nextcli

| 其他 CLI | nextcli |
| --- | --- |
| 单 agent 串行执行 | 四 agent 并行：Plan / Explore / Implement / Review 同步进行 |
| 工具调用是黑盒日志 | 工具调用带角色色条，谁调的、结果如何一目了然 |
| 必须配置 API key | 自带 Mock provider，零配置即可演示 |
| 纯命令行 / 纯 TUI 二选一 | 交互式 TUI + headless 模式皆可，CI 友好 |
| 进程退出后所有上下文丢失 | 每次任务自动存档，可搜索、可从 `/resume` 续作 |
| 上下文窗口大小看不到 | 顶部栏实时显示 token / 费用 / 上下文窗口填充率 |

## 安装

### 前置要求

- Python **3.11+**
- 推荐使用虚拟环境

### 方式一：从源码安装（推荐）

```bash
git clone <your-repo-url> nextcli
cd nextcli
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 方式二：pip 安装（待发布后）

```bash
pip install nextcli
```

## 快速开始

### 1. 离线体验（无需 API key）

最快的方式是先用 mock provider 跑一遍：

```bash
NEXTCLI_USE_MOCK=1 nextcli
```

启动后输入任务，例如：

```
Refactor tests/fixtures/sample_repo/example.py to use dataclasses and add tests
```

约 1 秒内你会看到 4 个 Agent 同时上线，工具调用按角色着色，Chat Log 中流式输出最终答复。

### 2. 配置真实 LLM

```bash
export NEXTCLI_ANTHROPIC_API_KEY=sk-ant-...
nextcli
```

首次启动时，4 步 onboarding 向导会引导你把 key 写入 `~/.next-cli/config.json`。

### 3. 自定义 Provider（OpenAI 兼容）

```bash
export NEXTCLI_PROVIDER=custom
export NEXTCLI_CUSTOM_API_KEY=sk-...
export NEXTCLI_CUSTOM_BASE_URL=https://openrouter.ai/api/v1
export NEXTCLI_CUSTOM_MODEL=anthropic/claude-sonnet-4-5
nextcli
```

## 使用方法

```bash
nextcli                       # 使用默认 provider（env / .env / config.json）
nextcli --provider mock       # 临时切换为 mock
NEXTCLI_USE_MOCK=1 nextcli    # 等价于 --provider mock
```

### 斜杠命令

在输入框输入 `/` 打开命令面板，↑/↓ 选择，Enter 执行，Tab 补全。

| 命令 | 描述 | 别名 |
| --- | --- | --- |
| `/resume` | 浏览并续作本工作区历史会话 | `/sessions` |
| `/config` | 重新配置 provider、API key、模型 | `/setup`、`/onboard` |
| `/clear` | 清空 chat、board、trace 三个面板 | |
| `/help` | 列出所有命令与键位 | |

### 键位

| 按键 | 作用 |
| --- | --- |
| 输入框 `Enter` | 提交当前任务 |
| `Ctrl+C` | 退出 |
| `Ctrl+R` | 重新打开配置向导 |
| 命令面板打开时 `Esc` | 关闭面板 |
| 双击 Agent 面板上的 pill | 打开该 Agent 的完整 message 历史 |

### headless 模式

```bash
nextcli --plain --task "add docstrings and run pytest"
```

事件按行打印到 stdout，适合管道与日志收集。

## 架构

```
src/nextcli/
├── agent/          # agent 事件循环、角色 prompts、事件总线
├── llm/            # LLMProvider 协议 + Anthropic / OpenAI / Mock / Custom
├── tools/          # 工具基类 + read / write / edit / shell / glob / grep / spawn_agent
├── orchestrator/   # Planner、fan-out / gather / merge、Runner
├── tui/            # Textual App、各 pane、命令面板、resume 抽屉
├── util/           # 日志、路径
├── cli.py          # 命令行入口
├── config.py       # env / .env / config.json 三层配置合并
└── __main__.py     # `python -m nextcli` 入口
```

| 模块 | 职责 |
| --- | --- |
| `agent/` | `AgentEvent` / `EventBus` / `Agent.run()` 主循环，以及每个角色（planner / explorer / implementer / reviewer）的 system prompt。 |
| `llm/` | 单一 `LLMProvider` 协议，统一的流式 `stream()` 接口；具体 adapter 负责把厂商私有的 tool schema 翻译为内部协议。 |
| `tools/` | `Tool` 协议、按角色 allowlist 的 `ToolRegistry`，以及 7 个内置工具。 |
| `orchestrator/` | 从 planner 的 tool call 派生子 Agent；任务结束后收集子 Agent 输出，回注到 planner 的 message history，再调用一次 planner 写最终总结。 |
| `tui/` | `NextCliApp`、`AgentBoard`、`ChatLog`、`ToolTrace`、`InputBar`、`CommandPalette`、`ResumeScreen`、`SessionViewerScreen`、`AgentDetailScreen`、`OnboardingScreen`。 |
| `util/` | `paths.py`（工作区 slug、项目根解析）、`log.py`。 |

### 上下文窗口

标题栏的 `ctx` 段由 `tui/app.py` 中的 `_CONTEXT_WINDOWS` 字典驱动：

| 模型 | 窗口 |
| --- | --- |
| `claude-opus-4-8`、`claude-opus-4-6`、`claude-sonnet-4-5`、`claude-sonnet-4-6` | 1,000,000 |
| `claude-haiku-4-5`、`o1`、`o3-mini` | 200,000 |
| `gpt-4o`、`gpt-4o-mini` | 128,000 |
| 其它 | 1,000,000（默认） |

费用按 Claude Opus 4-6 公开标价计算：**$15 / 1M 输入 token**，**$75 / 1M 输出 token**。

## 配置

配置按以下优先级合并（高优先级覆盖低优先级）：

1. **环境变量**（最高）
2. **项目根目录 `.env`**（由 `python-dotenv` 加载）
3. **`~/.next-cli/config.json`**（由 onboarding 向导持久化）

### 支持的环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `NEXTCLI_PROVIDER` | `anthropic` / `openai` / `mock` / `custom` | `anthropic` |
| `NEXTCLI_USE_MOCK` | 真值（`1` / `true` / `yes` / `on`）强制走 mock | `0` |
| `NEXTCLI_ANTHROPIC_API_KEY` | Anthropic API key | — |
| `NEXTCLI_OPENAI_API_KEY` | OpenAI API key | — |
| `NEXTCLI_CUSTOM_API_KEY` | 自定义 provider API key | — |
| `NEXTCLI_CUSTOM_BASE_URL` | 自定义 provider Base URL（OpenAI 兼容） | — |
| `NEXTCLI_ANTHROPIC_MODEL` | Anthropic 模型名 | `claude-sonnet-4-5` |
| `NEXTCLI_OPENAI_MODEL` | OpenAI 模型名 | `gpt-4o` |
| `NEXTCLI_CUSTOM_MODEL` | 自定义 provider 模型名 | — |

完整字段可参考项目根目录的 `.env.example`。

### 会话文件

每次完成的任务会写入一个 JSON 文件：

```
~/.next-cli/sessions/<workspace-slug>_<YYYY-MM-DD_HH-MM-SS>.json
```

其中 `<workspace-slug>` 是当前工作目录路径的非字母数字字符替换为 `-` 后的形式（例如 `D:/31702/next-ai-cli` → `D-31702-next-ai-cli`），让不同项目的会话互不冲突。

## 运行测试

```bash
pip install -e ".[dev]"
pytest -q
```

所有测试默认走 mock，**不需要任何 API key**。`pyproject.toml` 已设置 `asyncio_mode = auto`，异步测试无需手动装饰。

## 贡献

欢迎贡献！建议流程：

1. Fork 本仓库并创建特性分支：`git checkout -b feat/your-feature`
2. 安装开发依赖：`pip install -e ".[dev]`
3. 修改代码并补充测试：`pytest -q`
4. 提交前确保测试通过、commit message 清晰
5. 发起 Pull Request，描述动机与变更点

大的功能变更建议先开 issue 讨论设计。代码风格遵循现有目录的惯例（`ruff` / `black` 配置可在后续补充）。

## 许可证

本项目使用 **MIT License**，详见 `pyproject.toml` 中的 `license` 字段。

---

🌐 其他语言：[English](README.md)
