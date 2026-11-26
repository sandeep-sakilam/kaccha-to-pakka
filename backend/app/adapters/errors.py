class AdapterError(Exception):
    """An outside service failed (timeout, bad response, outage). Callers fail closed."""


class NotConfiguredError(AdapterError):
    """A real adapter was selected but its keys are missing."""
