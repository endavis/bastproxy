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
import asyncio
import copy
import datetime
import logging
import logging.handlers
import numbers
import os
import re
import sys
import threading
import time
import traceback
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO, cast

# Third Party
# Project
from bastproxy.libs.api import API
from bastproxy.libs.logger import (
    ERROR_BUFFER,
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

from .tz import format_time_rfc3339, format_time_rfc3339_utc
from .utils import get_toplevel

default_log_file = "bastproxy.log"
data_logger_log_file = "networkdata.log"

type_counts: dict[str, dict[str, int]] = {}


def update_type_counts(name: str, level: int | str) -> None:
    logger_name = get_toplevel(name)
    if isinstance(level, numbers.Number):
        level = logging.getLevelName(level).lower()
    if logger_name not in type_counts:
        type_counts[logger_name] = {
            "debug": 0,
            "info": 0,
            "warning": 0,
            "error": 0,
            "critical": 0,
        }
    level_name = cast(str, level)
    if level_name not in type_counts[logger_name]:
        type_counts[logger_name][level_name] = 0
    type_counts[logger_name][level_name] += 1


class CustomColorFormatter(logging.Formatter):
    """Logging colored formatter, adapted from https://stackoverflow.com/a/56944256/3638629."""

    error = f"\x1b[{ALLCONVERTCOLORS['@x136']}m"
    warning = f"\x1b[{ALLCONVERTCOLORS['@y']}m"
    info = f"\x1b[{ALLCONVERTCOLORS['@w']}m"
    debug = f"\x1b[{ALLCONVERTCOLORS['@x246']}m"
    critical = f"\x1b[{ALLCONVERTCOLORS['@r']}m"
    reset = "\x1b[0m"

    def __init__(self, fmt: str) -> None:
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

    def format(self, record: logging.LogRecord) -> str:
        log_fmt: str | None
        if record.name != "root":
            exc_info = record.exc_info
            if "exc_info" in record.__dict__ and exc_info:
                # work on a copy so the other handlers still see the original record
                record = copy.copy(record)
                formatted_exc = traceback.format_exception(exc_info[1])
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


def _record_names(record: logging.LogRecord) -> tuple[str, ...]:
    """Get the names a record was logged to."""
    return getattr(record, "log_sources", None) or (record.name,)


def _first_allowed(record: logging.LogRecord, api: API, api_name: str) -> str | None:
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


def _emit_as(record: logging.LogRecord, name: str) -> logging.LogRecord:
    """Get a copy of the record under the name that is shown."""
    if name == record.name:
        return record
    new_record = copy.copy(record)
    new_record.name = name
    return new_record


class TypeCountHandler(logging.Handler):
    """Count each record once per source, whatever the other handlers do.

    It is the only place that counts, so quiet mode, startup and the other
    handlers' routing do not change the counts.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        for name in _record_names(record):
            update_type_counts(name, record.levelno)


class CustomConsoleHandler(logging.StreamHandler):
    def __init__(self, stream: TextIO = sys.stdout) -> None:
        super().__init__(stream=stream)
        self.api = API(owner_id="plugins.core.log:CustomConsoleHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        # Check if quiet mode is enabled
        if self.api.quiet_mode:
            return

        try:
            allowed_name = _first_allowed(
                record, self.api, "plugins.core.log:logger.console.is.enabled"
            )
            if allowed_name is not None:
                super().emit(_emit_as(record, allowed_name))
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


# --- archiving of rotated log files (#779) ---

ARCHIVE_DIR = "archive"
DEFAULT_ARCHIVE_RETENTION_DAYS = 30
ARCHIVE_RETENTION_SETTING = "archive_retention_days"
NETWORKDATA_LOG_SETTING = "networkdata_log"
LOG_PLUGIN_ID = "plugins.core.log"
TYPE_FILES_DIR = "types"
_SECONDS_PER_DAY = 86400

# a rotated file is named <base>.YYYY-MM-DD, or with _HH-MM-SS for an archive on demand
_ROTATED_SUFFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(_\d{2}-\d{2}-\d{2})?$")
# a type name becomes a directory and file name, so it must not hold a path separator
_VALID_TYPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_ARCHIVE_LOCK = threading.Lock()
_ARCHIVE_TASKS: set["asyncio.Task[None]"] = set()


def is_valid_type_name(name: str) -> bool:
    """Check that a log type can be used as a directory and file name."""
    return bool(_VALID_TYPE_RE.fullmatch(name)) and ".." not in name


def _unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Get a path in directory that does not exist, adding -1, -2 to the stem."""
    candidate = directory / f"{stem}{suffix}"
    count = 0
    while candidate.exists():
        count += 1
        candidate = directory / f"{stem}-{count}{suffix}"
    return candidate


def archive_file(path: Path, archive_dir: Path) -> Path:
    """Zip a file into archive_dir as <name>.zip, then remove the file.

    The member name is the file's basename. An existing zip is never replaced.
    """
    make_log_dir(archive_dir)
    target = _unique_path(archive_dir, path.name, ".zip")
    with (
        open(target, "xb", opener=_private_opener) as handle,
        zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive,
    ):
        archive.write(path, arcname=path.name)
    path.unlink()
    return target


def sweep_rotated(log_path: Path, archive_dir: Path) -> list[Path]:
    """Zip plain rotated files (<base>.YYYY-MM-DD[_HH-MM-SS]) left next to the log."""
    prefix = log_path.name + "."
    archived: list[Path] = []
    if not log_path.parent.is_dir():
        return archived
    for candidate in sorted(log_path.parent.iterdir()):
        if (
            candidate.is_file()
            and candidate.name.startswith(prefix)
            and _ROTATED_SUFFIX_RE.fullmatch(candidate.name[len(prefix) :])
        ):
            archived.append(archive_file(candidate, archive_dir))
    return archived


def prune_archives(archive_dir: Path, retention_days: int, now: float) -> list[Path]:
    """Delete zips older than retention_days, by modification time. 0 keeps everything."""
    removed: list[Path] = []
    if retention_days <= 0 or not archive_dir.is_dir():
        return removed
    cutoff = now - retention_days * _SECONDS_PER_DAY
    for candidate in sorted(archive_dir.glob("*.zip")):
        if candidate.is_file() and candidate.stat().st_mtime < cutoff:
            candidate.unlink()
            removed.append(candidate)
    return removed


def run_archive_job(
    rotated: Path | None,
    log_path: Path,
    retention_days: int,
    now: float | None = None,
) -> None:
    """Zip the rotated file, sweep older plain rotated files and prune old zips."""
    archive_dir = log_path.parent / ARCHIVE_DIR
    with _ARCHIVE_LOCK:
        if rotated is not None and rotated.exists():
            archive_file(rotated, archive_dir)
        sweep_rotated(log_path, archive_dir)
        prune_archives(archive_dir, retention_days, time.time() if now is None else now)


def _archive_job_done(task: "asyncio.Task[None]") -> None:
    """Log, on the loop thread, an archive job that failed."""
    _ARCHIVE_TASKS.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logging.getLogger(LOG_PLUGIN_ID).error(
            "archiving a log file failed: %r", error, exc_info=error
        )


def _schedule_archive(job: Callable[[], None]) -> None:
    """Run an archive job in a worker thread when a loop is running, else inline.

    Errors are never logged from the worker thread: the client handler would send
    data to the client from it. The inline path is reached from inside a handler's
    emit, so an error goes to stderr rather than back into the handlers.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            job()
        except Exception:
            traceback.print_exc(file=sys.stderr)
        return
    task = loop.create_task(asyncio.to_thread(job))
    _ARCHIVE_TASKS.add(task)
    task.add_done_callback(_archive_job_done)


class ArchivingMixin(logging.handlers.TimedRotatingFileHandler):
    """A timed rotating handler that zips its rotated files into ``archive/``.

    The rename is done in the handler, which is cheap. The zip, the sweep of older
    plain rotated files and the pruning run in an archive job.
    """

    archive: bool = False
    api: API

    def _retention_days(self) -> int:
        """Get the retention in days, read at rotation time on the calling thread."""
        try:
            if self.api("libs.api:api.exists")("plugins.core.settings:setting.get"):
                value = self.api("plugins.core.settings:setting.get")(
                    LOG_PLUGIN_ID, ARCHIVE_RETENTION_SETTING
                )
                if isinstance(value, int) and not isinstance(value, bool):
                    return value
        except Exception:
            # a settings failure must not stop a rotation, the default applies;
            # report it on stderr, logging from here would re-enter the handlers
            traceback.print_exc(file=sys.stderr)
        return DEFAULT_ARCHIVE_RETENTION_DAYS

    def _schedule(self, rotated: Path) -> None:
        log_path = Path(self.baseFilename)
        retention = self._retention_days()
        _schedule_archive(lambda: run_archive_job(rotated, log_path, retention))

    def rotate(self, source: str, dest: str) -> None:
        """Rename the file, then archive it."""
        if not self.archive:
            super().rotate(source, dest)
            return
        if os.path.exists(source):
            os.rename(source, dest)
            self._schedule(Path(dest))

    def archive_now(self, now: datetime.datetime | None = None) -> Path | None:
        """Rotate the current file at once to a timestamped name and archive it.

        Returns the rotated path, or None when the file is missing or empty.
        """
        stamp = (now or datetime.datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
        base = Path(self.baseFilename)
        self.acquire()
        try:
            if self.stream:
                self.stream.flush()
                self.stream.close()
                self.stream = None
            if not base.exists() or base.stat().st_size == 0:
                if not self.delay:
                    self.stream = self._open()
                return None
            rotated = _unique_path(base.parent, f"{base.name}.{stamp}", "")
            os.rename(base, rotated)
            if not self.delay:
                self.stream = self._open()
            self._schedule(rotated)
            return rotated
        finally:
            self.release()


class ArchivingFileHandler(PrivateFileMixin, ArchivingMixin):
    """A midnight rotating file handler with mode 0o600 files that archives rotations."""

    def __init__(
        self,
        filename: str | os.PathLike[str],
        when: str = "midnight",
        delay: bool = False,
        archive: bool = True,
    ) -> None:
        super().__init__(filename, when, delay=delay)
        self.api = API(owner_id="plugins.core.log:ArchivingFileHandler")
        self.archive = archive


class NetworkDataFileHandler(ArchivingFileHandler):
    """The network data log. The ``networkdata_log`` setting turns it off."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.api("libs.api:api.exists")("plugins.core.settings:setting.get") and not (
                self.api("plugins.core.settings:setting.get")(
                    LOG_PLUGIN_ID, NETWORKDATA_LOG_SETTING
                )
            ):
                return
        except Exception:
            # a settings failure keeps the log on, which is the default;
            # report it on stderr, logging from here would re-enter the handlers
            traceback.print_exc(file=sys.stderr)
        super().emit(record)


