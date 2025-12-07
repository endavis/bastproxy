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
import logging
import logging.handlers
import numbers
import sys
import traceback

# Third Party
# Project
from bastproxy.libs.api import API
from bastproxy.libs.records import (
    LogRecord,
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
        self.api = API(owner_id=f"{__name__}:CustomColorFormatter")
        self.FORMATS = {
            logging.DEBUG: self.debug + self.fmt + self.reset,
            logging.INFO: self.info + self.fmt + self.reset,
            logging.WARNING: self.warning + self.fmt + self.reset,
            logging.ERROR: self.error + self.fmt + self.reset,
            logging.CRITICAL: self.critical + self.fmt + self.reset,
        }

    def format(self, record: logging.LogRecord):
        if record.name != "root":
            if "exc_info" in record.__dict__ and record.exc_info:
                formatted_exc = traceback.format_exception(record.exc_info[1])
                formatted_exc_no_newline = [
                    line.rstrip() for line in formatted_exc if line
                ]
                if isinstance(record.msg, LogRecord):
                    record.msg.extend(formatted_exc_no_newline)
                    record.msg.addupdate("Modify", "add traceback")
                    record.msg.format()
                elif isinstance(record.msg, str):
                    record.msg += "\n".join(formatted_exc_no_newline)
                record.exc_info = None
                record.exc_text = None
            if self.api("libs.api:has")("plugins.core.log:get.level.color") and (
                color := self.api("plugins.core.log:get.level.color")(record.levelno)
            ):
                log_fmt = f"\x1b[{ALLCONVERTCOLORS[color]}m{self.fmt}{self.reset}"
            else:
                log_fmt = self.FORMATS.get(record.levelno)
        else:
            log_fmt = ""

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class CustomConsoleHandler(logging.StreamHandler):
    def __init__(self, stream=sys.stdout):
        super().__init__(stream=stream)
        self.api = API(owner_id=f"{__name__}:CustomConsoleHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        # Check if quiet mode is enabled
        if self.api.quiet_mode:
            return

        update_type_counts(record.name, record.levelno)
        try:
            canlog = bool(
                not self.api("libs.api:has")("plugins.core.log:can.log.to.console")
                or self.api("plugins.core.log:can.log.to.console")(
                    record.name, record.levelno
                )
            )
            if isinstance(record.msg, LogRecord):
                if canlog and not record.msg.wasemitted["console"]:
                    record.msg.wasemitted["console"] = True
                    super().emit(record)
            elif canlog:
                super().emit(record)
        except Exception:
            super().emit(record)


class CustomRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
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
        super().__init__(
            filename, when, interval, backupCount, encoding, delay, utc, atTime
        )
        self.api = API(owner_id=f"{__name__}:CustomRotatingFileHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        update_type_counts(record.name, record.levelno)
        try:
            canlog = bool(
                not self.api("libs.api:has")("plugins.core.log:can.log.to.file")
                or self.api("plugins.core.log:can.log.to.file")(
                    record.name, record.levelno
                )
            )
            if isinstance(record.msg, LogRecord):
                if canlog and not record.msg.wasemitted["file"]:
                    record.msg.wasemitted["file"] = True
                    super().emit(record)
            elif canlog:
                super().emit(record)
        except Exception:
            super().emit(record)


class CustomClientHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.api = API(owner_id=f"{__name__}:CustomClientHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record):
        if self.api.startup:
            return

        if not self.api("libs.api:has")("plugins.core.log:can.log.to.client"):
            return

        update_type_counts(record.name, record.levelno)

        canlog = self.api("plugins.core.log:can.log.to.client")(
            record.name, record.levelno
        )
        if canlog or record.levelno >= logging.ERROR:
            formatted_message = self.format(record)
            if isinstance(record.msg, LogRecord):
                if self.api("libs.api:has")("plugins.core.log:get.level.color"):
                    color = self.api("plugins.core.log:get.level.color")(record.levelno)
                else:
                    color = None
                if not record.msg.wasemitted["client"]:
                    new_message = NetworkData(
                        owner_id=f"{__name__}:CustomClientHandler:emit"
                    )
                    [
                        new_message.append(NetworkDataLine(line, color=color or ""))
                        for line in formatted_message.splitlines()
                    ]
                    record.msg.wasemitted["client"] = True
                    SendDataDirectlyToClient(new_message)()
            else:
                new_message = NetworkData(
                    formatted_message.splitlines(),
                    owner_id=f"{__name__}:CustomClientHandler:emit",
                )
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
    rootlogger.setLevel(log_level)

    default_log_file_path = API.BASEDATALOGPATH / default_log_file
    (API.BASEDATALOGPATH / "networkdata").mkdir(parents=True, exist_ok=True)
    data_logger_log_file_path = (
        API.BASEDATALOGPATH / "networkdata" / data_logger_log_file
    )

    file_handler = CustomRotatingFileHandler(
        filename=default_log_file_path, when="midnight"
    )
    file_handler.formatter = logging.Formatter(
        "%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    console_handler = CustomConsoleHandler()
    console_handler.formatter = CustomColorFormatter(
        "%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    client_handler = CustomClientHandler()
    client_handler.formatter = CustomColorFormatter(
        "%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"
    )

    # add the handler to the root logger
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(console_handler)
    logging.getLogger().addHandler(client_handler)

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
    data_logger_file_handler = logging.handlers.TimedRotatingFileHandler(
        data_logger_log_file_path, when="midnight"
    )
    data_logger_file_handler.formatter = logging.Formatter(
        "%(asctime)s : %(name)-11s - %(message)s"
    )
    data_logger.addHandler(data_logger_file_handler)
    data_logger.propagate = False
