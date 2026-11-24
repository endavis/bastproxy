# Project: bastproxy
# Filename: libs/gcfreeze.py
#
# File Description: freeze long-lived startup objects out of full garbage collections
#
# By: Bast
"""Freeze the long-lived startup heap out of full garbage collections (#758).

Once every plugin has loaded, the objects they created live until exit. A full
(generation 2) collection still walks all of them and stalls the event loop.
``gc.freeze()`` moves them to a permanent generation that collections skip.

The trade-off is reference cycles. A plugin instance is full of cycles (bound
method callbacks, ``self.api``, registrations), and a frozen cycle is never
reclaimed, so unloading or reloading a plugin would leak its objects. The
plugin manager commands therefore call :func:`refreeze` after a load, unload or
reload: ``gc.unfreeze()``, a full ``gc.collect()``, then ``gc.freeze()`` again.
An old object that is still referenced at that point is frozen again and is
released at the next re-freeze.

``--no-gc-freeze`` skips the startup freeze; :func:`refreeze` is then a no-op.
"""

# Standard Library
import gc
import time

# Project
from bastproxy.libs.logger import get_logger

logger = get_logger(__name__)

_frozen: bool = False


def _log(action: str, reason: str, collected: int, started: float) -> None:
    """Log one INFO line describing a freeze or re-freeze."""
    logger.info(
        "gc %s (%s): frozen=%d collected=%d elapsed=%.1fms",
        action,
        reason,
        gc.get_freeze_count(),
        collected,
        (time.perf_counter() - started) * 1000,
    )


def freeze_long_lived_objects(reason: str) -> int:
    """Collect, then freeze every tracked object.

    Args:
        reason: why the freeze runs, for the log line.

    Returns:
        the number of frozen objects.

    """
    global _frozen
    started = time.perf_counter()
    collected = gc.collect()
    gc.freeze()
    _frozen = True
    _log("freeze", reason, collected, started)
    return gc.get_freeze_count()


def refreeze(reason: str) -> int | None:
    """Unfreeze, collect and freeze again so dropped plugin cycles are reclaimed.

    Args:
        reason: why the re-freeze runs, for the log line.

    Returns:
        the number of frozen objects, or None when nothing was frozen.

    """
    if not _frozen:
        return None
    started = time.perf_counter()
    gc.unfreeze()
    collected = gc.collect()
    gc.freeze()
    _log("refreeze", reason, collected, started)
    return gc.get_freeze_count()


def is_frozen() -> bool:
    """Return True once the startup freeze has run."""
    return _frozen