_ARCHIVE_TARGETS: dict[str, ArchivingMixin] = {}
TYPE_FILE_HANDLER: "TypeFileHandler | None" = None


def archive_target(name: str) -> ArchivingMixin | None:
    """Get the main or networkdata file handler by target name."""
    return _ARCHIVE_TARGETS.get(name)


def type_file_handler() -> "TypeFileHandler | None":
    """Get the handler that writes the per-type files."""
    return TYPE_FILE_HANDLER


class TypeFileHandler(logging.Handler):
    """Write the types that have their own file to ``<base_dir>/<type>/<type>.log``."""

    FORMAT_TIMESTAMP = "%(asctime)s : %(levelname)-9s - %(message)s"
    FORMAT_PLAIN = "%(message)s"

    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.api = API(owner_id="plugins.core.log:TypeFileHandler")
        self.files: dict[str, ArchivingFileHandler] = {}
        self._with_stamp = logging.Formatter(self.FORMAT_TIMESTAMP)
        self._plain = logging.Formatter(self.FORMAT_PLAIN)
        self.setLevel(logging.DEBUG)

    def path_for(self, top: str) -> Path:
        """Get the path of a type's file."""
        return self.base_dir / top / f"{top}.log"

    def _handler_for(self, top: str) -> ArchivingFileHandler:
        handler = self.files.get(top)
        if handler is None:
            make_log_dir(self.base_dir / top)
            handler = ArchivingFileHandler(self.path_for(top), when="midnight", delay=True)
            handler.api = self.api
            self.files[top] = handler
        return handler

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if not self.api("libs.api:api.exists")("plugins.core.log:logger.file.separate.get"):
                return
            get_info = self.api("plugins.core.log:logger.file.separate.get")
            has_check = self.api("libs.api:api.exists")("plugins.core.log:logger.file.is.enabled")
            check = self.api("plugins.core.log:logger.file.is.enabled") if has_check else None
            seen: set[str] = set()
            for name in _record_names(record):
                top = get_toplevel(name)
                if top in seen:
                    continue
                seen.add(top)
                info = get_info(top)
                if not info or not is_valid_type_name(top):
                    continue
                if check is not None and not check(name, record.levelno):
                    continue
                handler = self._handler_for(top)
                stamped = info.get("timestamp", True)
                handler.setFormatter(self._with_stamp if stamped else self._plain)
                handler.handle(_emit_as(record, name))
        except Exception:
            self.handleError(record)

    def close_type(self, top: str) -> None:
        """Close the file of a type that no longer has its own file."""
        handler = self.files.pop(top, None)
        if handler is not None:
            handler.close()

    def archive_type(self, top: str) -> Path | None:
        """Rotate a type's file at once and archive it. None when it has nothing to archive."""
        if not is_valid_type_name(top):
            return None
        return self._handler_for(top).archive_now()

    def close(self) -> None:
        for top in list(self.files):
            self.close_type(top)
        super().close()


