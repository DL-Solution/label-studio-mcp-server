"""Core MCP server object and the tool-registration plumbing.

This module owns the single ``FastMCP`` instance and the decorators every tool
module uses to register itself. The Label Studio client is created lazily on the
first tool/resource call (see ``require_ls_connection``); the heavy SDK import is
kept out of module import so the MCP ``initialize`` handshake stays fast and
clients like Claude Desktop don't time out on startup.
"""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
import functools

from .mcp_env import get_ls
from .errors import _format_tool_error

# Initialize FastMCP server
mcp = FastMCP("label-studio-mcp")


# --- Tool registration helpers with MCP annotations ---
# MCP clients (e.g. Claude) use these annotation hints to group tools in their
# permission UI into "Read-only", "Write/delete" and "Other" categories, and to
# decide how cautious to be before invoking a tool. Use the wrapper that matches
# a tool's behaviour instead of the bare ``@mcp.tool()``.

def read_tool(**kwargs):
    """Register a read-only tool (no side effects). -> "Read-only tools"."""
    return mcp.tool(annotations=ToolAnnotations(readOnlyHint=True), **kwargs)


def write_tool(**kwargs):
    """Register a mutating, non-destructive tool. -> "Write/delete tools"."""
    return mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
        **kwargs,
    )


def destructive_tool(**kwargs):
    """Register a destructive tool (deletes/irreversible). -> "Write/delete tools"."""
    return mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
        **kwargs,
    )


def require_ls_connection(func):
    """Build (or reuse) the Label Studio client and expose it to the tool body.

    The wrapped tool/resource bodies reference a module-global ``ls`` directly.
    Each tool module defines its own ``ls = None``; this decorator populates that
    name in the wrapped function's own module namespace before the body runs, so
    tools split across modules all see a ready client. Errors raised by the body
    are rendered as a compact JSON string rather than propagating to the client.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        client = get_ls()
        if client is None:
            # Make the error message more informative
            return ("Error: Label Studio client not available. "
                    "Please check server logs for initialization errors "
                    "(e.g., missing 'LABEL_STUDIO_API_KEY', invalid key, or connection issue with 'LABEL_STUDIO_URL').")
        # Expose the client as the ``ls`` global of the module that defines the
        # wrapped function, so the tool body can keep referencing ``ls`` directly.
        func.__globals__["ls"] = client
        try:
            # Execute the wrapped function (tool or resource handler)
            return func(*args, **kwargs)
        except Exception as e:
            # Return a compact, JSON-serializable error (never a full HTML page).
            return _format_tool_error(func.__name__, e)
    return wrapper
