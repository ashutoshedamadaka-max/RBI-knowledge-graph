"""Safe diagnostics for failures that may contain provider credentials."""

import logging


def log_failure(logger: logging.Logger, event: str, error: Exception, *, level: int = logging.WARNING) -> None:
    """Record type and HTTP status without exception messages, headers, or tracebacks."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if not isinstance(status, int):
        status = None
    logger.log(level, "%s error_type=%s status_code=%s", event, type(error).__name__, status)
