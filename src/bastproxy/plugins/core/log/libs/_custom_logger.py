# Project: bastproxy
# Filename: plugins/core/log/libs/_custom_logger.py
#
# File Description: a plugin to change logging settings
#
# By: Bast
"""This module handles changing logging settings.

see info/logging_notes.txt for more information about logging
"""

# Standard Library
import copy
import logging
import logging.handlers
import numbers
import os
import sys
import traceback
from pathlib import Path
from typing import Any

# Third Party
# Project
from bastproxy.libs.api import API
from bastproxy.libs.logger import (
    RECORD_LOG_BUFFER,
    RecordContextFilter,
    RecordIdFormatter,
    RenderFilter,
)
from bastproxy.libs.records import (
    NetworkData,
    NetworkDataLine,
    SendDataDirectlyToClient,
)
from bastproxy.plugins.core.colors import ALLCONVERTCOLORS

from .tz import formatTime_RFC3339, formatTime_RFC3339_UTC
from .utils import get_toplevel

default_log_file = "bastproxy.log"
data_logger_log_file = "networkdata.log"

type_counts = {}


def update_type_counts(name, level):
    logger_name = get_toplevel(name)
    if isinstance(level, numbers.Number):
        level = logging.getLevelName(level).lower()  # type: ignore
    if logger_name not in type_counts:
        type_counts[logger_name] = {
            "debug": 0,
            "info": 0,
            "warning": 0,
            "error": 0,
            "critical": 0,
        }
    if level not in type_counts[logger_name]:
        type_counts[logger_name][level] = 0
    type_counts[logger_name][level] += 1


class CustomColorFormatter(logging.Formatter):
    """Logging colored formatter, adapted from https://stackoverflow.com/a/56944256/3638629."""

    error = f"\x1b[{ALLCONVERTCOLORS['@x136']}m"
    warning = f"\x1b[{ALLCONVERTCOLORS['@y']}m"
    info = f"\x1b[{ALLCONVERTCOLORS['@w']}m"
    debug = f"\x1b[{ALLCONVERTCOLORS['@x246']}m"
    critical = f"\x1b[{ALLCONVERTCOLORS['@r']}m"
    reset = "\x1b[0m"

    def __init__(self, fmt: str):
        super().__init__()
        self.fmt = fmt
        self.api = API(owner_id="plugins.core.log:CustomColorFormatter")
        self.FORMATS = {
            logging.DEBUG: self.debug + self.fmt + self.reset,
            logging.INFO: self.info + self.fmt + self.reset,
            logging.WARNING: self.warning + self.fmt + self.reset,
            logging.ERROR: self.error + self.fmt + self.reset,
            logging.CRITICAL: self.critical + self.fmt + self.reset,
        }

    def format(self, record):
        if record.name != "root":
            if "exc_info" in record.__dict__ and record.exc_info:
                # work on a copy so the other handlers still see the original record
                record = copy.copy(record)
                formatted_exc = traceback.format_exception(record.exc_info[1])
                formatted_exc_no_newline = [line.rstrip() for line in formatted_exc if line]
                record.msg = "\n".join([record.getMessage(), *formatted_exc_no_newline])
                record.args = ()
                record.exc_info = None
                record.exc_text = None
            if self.api("libs.api:api.exists")("plugins.core.log:log.level.color.get") and (
                color := self.api("plugins.core.log:log.level.color.get")(record.levelno)
            ):
                log_fmt = f"\x1b[{ALLCONVERTCOLORS[color]}m{self.fmt}{self.reset}"
            else:
                log_fmt = self.FORMATS.get(record.levelno)
        else:
            log_fmt = ""

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def _record_names(record) -> tuple[str, ...]:
    """Get the names a record was logged to."""
    return getattr(record, "log_sources", None) or (record.name,)


def _first_allowed(record, api, api_name: str):
    """Get the first name the handler allows, or None.

    If the check API does not exist yet, the first name is allowed.
    """
    names = _record_names(record)
    if not api("libs.api:api.exists")(api_name):
        return names[0]
    check = api(api_name)
    for name in names:
        if check(name, record.levelno):
            return name
    return None


def _emit_as(record, name):
    """Get a copy of the record under the name that is shown."""
    if name == record.name:
        return record
    new_record = copy.copy(record)
    new_record.name = name
    return new_record


