---
title: "ADR-0006: Records adapt pydatatracker containers and locked writes raise RuntimeError"
description: Records adapt pydatatracker containers through a mixin and a read-only update view; a locked NetworkDataLine or NetworkData raises RuntimeError on writes; the actor comes from a context variable; a benchmark gate caps 75 us per line created and 20 us per change locally and on main, and fails a pull request that is more than 25% slower than its base on the same runner.
date: 2026-11-09
audience: [contributors]
tags: [adr, records]
---

# ADR-0006: Records adapt pydatatracker containers and locked writes raise RuntimeError

## Status

Accepted

## Context

ADR-0005 decided what records track, what a change holds, how long it is kept and what it may cost. It says the lock "is enforced on every mutation" but not how: by raising or by ignoring the write. It does not cover how the pydatatracker containers fit the record interface the rest of the proxy uses. Issue #43 asks for both.

Today `NetworkDataLine` is a `BaseRecord` on `AttributeMonitor` and `NetworkData` is a `TrackedUserList`. A write to a locked line is dropped and recorded as an `Info` update, and `pop`, `sort` and `+=` on a locked `NetworkData` change the list without a record (#47, #48). Inference from the audit: a silent drop hides a plugin bug until someone reads the update list.

pydatatracker 0.2.0 offers `TrackedAttr` and `TrackedList`. A locked container raises `RuntimeError`, it takes the actor from a context variable, and it caps history with `tracking_max_changes`. Two behaviours needed handling:

- It re-homes every child entry onto the parent, so a parent shows each child change twice if it reads its whole log.
- `TrackedList.lock()` calls `lock()` on each child, and a whole-object lock on a `TrackedAttr` also refuses writes to `was_sent`. The network layer sets `was_sent` after the line is locked.

## Decision

This is slice 1 of #43. The repo admin approved the split and the breaking change on 2026-11-09. Slices 2 to 5 are #246 to #249.

1. **Adapter.** `bastproxy.libs.records.tracking` holds `TrackedRecordMixin`, placed first in the bases (`class NetworkData(TrackedRecordMixin, TrackedList)`) so its `__eq__` and `__hash__` win over the container's content equality. It provides `uuid` and `created` (over pydatatracker's own), `owner_id`, `parent`, `parents`, identity by class and uuid, registration with `RMANAGER`, `addupdate` and `updates`.
2. **A view, not a copy.** `updates` returns `TrackedUpdate` objects that wrap the container's `ChangeLogEntry` entries and give them `UpdateRecord`'s display interface. `RMANAGER` and `plugins/debug/records` need no changes.
3. **Own entries only.** The view keeps entries whose tree has one item. A re-homed child entry has two or more, so `get_all_updates` on a processing record shows each line change once.
4. **Shared display code.** `RecordDisplayMixin` holds the detail formatting that `BaseRecord` and the tracked classes share, with three hooks for what differs.
5. **Per-field line lock.** `NetworkDataLine.lock()` locks the eight fields the old code locked and leaves `was_sent` writable. A second call does nothing, and `format()` does nothing on a locked line. The send steps format first, then lock the message.
6. **Locked writes raise `RuntimeError`.** This covers every mutation of a locked `NetworkData` (`append`, `insert`, `extend`, `pop`, `sort`, `+=`, item and slice assignment) and every write to a locked `NetworkDataLine` field or to `original_line`. Silent loss hid bugs (#48).
7. **One conversion hook.** `NetworkData._tracking_convert_item` turns str, bytes and bytearray into `NetworkDataLine`, rejects other types with `TypeError`, and makes the list the line's parent. Every way of storing an item goes through it.
8. **Actor from a context variable.** The events plugin runs each callback, and the commands plugin runs each command, inside `tracking_actor("<owner>:<name>")`. Plugins import `tracking_actor` from `bastproxy.libs.records.tracking`, not from pydatatracker. Stack capture is off.
9. **Retention.** `MAX_CHANGES = 1000` per record, the cap `UpdateManager` has. #249 and #233 make retention configurable.
10. **Benchmark gate.** `tests/benchmarks/test_bench_networkdataline.py` runs create and change under `tracking_actor("bench")` and, when benchmarks are enabled, asserts at most 75 us per line created and 20 us per change. Creation is above the ADR-0005 target of 50 us for CI runner speed (#412); the change gate is the ADR-0005 target. `doit benchmark` and pushes to main enforce the fixed limits. On pull requests the workflow sets `BENCH_ABSOLUTE_GATE=report`, so the fixed limits are report-only, and `.github/scripts/benchmark_vs_base.sh` benchmarks the base and the PR on the same runner, failing when the median of creation or change is more than 25% slower (#439). A disabled run (`doit check`) skips the assertion. The gate is not loosened to pass a slower change; it moved once, for runner speed (#412).

## Rationale

- **Mixin and view (1, 2):** the rest of the proxy reads `uuid`, `parents`, `updates` and `format_detailed`. Keeping that interface on the tracked classes means no other module changes in this slice.
- **Own-entry filter (3):** the other choice is to read the whole log and show duplicates, which misleads anyone reading a processing record's updates.
- **Per-field lock (5):** locking the whole object would refuse `was_sent` and break the send path in `src/bastproxy/libs/net/client.py` and `src/bastproxy/libs/net/mud.py`.
- **Raising (6):** a refused write that raises is caught and logged by `Event.raise_priority`, so the proxy keeps running, and the plugin author sees the error. The old drop was visible only in an update.
- **One hook (7):** it replaces the constructor loop and four method overrides, and it also covers `+=` and slices, which the old class missed. It gives appended lines a parent, which closes the #47 gap for these two classes.
- **Gate (10):** a target with no assertion fails nothing. The ADR-0005 text asks for the benchmark to measure the targets. The creation gate is 75 us, not the 50 us target, because runner speed moves unchanged code past the target (#412). A fixed limit cannot cover runner speed at all, so a pull request is gated on its slowdown against its base on the same runner (#439). The fixed limits still bind local runs and pushes to main; a slow runner can fail the absolute check on a push to main, which blocks no pull request.

## Dict records

`BaseDictRecord` (`EventDataRecord`, `CmdArgsRecord`) is a `TrackedDict` with `TrackedRecordMixin` (#246). A value that is itself a record is stored without being linked as a pydatatracker child. pydatatracker links every tracked value a dict stores, and a link merges the locks of the two trees: with pydatatracker 0.2.0, a locked `NetworkData` stored in an unlocked `TrackedDict` became unlocked, and locking the dict locked the stored lines (probed during planning). Records already have their own record parents and locks, so the dict skips the link for them; a plain `TrackedDict` or `TrackedList` value is still linked. A record shared by several events keeps each of them in `parents` (`EventDataRecord.add_receiving_event`), which the record manager already lists under each parent.

## Consequences

Measured with `uv run pytest tests/benchmarks/test_bench_networkdataline.py --benchmark-enable --benchmark-only` on the final code of this slice, Python 3.12.12, pydatatracker 0.2.0, one run. Medians:

```
test_bench_networkdataline_create            270.2 us per 15 lines  = 18.0 us per line   (target 50)
test_bench_networkdataline_attribute_change    6.5 us per change                          (target 20)
test_bench_networkdata_build                 400.8 us per 15 lines  = 26.7 us per line
test_bench_networkdataline_lock            1,052.8 us per 15 lines  = 70.2 us per line   (informational)
test_bench_networkdata_get_formatted_details 1,421.1 us per 15 lines
```

ADR-0005 measured the old `NetworkDataLine` at 95.9 us to create and 42.2 us per change with a different harness (1,500 lines, median of 5 runs), so those figures are a reference, not a like-for-like "before".

- **Breaking for plugins.** A write to a locked `NetworkDataLine` or `NetworkData` raises `RuntimeError`. Plugins meet this in `ev_to_client_data_read` and `ev_to_mud_data_read` callbacks. A grep found no bundled plugin that writes in those events. Unsent lines (`send=False`) are now locked when their message is sent.
- `NetworkData` is a `list` subclass, not a `UserList`: `.data` is gone and `.locked` is read-only. Both classes lose `stack_at_creation`, `event_stack`, `check_for_change` and the `_am_*` methods.
- `#bp.debug.records.detail` shows no creation stacks and no "original input" update for these two types, the update actions are pydatatracker's (`update`, `add`, `lock`), and the actor is the context name, "Unknown" on the raw network read path.
- Records still on `AttributeMonitor` or `UserList` kept their old behaviour until slices 2 to 4. After #248 none remain, and the processing records show their updates as `TrackedUpdate` too.
- The locking of a line costs one change entry per field. It is not part of the ADR-0005 targets.
- `bastproxy.libs.records.*` is under a mypy `ignore_errors` override, so the new adapter is annotated but not checked by `doit type_check`.

## Related Issues

- #43 (replace the attribute monitor with pydatatracker; this is slice 1)
- #246 (slice 2: dict records, done), #247, #248, #249 (slices 3 to 5)
- #230, #234 (addressed by #246)
- #47, #48 (lock and in-place mutations, for these two classes)
- #79 (ADR-0005)
- #412 (creation gate raised to 75 us for CI runner speed)
- #439 (pull requests gated against their base on the same runner)

## Related Documentation

- [Record System](../claude/record_system.md)
- [Data Flow](../claude/data_flow.md)
- [ADR-0005: Record tracking: scope, change contents, retention and cost](0005-record-tracking-scope-change-contents-retention-and-cost.md)
