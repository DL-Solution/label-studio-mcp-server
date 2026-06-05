import argparse
import os
import threading

from label_studio_mcp.mcp_server import mcp


def _str_to_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _warm_up_client() -> None:
    """Build the Label Studio client off the request path, in the background.

    The SDK import + client construction can take minutes on first use (cold
    bytecode compilation, AV scanning of a large package on Windows). It is
    deliberately deferred out of module import so the MCP ``initialize``
    handshake stays fast. But if it runs inside the first tool call, that call
    can exceed the client's per-request timeout (~4 min in Claude Desktop) — the
    work still completes server-side, so a user retry creates a duplicate
    project. Warming the cached, idempotent ``get_ls()`` here moves the cost
    into a background thread so the first real tool call finds it ready.
    """
    # Imported lazily so this module stays cheap to import.
    from label_studio_mcp.mcp_env import get_ls

    try:
        get_ls()
    except Exception:
        # get_ls() already logs and caches failures; the next tool call will
        # surface a proper error. Never let warm-up crash the server.
        pass


# Ensures the warm-up runs exactly once even if the trigger fires more than once.
_warm_up_started = threading.Event()


def _start_warm_up() -> None:
    """Kick off the background warm-up thread, at most once."""
    if _warm_up_started.is_set():
        return
    _warm_up_started.set()
    threading.Thread(target=_warm_up_client, name="ls-warmup", daemon=True).start()


def _arm_warm_up_after_handshake() -> bool:
    """Defer warm-up until the client signals it has finished initializing.

    Running the heavy SDK import concurrently with the ``initialize`` handshake
    makes that one handshake slow (observed ~14 s on Windows): the request that
    negotiates capabilities contends with the import for Python's interpreter/
    import machinery, while later calls like ``tools/list`` are unaffected.

    The client sends ``notifications/initialized`` immediately *after* it
    receives the ``initialize`` response, so hooking that notification starts
    the warm-up the instant the handshake is done — early enough to be ready
    before the first (much later) tool call, but late enough not to slow the
    handshake. Returns False if the server internals aren't shaped as expected,
    so the caller can fall back to starting the warm-up immediately.
    """
    try:
        from mcp import types

        low_level = mcp._mcp_server
        handlers = low_level.notification_handlers
    except Exception:
        return False

    previous = handlers.get(types.InitializedNotification)

    async def _on_initialized(notification):
        _start_warm_up()
        if previous is not None:  # pragma: no cover - defensive chaining
            await previous(notification)

    handlers[types.InitializedNotification] = _on_initialized
    return True


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

    # Build the Label Studio client in the background so the heavy SDK import is
    # paid off the request path, not on the first tool call. For stdio (Claude
    # Desktop et al.) defer it until the client finishes the handshake, so the
    # import can't slow down ``initialize``; if that hook can't be installed,
    # fall back to starting immediately. HTTP transports may serve many clients
    # and have no single handshake to wait on, so warm up right away there.
    deferred = args.transport == "stdio" and _arm_warm_up_after_handshake()
    if not deferred:
        _start_warm_up()

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