class CustomConsoleHandler(logging.StreamHandler):
    def __init__(self, stream=sys.stdout):
        super().__init__(stream=stream)
        self.api = API(owner_id="plugins.core.log:CustomConsoleHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        # Check if quiet mode is enabled
        if self.api.quiet_mode:
            return

        for name in _record_names(record):
            update_type_counts(name, record.levelno)
        try:
            name = _first_allowed(record, self.api, "plugins.core.log:logger.console.is.enabled")
            if name is not None:
                super().emit(_emit_as(record, name))
        except Exception:
            super().emit(record)


LOG_DIR_MODE = 0o700
LOG_FILE_MODE = 0o600


def make_log_dir(path: Path) -> None:
    """Create a log directory (and missing parents) with mode 0o700.

    Only directories created by this call are changed; existing ones keep their mode.
    """
    missing = [p for p in (path, *path.parents) if not p.exists()]
    path.mkdir(parents=True, exist_ok=True, mode=LOG_DIR_MODE)
    for created in missing:
        created.chmod(LOG_DIR_MODE)


def _private_opener(path: str, flags: int) -> int:
    """Open ``path`` so a file created by the call has mode 0o600 from the start."""
    return os.open(path, flags, LOG_FILE_MODE)


class PrivateFileMixin:
    """Open log files, including rotated ones, so new files are created with mode 0o600.

    The mode is passed at creation through the ``opener`` hook, so the file never
    exists with a wider mode. An existing file keeps its mode.
    """

    def _open(self) -> Any:
        return open(
            self.baseFilename,  # type: ignore[attr-defined]
            self.mode,  # type: ignore[attr-defined]
            encoding=self.encoding,  # type: ignore[attr-defined]
            errors=self.errors,  # type: ignore[attr-defined]
            opener=_private_opener,
        )


class PrivateTimedRotatingFileHandler(PrivateFileMixin, logging.handlers.TimedRotatingFileHandler):
    """A timed rotating file handler whose files are created with mode 0o600."""


class CustomRotatingFileHandler(PrivateFileMixin, logging.handlers.TimedRotatingFileHandler):
    def __init__(
        self,
        filename,
        when="midnight",
        interval=1,
        backupCount=0,
        encoding=None,
        delay=False,
        utc=False,
        atTime=None,
    ):
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)
        self.api = API(owner_id="plugins.core.log:CustomRotatingFileHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        for name in _record_names(record):
            update_type_counts(name, record.levelno)
        try:
            name = _first_allowed(record, self.api, "plugins.core.log:logger.file.is.enabled")
            if name is not None:
                super().emit(_emit_as(record, name))
        except Exception:
            super().emit(record)


class CustomClientHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.api = API(owner_id="plugins.core.log:CustomClientHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        if self.api.startup:
            return

        if not self.api("libs.api:api.exists")("plugins.core.log:logger.client.is.enabled"):
            return

        names = _record_names(record)
        for name in names:
            update_type_counts(name, record.levelno)

        check = self.api("plugins.core.log:logger.client.is.enabled")
        shown = next((n for n in names if check(n, record.levelno)), None)
        if shown is None and record.levelno >= logging.ERROR:
            shown = names[0]
        if shown is None:
            return

        formatted_message = self.format(_emit_as(record, shown))
        if self.api("libs.api:api.exists")("plugins.core.log:log.level.color.get"):
            color = self.api("plugins.core.log:log.level.color.get")(record.levelno)
        else:
            color = None
        new_message = NetworkData(owner_id="plugins.core.log:CustomClientHandler:emit")
        for line in formatted_message.splitlines():
            new_message.append(NetworkDataLine(line, color=color or ""))
        SendDataDirectlyToClient(new_message)()


def reset_logging():
    """Reset logging handlers and filters."""
    rootlogger = logging.getLogger()
    while rootlogger.hasHandlers():
        try:
            rootlogger.handlers[0].acquire()
            rootlogger.handlers[0].flush()
            rootlogger.handlers[0].close()
        except (OSError, ValueError):
            pass
        finally:
            rootlogger.handlers[0].release()
        rootlogger.removeHandler(rootlogger.handlers[0])
    list(map(rootlogger.removeFilter, rootlogger.filters[:]))


def setup_loggers(log_level: int):
    from bastproxy.libs.api import API

    reset_logging()
    rootlogger = logging.getLogger()
    rootlogger.setLevel(logging.DEBUG)

    default_log_file_path = API.BASEDATALOGPATH / default_log_file
    make_log_dir(API.BASEDATALOGPATH / "networkdata")
    data_logger_log_file_path = API.BASEDATALOGPATH / "networkdata" / data_logger_log_file

    file_handler = CustomRotatingFileHandler(filename=default_log_file_path, when="midnight")
    file_handler.formatter = RecordIdFormatter(
        "%(asctime)s : %(levelname)-9s - %(name)-22s - %(record_id)s - %(message)s"
    )

    console_handler = CustomConsoleHandler()
    console_handler.formatter = CustomColorFormatter(
        "%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    client_handler = CustomClientHandler()
    client_handler.formatter = CustomColorFormatter(
        "%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    # the buffer is a module-level instance, so do not stack filters on a second setup
    RECORD_LOG_BUFFER.filters.clear()
    for handler in (file_handler, console_handler, client_handler, RECORD_LOG_BUFFER):
        handler.addFilter(RenderFilter())
        handler.addFilter(RecordContextFilter())

    # add the handler to the root logger
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(console_handler)
    logging.getLogger().addHandler(client_handler)
    logging.getLogger().addHandler(RECORD_LOG_BUFFER)

    if API.LOG_IN_UTC_TZ:
        logging.Formatter.formatTime = formatTime_RFC3339_UTC
    else:
        logging.Formatter.formatTime = formatTime_RFC3339

    # This logger is for any network data from both the mud and the client to facilitate
    # debugging. It is not intended to be used for general logging. It will not use the same
    # log settings as the root logger. It will log to a file and not to the console.
    # logging network data from the mud will use data.mud
    # logging network data to/from the client will use data.<client_uuid>
    data_logger = logging.getLogger("data")
    data_logger.setLevel(logging.INFO)
    data_logger_file_handler = PrivateTimedRotatingFileHandler(
        data_logger_log_file_path, when="midnight"
    )
    data_logger_file_handler.formatter = logging.Formatter(
        "%(asctime)s : %(name)-11s - %(message)s"
    )
    data_logger.addHandler(data_logger_file_handler)
    data_logger.propagate = False
