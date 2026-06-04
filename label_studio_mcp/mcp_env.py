import os
import sys
import httpx
from label_studio_sdk.client import LabelStudio


def _log(message: str) -> None:
    """Emit diagnostics to stderr.

    For the stdio transport, stdout is the JSON-RPC channel, so any logging must
    go to stderr to avoid corrupting the protocol stream.
    """
    print(message, file=sys.stderr)

LABEL_STUDIO_URL = os.getenv("LABEL_STUDIO_URL", "http://localhost:8080")
LABEL_STUDIO_API_KEY = os.getenv("LABEL_STUDIO_API_KEY")

# Optional TLS configuration. Useful when Label Studio is served over HTTPS with a
# certificate issued by an internal/corporate CA (e.g. an Active Directory CA such
# as internal.example) that isn't in the default trust store.
#   LABEL_STUDIO_CA_BUNDLE  - path to a PEM file containing the internal CA (chain)
#                             to trust for the Label Studio HTTPS certificate.
#   LABEL_STUDIO_VERIFY_SSL - set to "false" to disable certificate verification
#                             entirely (insecure; only for trusted internal networks
#                             or testing). Defaults to enabled.
LABEL_STUDIO_CA_BUNDLE = os.getenv("LABEL_STUDIO_CA_BUNDLE") or None
LABEL_STUDIO_VERIFY_SSL = os.getenv("LABEL_STUDIO_VERIFY_SSL", "true").strip().lower() not in {
    "0", "false", "no", "off",
}


def _build_httpx_client():
    """Return a custom httpx.Client only when non-default TLS settings are needed.

    Returns None when the defaults are fine, so the SDK uses its own client.
    """
    if not LABEL_STUDIO_VERIFY_SSL:
        return httpx.Client(verify=False)
    if LABEL_STUDIO_CA_BUNDLE:
        return httpx.Client(verify=LABEL_STUDIO_CA_BUNDLE)
    return None


ls = None
if LABEL_STUDIO_API_KEY:
    try:
        client_kwargs = {"base_url": LABEL_STUDIO_URL, "api_key": LABEL_STUDIO_API_KEY}
        httpx_client = _build_httpx_client()
        if httpx_client is not None:
            client_kwargs["httpx_client"] = httpx_client

        ls = LabelStudio(**client_kwargs)

        if not LABEL_STUDIO_VERIFY_SSL:
            tls_note = " (TLS verification DISABLED)"
        elif LABEL_STUDIO_CA_BUNDLE:
            tls_note = f" (trusting CA bundle: {LABEL_STUDIO_CA_BUNDLE})"
        else:
            tls_note = ""
        _log(f"Connected to Label Studio at {LABEL_STUDIO_URL}{tls_note}")
    except Exception as e:
        _log(f"Error initializing Label Studio client: {e}")
else:
    _log("LABEL_STUDIO_API_KEY not set; Label Studio client unavailable.")
