---
title: Logging System
description: How bastproxy code logs through standard-library loggers, how thresholds and handlers route messages, and how to migrate from LogRecord
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - logging
---

# Logging System

Bastproxy code logs through standard-library loggers. `src/bastproxy/libs/logger.py` adds a few helpers, and the log plugin (`src/bastproxy/plugins/core/log/`) decides where each message goes. `LogRecord` no longer exists (#247, part of #43); see [ADR-0005](../decisions/0005-record-tracking-scope-change-contents-retention-and-cost.md) point 4.

## Writing log calls

```python
import logging

from bastproxy.libs.logger import get_logger, log_to

logger = get_logger(__name__)          # module level: one logger for the module

logger.debug("started %s with %s", name, args)
logger.error("lookup failed for %s", key, exc_info=True)

get_logger(self.plugin_id).info("plugin ready")                      # another logger name
log_to([__name__, self.plugin_id], logging.DEBUG, "added %s", item)  # more than one source
```

- **Use lazy `%` arguments, never an f-string.** The level is checked before the message is built, so a disabled `debug` call never formats its arguments. The arguments themselves are still evaluated, so keep them cheap.
- **`get_logger(name)`** returns `logging.getLogger(name)` with an explicit level taken from the per-name threshold (INFO when none is set). An explicit level avoids dotted-hierarchy inheritance and works for owner IDs with a `:` suffix.
- **`log_to(sources, level, msg, *args, exc_info=None, stack_info=False)`** is for a message that belongs to more than one logger name. It makes one call on the first source whose logger is enabled for the level, and returns at once if none is. The record carries `log_sources`, the tuple of all sources. `record.funcName` is the caller's.
- **`stack_info=True` and `exc_info=True`** are passed through. A `stack_info` stack ends at the caller.
- A message that is a list of lines is not accepted any more: join the lines with `"\n"` and log them as one string.

## Thresholds are a pre-filter, handlers decide

The root logger is at DEBUG and has three handlers (console, file, client) in `src/bastproxy/plugins/core/log/libs/_custom_logger.py`. Each handler asks the log plugin whether a name may be emitted at a level (`logger.console.is.enabled`, `logger.file.is.enabled`, `logger.client.is.enabled`), and the client handler also lets ERROR and above through.

`set_threshold(name, level)` stores a level per toplevel name (the part before the first `:`) and sets it on the logger and on every existing logger with that toplevel. The log plugin calls it (`_sync_threshold`) at startup and whenever a console, file or client level changes: the threshold is DEBUG if any of the three is at a level below INFO for that name, otherwise INFO. The invariant: a logger's level is never above a level a handler would accept for that name. Because of this, a debug message for a name that no handler wants at debug is dropped before any handler runs. The handlers still make the routing decision.

## Routing in the handlers

- **One emission per handler.** For a record from `log_to`, each handler takes the first name in `log_sources` that it allows and emits a copy of the record under that name. The client handler falls back to the first source for ERROR and above.
- **Counts.** `update_type_counts` runs once per source in each handler, so `#bp.core.log.types` counts per source. Debug messages for names that are not at debug are no longer counted, because they never reach a handler.
- **`record_id`.** `RecordContextFilter` sets `record.record_id` to the UUID of the active record in `RMANAGER` (or `None`). It stores the UUID string, never the record, so a log record keeps no record alive.
- **Rendering.** `RenderFilter` runs once per record on each handler: it formats the message with its arguments, splits it into lines and drops `\r`.

## Log lines for each record

A fourth root handler, `RecordLogBuffer` in `src/bastproxy/libs/logger.py`, keeps the last log lines written while a record was the active record. It has the same `RenderFilter` and `RecordContextFilter` as the other handlers and runs at DEBUG, so what it holds is what the logger thresholds let through.

- **Limits.** The last 50 lines for each `record_id` (`MAX_LINES_PER_RECORD`), for at most 2000 record ids (`MAX_RECORDS`). The oldest record id is evicted first. Access is guarded by the handler's lock.
- **Format.** `"%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s"`, with no colour codes. Records with no `record_id` are skipped.
- **Not buffered.** The `data` logger has `propagate = False`, so `data.*` messages never reach the root handlers.
- **API.** `get_record_logs(record_id)` returns a copy of the lines; `clear_record_logs()` empties the buffer (for tests).
- **Showing them.** With the `showRecordLogs` setting of `plugins.debug.records` on (default off), `#bp.debug.records.detail <uid>` ends with a `Log messages :` section, each line indented 4 spaces, or `none`. It covers the record itself, not its children, and is also written by the dump option (`-d`). It is not shown with `-u`.

The file log carries the record id: `"%(asctime)s : %(levelname)-9s - %(name)-22s - %(record_id)s - %(message)s"`, with `-` when no record is active. `RecordIdFormatter` formats a copy, so the log record keeps `None`. The console and client formats are unchanged.

## Colours

Colours are applied when a record is output, not when it is logged:

- `CustomColorFormatter` wraps the whole formatted message in the level colour (`log.level.color.get`), which is how the console shows it. It appends an `exc_info` traceback as separate lines, on a copy of the record.
- The client handler sends one `NetworkDataLine(line, color=<level colour>)` per line.
- The file handler uses a plain formatter, so **the log file has no ANSI codes**.
- `@` colour codes inside interpolated values are not converted any more.

## Testing a logger

`#bp.core.log.test -l <logtype> -ll <level> "<message>"` logs a message and reports `Console`, `File` and `Client`. The flags come from the `is.enabled` APIs, quiet mode and startup, not from the handlers.

## Migrating a plugin

`bastproxy.libs.records.LogRecord` and `RMANAGER.default_filter` are removed. The `showLogRecords` setting of `plugins.debug.records` is renamed `showRecordLogs` and now shows the log lines kept for the record; see [Log lines for each record](#log-lines-for-each-record).

| Before | After |
|--------|-------|
| `LogRecord("msg", level="debug", sources=[a])()` | `get_logger(a).debug("msg")` |
| `LogRecord(f"x {v}", level="info", sources=[__name__])()` | `logger.info("x %s", v)` with `logger = get_logger(__name__)` |
| `LogRecord("msg", level="debug", sources=[a, b])()` | `log_to([a, b], logging.DEBUG, "msg")` |
| `LogRecord(["l1", "l2"], ...)()` | one string: `"\n".join(lines)` |
| `LogRecord("msg", level="error", sources=[a], exc_info=True)()` | `get_logger(a).error("msg", exc_info=True)` |

## Measured cost

Scratch measurement after #247 (Python 3.12.12, one run, median of 5 runs of 2000 calls, a `NullHandler` only, no plugins): `get_logger(NAME).debug(...)` costs 0.54 us per call with debug off and 5.02 us with debug on; `log_to` with two sources costs 1.44 us with debug off and 5.03 us with debug on. `tests/benchmarks/test_bench_logging.py` asserts at most 5 us for the debug-off single-source call when benchmarks are enabled (`doit benchmark`).

## Related

- [Record System](record_system.md)
- [ADR-0005](../decisions/0005-record-tracking-scope-change-contents-retention-and-cost.md)
- `info/logging_notes.txt`
