# 🚀 SuperAI MCP

将 **Gemini CLI**、**Codex CLI** 和 **Claude CLI** 包装为 MCP 工具，让 Claude Code 能调用其他 AI CLI 进行 code review 和编码任务。

## ✨ 特性

- 🔧 **四工具**: `mcp__super__codex` + `mcp__super__gemini` + `mcp__super__claude` + `mcp__super__broadcast`
- 📋 **四种模式**: prompt 转发 / git diff review / 文件列表 review / commit 审查
- 🔄 **会话续接**: 通过 `session_id` 延续上下文
- 🎯 **模型选择**: 支持指定模型和推理深度
- ⚡ **纯异步**: 基于 `asyncio.create_subprocess_exec`，无线程
- 🔒 **安全**: 路径遍历防护、git ref 校验、无 shell 注入
- 📡 **进度通知**: 长时间任务每 25s 发送 `report_progress` keepalive
- 🔄 **配额回退**: 限流时自动级联降级（Gemini→flash / Claude→sonnet→haiku / Codex effort 降级）
- 🏷️ **工具注解**: 每个工具附带 `ToolAnnotations` 元数据

## 📦 前置依赖

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- 至少安装以下 CLI 之一（未安装的会在调用时返回错误，不影响其他工具）：
  - [Codex CLI](https://github.com/openai/codex) — `npm install -g @openai/codex`
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli) — `npm install -g @google/gemini-cli`
  - [Claude Code](https://github.com/anthropics/claude-code) — `curl -fsSL https://claude.ai/install.sh | bash` 或 `brew install --cask claude-code`

## 🔌 安装与配置

### Claude Code

```bash
# 从 Git 直接安装（推荐）
claude mcp add super -s user --transport stdio -- uvx --from git+https://github.com/babywbx/SuperAI-MCP.git superai-mcp

# 或 clone 后本地安装
git clone https://github.com/babywbx/SuperAI-MCP.git
claude mcp add super -s user --transport stdio -- uv run --directory /path/to/SuperAI-MCP superai-mcp
```

<details>
<summary>手动编辑配置文件</summary>

在 `~/.claude/mcp.json`（全局）或 `.mcp.json`（项目级）中添加：

```json
{
  "mcpServers": {
    "super": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/babywbx/SuperAI-MCP.git", "superai-mcp"]
    }
  }
}
```

</details>

<details>
<summary>可选：自动允许工具调用（免去每次确认）</summary>

在 `~/.claude/settings.json` 中添加：

```json
{
  "permissions": {
    "allow": [
      "mcp__super"
    ]
  }
}
```

也可以只允许特定工具：`"mcp__super__codex"`、`"mcp__super__gemini"`、`"mcp__super__claude"`、`"mcp__super__broadcast"`。

</details>

### Codex CLI

在 `~/.codex/config.toml` 中添加：

```toml
[mcp_servers.super]
command = "uvx"
args = ["--from", "git+https://github.com/babywbx/SuperAI-MCP.git", "superai-mcp"]
```

### Gemini CLI

```bash
gemini mcp add super -- uvx --from git+https://github.com/babywbx/SuperAI-MCP.git superai-mcp
```

<details>
<summary>手动编辑配置文件</summary>

在 `~/.gemini/settings.json` 中添加：

```json
{
  "mcpServers": {
    "super": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/babywbx/SuperAI-MCP.git", "superai-mcp"]
    }
  }
}
```

</details>

配置后重启对应 CLI 即可使用。

## 🛠️ 工具参数

### `codex`

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | 必填 | 任务指令 |
| `cd` | str | 必填 | 工作目录 |
| `session_id` | str | `""` | 会话续接 |
| `sandbox` | str | `"read-only"` | 沙盒模式 |
| `model` | str | `""` | 模型名 |
| `reasoning_effort` | str | `""` | 推理深度: low/medium/high/xhigh |
| `review_uncommitted` | bool | `False` | 审查未提交更改 |
| `review_base` | str | `""` | 审查相对于某分支的更改 |
| `review_commit` | str | `""` | 审查特定 commit (7-40 位 hex SHA) |
| `files` | list[str] | `None` | 文件列表模式 |
| `return_all_messages` | bool | `False` | 返回完整事件流 |
| `auto_split` | bool | `False` | 自动拆分大任务为子任务执行 |

### `gemini`

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | 必填 | 任务指令 |
| `cd` | str | 必填 | 工作目录 |
| `session_id` | str | `""` | 会话续接 |
| `sandbox` | bool | `True` | 是否沙盒 |
| `model` | str | `""` | 模型名/别名 (pro, flash 等) |
| `review_uncommitted` | bool | `False` | 审查未提交更改 |
| `review_base` | str | `""` | 审查相对于某分支的更改 |
| `review_commit` | str | `""` | 审查特定 commit (7-40 位 hex SHA) |
| `files` | list[str] | `None` | 文件列表模式 |
| `return_all_messages` | bool | `False` | 返回完整事件流 |
| `auto_split` | bool | `False` | 自动拆分大任务为子任务执行 |

### `claude`

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | 必填 | 任务指令 |
| `cd` | str | 必填 | 工作目录 |
| `session_id` | str | `""` | 会话续接 (映射到 --resume) |
| `sandbox` | str | `"read-only"` | 沙盒模式 (映射到权限模式) |
| `model` | str | `""` | 模型名 (opus/sonnet/haiku 等) |
| `effort` | str | `""` | 推理深度: low/medium/high |
| `max_budget_usd` | float | `0.0` | API 费用上限 (0=不限) |
| `review_uncommitted` | bool | `False` | 审查未提交更改 |
| `review_base` | str | `""` | 审查相对于某分支的更改 |
| `review_commit` | str | `""` | 审查特定 commit (7-40 位 hex SHA) |
| `files` | list[str] | `None` | 文件列表模式 |
| `return_all_messages` | bool | `False` | 返回完整 JSON |
| `auto_split` | bool | `False` | 自动拆分大任务为子任务执行 |

### `broadcast`

将同一 prompt 并发发送给多个 CLI，聚合返回结果。适用于对比不同 AI 的回答。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | 必填 | 任务指令 |
| `cd` | str | 必填 | 工作目录 |
| `targets` | list[str] | `None` | 目标 CLI 列表，空=全部 (`codex`, `gemini`, `claude`) |
| `model` | str | `""` | 传给各 CLI 的模型名 |
| `review_uncommitted` | bool | `False` | 审查未提交更改 |
| `review_base` | str | `""` | 审查相对于某分支的更改 |
| `review_commit` | str | `""` | 审查特定 commit (7-40 位 hex SHA) |
| `files` | list[str] | `None` | 文件列表模式 |
| `return_all_messages` | bool | `False` | 返回完整事件流 |

## 🚦 使用模式

```
1️⃣ 默认模式 — prompt 直接转发给 CLI
2️⃣ Review 模式 — 自动获取 git diff 注入 prompt (uncommitted / base / commit)
3️⃣ 文件模式 — 读取文件内容注入 prompt
```

## 🔄 配额/限流回退

当 CLI 返回限流错误（`RESOURCE_EXHAUSTED`、`overloaded_error`、`429`、`rate_limit`、`quota` 等）时，会自动级联降级重试。降级前先发一个短探测请求验证目标可用。

| CLI | 回退策略 | 示例 |
|-----|---------|------|
| **Gemini** | 切换为 `flash` 模型 | `pro` → `flash` |
| **Claude** | 按模型降级 | 当前模型 → `sonnet` → `haiku` |
| **Codex** | 降低推理深度 | `high` → `medium` → `low` |

成功时响应内容以 `[fallback: ...]` 前缀标注（如 `[fallback: sonnet]`、`[fallback: effort=medium]`）。
如果已处于链末端（Gemini 已用 `flash`、Claude 已用 `haiku`、Codex 已用 `low`），不会重试。

## 📡 进度通知

CLI 执行期间每 25 秒通过 MCP `report_progress` 发送一次心跳通知，包含已运行时间。
防止长时间任务时客户端误判超时断开连接。

## 🧪 测试

```bash
uv run pytest -v
```

## 📄 许可

MIT License © 2026 [Babywbx](https://github.com/babywbx)