class CustomRotatingFileHandler(PrivateFileMixin, ArchivingMixin):
    def __init__(
        self,
        filename: str | os.PathLike[str],
        when: str = "midnight",
        interval: int = 1,
        backupCount: int = 0,  # noqa: N803  # mirrors the stdlib TimedRotatingFileHandler signature
        encoding: str | None = None,
        delay: bool = False,
        utc: bool = False,
        atTime: datetime.time | None = None,  # noqa: N803  # mirrors the stdlib TimedRotatingFileHandler signature
        archive: bool = False,
    ) -> None:
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc, atTime)
        self.api = API(owner_id="plugins.core.log:CustomRotatingFileHandler")
        self.archive = archive
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            allowed_name = _first_allowed(
                record, self.api, "plugins.core.log:logger.file.is.enabled"
            )
            if allowed_name is not None:
                super().emit(_emit_as(record, allowed_name))
        except Exception:
            super().emit(record)


class CustomClientHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.api = API(owner_id="plugins.core.log:CustomClientHandler")
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        if self.api.startup:
            return

        if not self.api("libs.api:api.exists")("plugins.core.log:logger.client.is.enabled"):
            return

        names = _record_names(record)
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


def reset_logging() -> None:
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
    global TYPE_FILE_HANDLER
    TYPE_FILE_HANDLER = None
    _ARCHIVE_TARGETS.clear()


