# Project: bastproxy
# Filename: libs/logger.py
#
# File Description: thin helpers over the standard library logging module
#
# By: Bast
"""Thin helpers over the standard library logging module.

Bastproxy code logs through standard-library loggers. This module adds:

- ``get_logger``: a logger with an explicit level taken from the per-name thresholds,
  so a disabled level is dropped before the message is built.
- ``set_threshold``: sets the threshold for a logger name (used by the log plugin).
- ``log_to``: one record for a message that goes to more than one source.
- ``RenderFilter`` and ``RecordContextFilter``: filters for the root handlers.
- ``RecordIdFormatter``: the file log formatter, showing ``-`` when there is no record id.
- ``RecordLogBuffer``, ``get_record_logs``: the last log lines written for each record.

Use lazy ``%`` arguments so the message is only built when the level is enabled::

    logger = get_logger(__name__)
    logger.debug("started %s with %s", name, args)

This module uses the standard library only so ``libs`` never imports a plugin.
"""

# Standard Library
import copy
import logging
from collections import OrderedDict, deque
from typing import Any

LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

# toplevel logger name -> level. Missing names use INFO.
_thresholds: dict[str, int] = {}


def get_toplevel(logger_name: str) -> str:
    """Get the toplevel logger from a name (the part before the first ``:``)."""
    return logger_name.split(":")[0] if ":" in logger_name else logger_name


def get_logger(name: str) -> logging.Logger:
    """Get a logger with an explicit level from the thresholds.

    The explicit level avoids dotted-hierarchy inheritance and handles ``:`` suffixed
    owner IDs. The handlers still make the routing decision.
    """
    logger = logging.getLogger(name)
    level = _thresholds.get(get_toplevel(name), logging.INFO)
    if logger.level != level:
        logger.setLevel(level)
    return logger


def set_threshold(name: str, level: int | None) -> None:
    """Set the threshold for a logger name.

    Updates the logger and every existing logger with the same toplevel name.
    ``None`` resets the threshold to INFO.
    """
    top = get_toplevel(name)
    if level is None:
        _thresholds.pop(top, None)
        newlevel = logging.INFO
    else:
        _thresholds[top] = level
        newlevel = level
    logging.getLogger(name).setLevel(newlevel)
    for existing_name, existing in list(logging.root.manager.loggerDict.items()):
        if isinstance(existing, logging.Logger) and get_toplevel(existing_name) == top:
            existing.setLevel(newlevel)


def log_to(
    sources: Any,
    level: int,
    msg: object,
    *args: object,
    exc_info: Any = None,
    stack_info: bool = False,
) -> None:
    """Log one message to several sources.

    Makes one call on the first source whose logger is enabled for the level and
    returns at once if there is none. The handlers route the record using the
    ``log_sources`` attribute.
    """
    names = tuple(s for s in sources if s)
    for name in names:
        logger = get_logger(name)
        if logger.isEnabledFor(level):
            logger.log(
                level,
                msg,
                *args,
                extra={"log_sources": names},
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=2,
            )
            return


class RenderFilter(logging.Filter):
    """Render the message once: split it into lines and drop ``\\r``."""

    def filter(self, record: Any) -> bool:
        """Render the record message, once per record."""
        if getattr(record, "_bp_rendered", False):
            return True
        try:
            msg = record.msg
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", errors="replace")
                record.msg = msg
            text = record.getMessage()
        except Exception:
            text = str(record.msg)
        record.msg = "\n".join(text.splitlines())
        record.args = ()
        record._bp_rendered = True
        return True


class RecordContextFilter(logging.Filter):
    """Set ``record_id`` to the uuid of the active record, if there is one."""

    def filter(self, record: Any) -> bool:
        """Add the record_id attribute."""
        if getattr(record, "record_id", None):
            return True
        record_id = None
        try:
            from bastproxy.libs.records import RMANAGER

            latest = RMANAGER.get_latest_record()
            if latest is not None:
                record_id = getattr(latest, "uuid", None)
        except Exception:
            record_id = None
        record.record_id = record_id
        return True


class RecordIdFormatter(logging.Formatter):
    """Format a log record, showing ``-`` for a missing ``record_id``.

    The record keeps its ``None`` (a copy is formatted) so the buffer's check stays correct.
    """

    def format(self, record: Any) -> str:
        """Format a copy of the record with a displayable record_id."""
        if getattr(record, "record_id", None) is None:
            record = copy.copy(record)
            record.record_id = "-"
        return super().format(record)


MAX_LINES_PER_RECORD = 50
MAX_RECORDS = 2000


class RecordLogBuffer(logging.Handler):
    """Keep the last formatted log lines written for each record.

    Bounded: ``MAX_LINES_PER_RECORD`` lines for each record id, ``MAX_RECORDS`` record ids
    (the oldest record id is evicted). Records with no ``record_id`` are ignored. Access is
    guarded by the handler's lock.
    """

    def __init__(
        self,
        max_lines: int = MAX_LINES_PER_RECORD,
        max_records: int = MAX_RECORDS,
    ) -> None:
        super().__init__(level=logging.DEBUG)
        self.max_lines = max_lines
        self.max_records = max_records
        self.formatter = logging.Formatter(
            "%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"
        )
        self._lines: OrderedDict[str, deque[str]] = OrderedDict()

    def emit(self, record: Any) -> None:
        """Store the formatted line under the record's record_id."""
        record_id = getattr(record, "record_id", None)
        if not record_id:
            return
        try:
            line = self.format(record)
        except Exception:
            self.handleError(record)
            return
        lines = self._lines.get(record_id)
        if lines is None:
            lines = deque(maxlen=self.max_lines)
            self._lines[record_id] = lines
            while len(self._lines) > self.max_records:
                self._lines.popitem(last=False)
        lines.append(line)

    def get(self, record_id: str) -> list[str]:
        """Return a copy of the lines stored for a record id."""
        self.acquire()
        try:
            return list(self._lines.get(record_id, ()))
        finally:
            self.release()

    def clear(self) -> None:
        """Drop everything stored."""
        self.acquire()
        try:
            self._lines.clear()
        finally:
            self.release()


RECORD_LOG_BUFFER = RecordLogBuffer()


def get_record_logs(record_id: str) -> list[str]:
    """Return a copy of the log lines written while a record was the active record."""
    return RECORD_LOG_BUFFER.get(record_id)


def clear_record_logs() -> None:
    """Empty the buffer (for tests)."""
    RECORD_LOG_BUFFER.clear()
