"""The time used for regulatory state: when a source was checked, ingested or approved.

Production reads the system clock. The historical replay sets a simulated clock so
that monitoring behaves as it would have on a past date. Log and report timestamps
deliberately keep using real time.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

_now: Callable[[], datetime] = lambda: datetime.now(UTC)


def now() -> datetime:
    return _now()


@contextmanager
def simulated(clock: Callable[[], datetime]) -> Iterator[None]:
    """Use another clock inside this block; restore the previous one afterwards."""
    global _now
    previous, _now = _now, clock
    try:
        yield
    finally:
        _now = previous
