# 🚀 SuperAI MCP

将 **Gemini CLI**、**Codex CLI** 和 **Claude CLI** 包装为 MCP 工具，让 Claude Code 能调用其他 AI CLI 进行 code review 和编码任务。

## ✨ 特性

- 🔧 **十工具**: `codex` + `gemini` + `claude` + `broadcast` + `chain` + `vote` + `debate` + `list-models` + `status` + `usage`
- 📋 **五种模式**: prompt 转发 / git diff review (uncommitted/base/commit) / 文件列表 review
- 🔄 **会话续接**: 通过 `session_id` 延续上下文
- 🎯 **模型选择**: 支持指定模型和推理深度
- ⚡ **纯异步**: 基于 `asyncio.create_subprocess_exec`，无线程
- 🔍 **模型发现**: `list-models` 实时查询可用模型，`model` 参数自动校验+纠错建议
- 🔒 **安全**: 路径遍历防护、git ref 校验、无 shell 注入、嵌套深度限制 (最大 5 层)
- 📡 **进度通知**: 长时间任务每 5s 发送 `report_progress` keepalive
- ⏱️ **超时+宽限期**: 默认 300s 超时，CLI 活跃输出时自动延长 (30s 新输出 / 120s 关键词匹配)
- 🔄 **配额回退**: 限流时自动级联降级（Gemini→flash / Claude→sonnet→haiku / Codex effort 降级）
- 📝 **系统提示**: `system_prompt` 参数注入系统级指令
- 📦 **大 prompt 支持**: >200KB 自动通过 stdin 传递，避免 OS ARG_MAX 限制
- 🏷️ **工具注解**: 每个工具附带 `ToolAnnotations` 元数据
- 🤝 **多模型协作**: `chain` 流水线 / `vote` 投票共识 / `debate` 辩论迭代

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

也可以只允许特定工具：`"mcp__super__codex"`、`"mcp__super__gemini"`、`"mcp__super__claude"`、`"mcp__super__broadcast"`、`"mcp__super__chain"`、`"mcp__super__vote"`、`"mcp__super__debate"`、`"mcp__super__list-models"`、`"mcp__super__status"`、`"mcp__super__usage"`。

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
| `system_prompt` | str | `""` | 系统级指令 (注入 `<system>` 标签) |
| `timeout` | float | `300` | 超时秒数 |

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
| `system_prompt` | str | `""` | 系统级指令 (注入 `<system>` 标签) |
| `timeout` | float | `300` | 超时秒数 |

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
| `system_prompt` | str | `""` | 系统级指令 (注入 `<system>` 标签) |
| `timeout` | float | `300` | 超时秒数 |

### `broadcast`

将同一 prompt 并发发送给多个 CLI，聚合返回结果。适用于对比不同 AI 的回答。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | 必填 | 任务指令 |
| `cd` | str | 必填 | 工作目录 |
| `targets` | list[str] | `None` | 目标 CLI 列表，空=全部 (`codex`, `gemini`, `claude`) |
| `model` | str | `""` | 传给所有 CLI 的模型名 (全局覆盖) |
| `models` | dict[str,str] | `None` | 按 CLI 指定模型，如 `{"gemini": "gemini-3.1-pro-preview"}` |
| `review_uncommitted` | bool | `False` | 审查未提交更改 |
| `review_base` | str | `""` | 审查相对于某分支的更改 |
| `review_commit` | str | `""` | 审查特定 commit (7-40 位 hex SHA) |
| `files` | list[str] | `None` | 文件列表模式 |
| `return_all_messages` | bool | `False` | 返回完整事件流 |
| `system_prompt` | str | `""` | 系统级指令 (注入 `<system>` 标签) |
| `timeout` | float | `300` | 超时秒数 |

### `chain`

顺序多模型流水线。每步的输出自动注入下一步（以 `<previous_output>` 标签包裹）。首个失败即停止并返回部分结果。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `steps` | list[dict] | 必填 | 步骤列表，每个 `{target, prompt, model?}` |
| `cd` | str | 必填 | 工作目录 |
| `system_prompt` | str | `""` | 系统级指令 |
| `timeout` | float | `300` | 总超时秒数 (端到端预算) |

### `vote`

并行发给多个候选模型，再由评审模型选出最佳答案。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | 必填 | 任务指令 |
| `cd` | str | 必填 | 工作目录 |
| `candidates` | list[str] | `None` | 候选 CLI，空=全部 |
| `judge` | str | `"claude"` | 评审 CLI (自动从候选中排除) |
| `model` | str | `""` | 模型名 |
| `system_prompt` | str | `""` | 系统级指令 |
| `timeout` | float | `300` | 总超时秒数 |

### `debate`

两个模型交替辩论，每轮看到对手的上一轮回答（以 `<opponent_response>` 标签包裹）。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `prompt` | str | 必填 | 辩题/任务指令 |
| `cd` | str | 必填 | 工作目录 |
| `side_a` | str | `"codex"` | 正方 CLI |
| `side_b` | str | `"claude"` | 反方 CLI |
| `rounds` | int | `3` | 辩论轮数 |
| `model` | str | `""` | 模型名 |
| `system_prompt` | str | `""` | 系统级指令 |
| `timeout` | float | `300` | 总超时秒数 |

### `list-models`

查询 OpenRouter 上三家（OpenAI、Google、Anthropic）的可用模型列表。无需 API key，结果缓存 5 分钟。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `provider` | str | `""` | 按厂商过滤: `openai`、`google`、`anthropic`，空=三家全部 |

返回的 `model_id` 字段可直接作为其他工具的 `model` 参数使用。自动过滤掉 CLI 不兼容的变体（image、customtools、gemma、:free 等）。

> **⚠️ 注意**: 数据来自 OpenRouter，**不保证所有返回的模型都能在对应 CLI 中使用**。这是一个辅助发现功能，实际可用性以各 CLI 为准。截至 2026-03，已验证可用的最新模型：
>
> | CLI | 最新可用模型 |
> |-----|-------------|
> | Gemini | `gemini-3.1-pro-preview` |
> | Codex | `gpt-5.3-codex` |
> | Claude | `claude-opus-4-6` |

### `status`

检查所有 CLI 的可用性、版本和认证状态。无参数。

### `usage`

查看累计的 token 用量和调用次数。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `reset` | bool | `False` | 读取后清零计数器 |

## 🔍 模型校验

传入 `model` 参数时，工具会先通过 OpenRouter 缓存校验模型是否存在。这同样是辅助功能——通过校验不代表 CLI 一定支持，但**未通过校验的模型大概率是拼写错误**。

- **模型存在** → 正常执行
- **模型不存在** → 秒返回错误 + 推荐相似模型名
- **短别名** (`flash`、`pro`、`sonnet`、`haiku`、`opus`) → 跳过校验，直接走 CLI
- **OpenRouter 不可达** → 静默跳过校验，不影响主流程

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

CLI 执行期间每 5 秒通过 MCP `report_progress` 发送一次心跳通知，包含已运行时间和当前状态摘要。
防止长时间任务时客户端误判超时断开连接。

## 🧪 测试

```bash
uv run pytest -v
```

## 📄 许可

Apache-2.0 License © 2026 [Babywbx](https://github.com/babywbx)
