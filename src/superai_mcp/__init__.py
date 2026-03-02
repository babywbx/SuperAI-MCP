"""SuperAI MCP — Gemini CLI, Codex CLI & Claude CLI as MCP tools."""

__version__ = "0.1.0"


def main() -> None:
    """Entry point for `superai-mcp` command."""
    from superai_mcp.server import serve

    serve()
