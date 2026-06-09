# nextcli

> 下一代 Python 多 agent 编码助手 CLI。**实时可视化** Planner / Explorer / Implementer / Reviewer 并行协作，让 AI 写代码的过程从"黑盒"变成"白盒"。

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

## 特性 (Features)

- **多 agent 协同**：Planner / Explorer / Implementer / Reviewer 等角色并行工作，全程在 Agent Board 中可见。
- **彩色 trace 输出**：每个文件读写、shell 命令都按发起 agent 的角色着色（左侧色条），一眼看清谁在做什么。
- **离线 mock 模式**：无需任何 API key 即可体验完整的 4 agent 协作流程，方便快速预览与测试。
- **Textual TUI 界面**：全屏终端 UI，支持鼠标、键盘、可滚动、可搜索，Windows Terminal / macOS Terminal / Linux 终端开箱即用。
- **多 LLM provider**：内置 Anthropic、OpenAI、Mock、自定义（OpenAI 兼容）四种 provider，可通过环境变量或 CLI 参数切换。
- **工具集完备**：`read` / `write` / `edit` / `shell` / `glob` / `grep` / `spawn_agent`，覆盖日常编码场景。
- **会话持久化**：支持保存与恢复会话，便于回溯与续作。
- **headless 模式**：`--plain` + `--task` 可在 CI / 脚本中无 TUI 运行。

## 为什么选择 nextcli (Why nextcli)

| 其他 CLI | nextcli |
| --- | --- |
| 单 agent 串行执行 | 多 agent 并行，Plan / Explore / Implement / Review 同步进行 |
| 工具调用是黑盒日志 | 工具调用带角色色条，谁调的、结果如何一目了然 |
| 必须配置 API key | 自带 Mock provider，零配置即可演示 |
| 纯命令行 / 纯 TUI 二选一 | 交互式 TUI + headless 模式皆可，CI 友好 |

nextcli 的目标是**让你真正"看到" AI 在做什么**——而不是只能看最终结果。

## 安装 (Installation)

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

### 方式二：直接 pip install

```bash
pip install nextcli
```

> Windows 用户请把 `source .venv/bin/activate` 替换为 `.venv\Scripts\activate`。

## 快速开始 (Quick Start)

### 1. 离线体验（无需 API key）

最快的方式是先用 mock provider 跑一遍：

```bash
NEXTCLI_USE_MOCK=1 nextcli
```

启动后输入任务，例如：

```
Refactor tests/fixtures/sample_repo/example.py to use dataclasses and add tests
```

约 1 秒内你会看到 4 个 agent 同时上线，工具调用按角色着色，Chat Log 中流式输出最终答复。

### 2. 配置真实 LLM

复制示例环境变量文件并填入你的 key：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
# Provider 选择：anthropic | openai | mock | custom
NEXTCLI_PROVIDER=anthropic

NEXTCLI_ANTHROPIC_API_KEY=sk-ant-...
# NEXTCLI_OPENAI_API_KEY=sk-...

