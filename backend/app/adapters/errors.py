class AdapterError(Exception):
    """An outside service failed (timeout, bad response, outage). Callers fail closed."""


class NotConfiguredError(AdapterError):
    """A real adapter was selected but its keys are missing."""


PLACEHOLDER_KEYS = {"proxy", "injected", "placeholder", "from-proxy"}


def is_placeholder(key: str) -> bool:
    """A key value like "proxy" means the network proxy adds the real key to each request, so
    the process never sees it. The real adapter is used and sends the placeholder header."""
    return key.strip().lower() in PLACEHOLDER_KEYS