def setup_loggers(log_level: int) -> None:
    from bastproxy.libs.api import API

    reset_logging()
    rootlogger = logging.getLogger()
    rootlogger.setLevel(logging.DEBUG)

    default_log_file_path = API.BASEDATALOGPATH / default_log_file
    make_log_dir(API.BASEDATALOGPATH / "networkdata")
    data_logger_log_file_path = API.BASEDATALOGPATH / "networkdata" / data_logger_log_file

    file_handler = CustomRotatingFileHandler(
        filename=default_log_file_path, when="midnight", archive=True
    )
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
    type_handler = TypeFileHandler(API.BASEDATALOGPATH / TYPE_FILES_DIR)
    for handler in (file_handler, type_handler, console_handler, client_handler, RECORD_LOG_BUFFER):
        handler.addFilter(RenderFilter())
        handler.addFilter(RecordContextFilter())

    # add the handler to the root logger
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().addHandler(type_handler)
    logging.getLogger().addHandler(console_handler)
    logging.getLogger().addHandler(client_handler)
    logging.getLogger().addHandler(RECORD_LOG_BUFFER)
    # no render or context filters: the buffer renders the message itself
    logging.getLogger().addHandler(ERROR_BUFFER)
    logging.getLogger().addHandler(TypeCountHandler())

    if API.LOG_IN_UTC_TZ:
        logging.Formatter.formatTime = format_time_rfc3339_utc  # type: ignore[method-assign,assignment]  # module-level override of the stdlib formatter
    else:
        logging.Formatter.formatTime = format_time_rfc3339  # type: ignore[method-assign,assignment]  # module-level override of the stdlib formatter

    # This logger is for any network data from both the mud and the client to facilitate
    # debugging. It is not intended to be used for general logging. It will not use the same
    # log settings as the root logger. It will log to a file and not to the console.
    # logging network data from the mud will use data.mud
    # logging network data to/from the client will use data.<client_uuid>
    data_logger = logging.getLogger("data")
    data_logger.setLevel(logging.INFO)
    data_logger_file_handler = NetworkDataFileHandler(
        data_logger_log_file_path, when="midnight", archive=True
    )
    data_logger_file_handler.formatter = logging.Formatter(
        "%(asctime)s : %(name)-11s - %(message)s"
    )
    data_logger.addHandler(data_logger_file_handler)
    data_logger.propagate = False

    global TYPE_FILE_HANDLER
    TYPE_FILE_HANDLER = type_handler
    _ARCHIVE_TARGETS["main"] = file_handler
    _ARCHIVE_TARGETS["networkdata"] = data_logger_file_handler
