import argparse
import os

from label_studio_mcp.mcp_server import mcp


def _str_to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def main():
    """Entry point for the Label Studio MCP server.

    Supports multiple MCP transports so the server can be used both as a local
    subprocess (stdio, the default used by Claude Desktop / Cursor / VS Code)
    and as a network service over HTTP (streamable-http or the legacy sse).

    Configuration can be provided via CLI flags or environment variables:
        --transport / MCP_TRANSPORT   stdio | streamable-http | sse  (default: stdio)
        --host      / MCP_HOST        Bind host for HTTP transports     (default: 127.0.0.1)
        --port      / MCP_PORT        Bind port for HTTP transports     (default: 8000)
        --path      / MCP_PATH        URL path for the HTTP endpoint    (default: /mcp)
    """
    parser = argparse.ArgumentParser(description="Label Studio MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="MCP transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "127.0.0.1"),
        help="Host to bind when using an HTTP transport (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8000")),
        help="Port to bind when using an HTTP transport (default: 8000).",
    )
    parser.add_argument(
        "--path",
        default=os.getenv("MCP_PATH", "/mcp"),
        help="URL path for the streamable-http endpoint (default: /mcp).",
    )
    args = parser.parse_args()

    if args.transport in ("streamable-http", "sse"):
        # Apply network settings used by the HTTP transports.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        if args.transport == "streamable-http":
            mcp.settings.streamable_http_path = args.path
        else:
            mcp.settings.sse_path = args.path

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
