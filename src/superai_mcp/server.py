"""FastMCP server with tool registration."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("super")


def serve() -> None:
    """Start the MCP server."""
    mcp.run()