NEXTCLI_ANTHROPIC_MODEL=claude-sonnet-4-5
NEXTCLI_OPENAI_MODEL=gpt-4o
```

也可通过环境变量直接传入（适合临时使用）：

```bash
export NEXTCLI_ANTHROPIC_API_KEY=sk-ant-...
nextcli
```

启动后即可使用真实模型。

### 3. 自定义 Provider（OpenAI 兼容）

```bash
NEXTCLI_PROVIDER=custom
NEXTCLI_CUSTOM_API_KEY=your-key
NEXTCLI_CUSTOM_BASE_URL=https://your-endpoint/v1
NEXTCLI_CUSTOM_MODEL=your-model-name
nextcli
```

## 使用方法 (Usage)

### 启动 TUI

```bash
nextcli                                 # 使用默认 provider（来自 .env / 环境变量）
nextcli --provider mock                 # 临时切换为 mock
NEXTCLI_USE_MOCK=1 nextcli              # 等价于 --provider mock
```

### headless 模式（无 TUI，适合 CI / 脚本）

```bash
nextcli --plain --task "add docstring to foo.py and run pytest"
```

事件会按行打印到 stdout，便于管道与日志收集。

### 常用参数

| 参数 | 说明 |
| --- | --- |
| `--provider {anthropic,openai,mock}` | 临时覆盖 `NEXTCLI_PROVIDER` |
| `--plain` | 关闭 TUI，使用纯文本输出 |
| `--task "..."` | 与 `--plain` 配合，单任务执行后退出 |
| `--help` | 查看完整帮助 |

## 架构 (Architecture)

```
src/nextcli/
├── agent/          # agent 事件循环、角色 prompts、事件总线
├── llm/            # LLMProvider 协议 + Anthropic / OpenAI / Mock / Custom 实现
├── tools/          # 工具基类 + read/write/edit/shell/glob/grep/spawn_agent
├── orchestrator/   # Planner、fan-out / gather / merge、Runner
├── tui/            # Textual App、四象限布局、状态板、命令面板
├── util/           # 日志、路径等通用工具
├── cli.py          # 命令行入口
├── config.py       # env / .env / ~/.next-cli/config.json 三层配置合并
└── __main__.py     # `python -m nextcli` 入口
```

各模块职责：

- **agent/**：定义 agent 事件、事件循环、每个角色（planner/explorer/implementer/reviewer）的 system prompt。
- **llm/**：抽象 `LLMProvider` 协议，向上提供统一的 `stream()` 接口；向下适配 Anthropic / OpenAI / Mock / 自定义 OpenAI 兼容端点。
- **tools/**：工具协议 + 默认注册表；agent 通过工具读写文件、执行 shell、搜索代码、生成子 agent。
- **orchestrator/**：负责把用户的复杂任务拆给多个 agent（planner → fan-out → gather → merge），并归并结果。
- **tui/**：基于 Textual 的终端 UI，Agent Board / Chat Log / Tool Trace / 输入框四象限，鼠标键盘均可操作。
- **util/**：日志、路径等横切关注点。

## 运行测试 (Running Tests)

测试使用 pytest，**不需要任何 API key**（默认走 mock）：

```bash
pip install -e ".[dev]"
pytest -q
```

`pyproject.toml` 已配置 `asyncio_mode = auto`，异步测试无需手动装饰。

## 配置 (Configuration)

配置按以下优先级合并（高优先级覆盖低优先级）：

1. **环境变量**（最高）
2. **项目根目录 `.env`**（由 `python-dotenv` 加载）
3. **`~/.next-cli/config.json`**（用户级持久化配置）

### 支持的环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `NEXTCLI_PROVIDER` | `anthropic` / `openai` / `mock` / `custom` | `anthropic` |
| `NEXTCLI_USE_MOCK` | 任意真值（`1`/`true`/`yes`/`on`）强制走 mock | `0` |
| `NEXTCLI_ANTHROPIC_API_KEY` | Anthropic API key | — |
| `NEXTCLI_OPENAI_API_KEY` | OpenAI API key | — |
| `NEXTCLI_CUSTOM_API_KEY` | 自定义 provider API key | — |
| `NEXTCLI_CUSTOM_BASE_URL` | 自定义 provider Base URL（OpenAI 兼容） | — |
| `NEXTCLI_ANTHROPIC_MODEL` | Anthropic 模型名 | `claude-sonnet-4-5` |
| `NEXTCLI_OPENAI_MODEL` | OpenAI 模型名 | `gpt-4o` |
| `NEXTCLI_CUSTOM_MODEL` | 自定义 provider 模型名 | — |

> 完整字段可参考项目根目录的 `.env.example`。

## 贡献 (Contributing)

欢迎贡献！建议流程：

1. Fork 本仓库并创建特性分支：`git checkout -b feat/your-feature`
2. 安装开发依赖：`pip install -e ".[dev]"`
3. 修改代码并补充测试：`pytest -q`
4. 提交前确保测试通过、commit message 清晰
5. 发起 Pull Request，描述动机与变更点

大的功能变更建议先开 issue 讨论设计。代码风格遵循现有目录的惯例（`ruff` / `black` 配置可在后续补充）。

## 许可证 (License)

本项目使用 **MIT License**，详见 `pyproject.toml` 中的 `license` 字段。
