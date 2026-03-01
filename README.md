# 🚀 SuperAI MCP

将 **Gemini CLI** 和 **Codex CLI** 包装为 MCP 工具，让 Claude Code 能调用其他 AI CLI 进行 code review 和编码任务。

## ✨ 特性

- 🔧 **双工具**: `mcp__super__codex` + `mcp__super__gemini`
- 📋 **三种模式**: prompt 转发 / git diff review / 文件列表 review
- 🔄 **会话续接**: 通过 `session_id` 延续上下文
- 🎯 **模型选择**: 支持指定模型和推理深度
- ⚡ **纯异步**: 基于 `asyncio.create_subprocess_exec`，无线程
- 🔒 **安全**: 路径遍历防护、git ref 校验、无 shell 注入

## 📦 安装

```bash
# 需要 Python >= 3.12 和 uv
uv sync
```

## 🔌 配置 Claude Code

在 `.mcp.json` 中添加:

```json
{
  "mcpServers": {
    "super": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/SuperAI-MCP", "superai-mcp"]
    }
  }
}
```

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
| `files` | list[str] | `None` | 文件列表模式 |
| `return_all_messages` | bool | `False` | 返回完整事件流 |

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
| `files` | list[str] | `None` | 文件列表模式 |
| `return_all_messages` | bool | `False` | 返回完整事件流 |

## 🚦 使用模式

```
1️⃣ 默认模式 — prompt 直接转发给 CLI
2️⃣ Review 模式 — 自动获取 git diff 注入 prompt
3️⃣ 文件模式 — 读取文件内容注入 prompt
```

## 🧪 测试

```bash
uv run pytest -v
```

## 📄 许可

MIT
