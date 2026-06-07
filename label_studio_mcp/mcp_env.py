import os
import sys
import threading


def _log(message: str) -> None:
    """Emit diagnostics to stderr.

    For the stdio transport, stdout is the JSON-RPC channel, so any logging must
    go to stderr to avoid corrupting the protocol stream.
    """
    print(message, file=sys.stderr)

LABEL_STUDIO_URL = os.getenv("LABEL_STUDIO_URL", "http://localhost:8080")
LABEL_STUDIO_API_KEY = os.getenv("LABEL_STUDIO_API_KEY")

# Optional TLS configuration. Useful when Label Studio is served over HTTPS with a
# certificate issued by an internal/corporate CA (e.g. an Active Directory CA)
# that isn't in the default trust store.
#   LABEL_STUDIO_CA_BUNDLE  - path to a PEM file containing the internal CA (chain)
#                             to trust for the Label Studio HTTPS certificate.
#   LABEL_STUDIO_VERIFY_SSL - set to "false" to disable certificate verification
#                             entirely (insecure; only for trusted internal networks
#                             or testing). Defaults to enabled.
LABEL_STUDIO_CA_BUNDLE = os.getenv("LABEL_STUDIO_CA_BUNDLE") or None
LABEL_STUDIO_VERIFY_SSL = os.getenv("LABEL_STUDIO_VERIFY_SSL", "true").strip().lower() not in {
    "0", "false", "no", "off",
}

# Optional OpenRouter configuration for LLM-assisted labeling (see
# tools/llm_labeling.py). When set, a selected model produces the labeling.
#   OPENROUTER_API_KEY  - OpenRouter access token (https://openrouter.ai/keys).
#   OPENROUTER_MODEL    - default model id, e.g. "openai/gpt-4o-mini". Overridable
#                         per tool call.
#   OPENROUTER_BASE_URL - API base URL (rarely changed).
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or None
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL") or "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = (os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")


def _build_httpx_client():
    """Return a custom httpx.Client only when non-default TLS settings are needed.

    Returns None when the defaults are fine, so the SDK uses its own client.
    httpx is imported here (not at module load) to keep startup imports minimal.
    """
    import httpx

    if not LABEL_STUDIO_VERIFY_SSL:
        return httpx.Client(verify=False)
    if LABEL_STUDIO_CA_BUNDLE:
        return httpx.Client(verify=LABEL_STUDIO_CA_BUNDLE)
    return None


# Lazily-created Label Studio client cache.
#   _UNSET  -> not initialized yet (first get_ls() call will build it)
#   None    -> initialization was attempted but the client is unavailable
_UNSET = object()
_ls_cache = _UNSET

# Guards client construction so the background warm-up thread and a concurrent
# first tool call build the (heavy) SDK client exactly once.
_ls_lock = threading.Lock()


def get_ls():
    """Return the Label Studio client, building it on first use (lazy, cached).

    Importing the (heavy) Label Studio SDK and constructing the client is
    deferred out of module import. This keeps the MCP ``initialize`` handshake
    fast so clients like Claude Desktop don't time out waiting for the server to
    start. Subsequent calls return the cached client, or ``None`` if it could
    not be created (e.g. missing API key).
    """
    global _ls_cache
    # Fast path: already built (or already failed). No lock needed for a plain
    # reference read.
    if _ls_cache is not _UNSET:
        return _ls_cache

    with _ls_lock:
        # Re-check inside the lock: another thread may have built it while we
        # waited.
        if _ls_cache is not _UNSET:
            return _ls_cache
        return _build_ls()


def _build_ls():
    """Construct and cache the client. Caller must hold ``_ls_lock``."""
    global _ls_cache

    if not LABEL_STUDIO_API_KEY:
        _log("LABEL_STUDIO_API_KEY not set; Label Studio client unavailable.")
        _ls_cache = None
        return _ls_cache

    try:
        from label_studio_sdk.client import LabelStudio

        client_kwargs = {"base_url": LABEL_STUDIO_URL, "api_key": LABEL_STUDIO_API_KEY}
        httpx_client = _build_httpx_client()
        if httpx_client is not None:
            client_kwargs["httpx_client"] = httpx_client

        _ls_cache = LabelStudio(**client_kwargs)

        if not LABEL_STUDIO_VERIFY_SSL:
            tls_note = " (TLS verification DISABLED)"
        elif LABEL_STUDIO_CA_BUNDLE:
            tls_note = f" (trusting CA bundle: {LABEL_STUDIO_CA_BUNDLE})"
        else:
            tls_note = ""
        _log(f"Connected to Label Studio at {LABEL_STUDIO_URL}{tls_note}")
    except Exception as e:
        _log(f"Error initializing Label Studio client: {e}")
        _ls_cache = None

    return _ls_cache
