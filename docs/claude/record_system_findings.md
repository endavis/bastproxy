---
title: Record System Analysis and Findings
description: Audit of record mutation tracking, the parent/child tree, retention and memory, test coverage, docs accuracy and the patterns the record system uses, with defects and a patterns review
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - records
  - review
---

# Record System Analysis and Findings

**Date:** 2026-11-09
**Analyzer:** Claude Sonnet 5.5
**Scope:** The record system in `src/bastproxy/libs/records/` (`rtypes/`, `managers/`): which
mutations are tracked, the parent/child tree on every data path, what `RecordManager` keeps and what it
costs, test coverage, docs accuracy and patterns (audit issue #106). Compared against
[Record System](record_system.md) and [Data Flow](data_flow.md). Base commit `6e8b6ff`.

`AttributeMonitor`, `UpdateRecord` and `UpdateManager` are read only to fill the mutation table (Q1).
#43 replaces them with pydatatracker, so they get no pattern review and no coverage work here.

Requirements decided in [ADR-0005](../decisions/0005-record-tracking-scope-change-contents-retention-and-cost.md).

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [Status of the Known Items](#status-of-the-known-items)
4. [Q1: Which Mutations Are Recorded?](#q1-which-mutations-are-recorded)
5. [Q2: Is the Parent/Child Tree Right?](#q2-is-the-parentchild-tree-right)
6. [Q3: What Is Kept, and What Does It Cost?](#q3-what-is-kept-and-what-does-it-cost)
7. [Q4: What Is Untested?](#q4-what-is-untested)
8. [Q5: Where the Docs Disagreed With the Code](#q5-where-the-docs-disagreed-with-the-code)
9. [Q6: Patterns and Anti-Patterns](#q6-patterns-and-anti-patterns)
10. [New Defects](#new-defects)
11. [Other Observations](#other-observations)

---

## Executive Summary

The tracking does what the docs say for the cases it was built for: reassigning a monitored attribute
on a `NetworkDataLine`, and `append`, `insert`, `extend` and item assignment on a `NetworkData`, each
add an update, and `lock()` stops them. Everything else is open: most operations on the list and dict
record types are untracked, and the lock does not stop the in-place ones (Q1). The parent/child tree is
correct for commands and for events. It is wrong for MUD-originated lines and for lines appended to a
`NetworkData` in general, for split commands and for events shared with the triggers plugin (Q2).

The new findings are about retention and about two places the tree is quietly wrong:

- **Memory is capped by record count per type, not by size** (RS-5). One round of 15 MUD lines grew
  the traced heap by about 0.66 MB, and after 1,500 rounds the heap was 1,139 MB with the
  `ProcessDataToClient` store only 30% full. A stored `NetworkData` holds its lines, so the
  `NetworkDataLine` cap of 5,000 does not free anything: 17,516 lines were past that cap and
  still alive (Q3).
- **API stats grow with every record** (RS-4). Each record's owner ID contains its UUID, and the API
  statistics key calls by caller ID, so every record adds keys that are never removed: 371 new caller IDs
  per round of 15 lines (Q3).
- **Evicting an empty record leaves it in the store forever** (RS-1). `RecordManager.add` tests the
  evicted record for truth, and a list or dict record with no data is false. Verified with
  `NetworkData` and `LogRecord`; events raised with no arguments build an empty `EventDataRecord`.
- **The event data of a shared event moves** (RS-2). `ProcessRaisedEvent` re-parents the
  `EventDataRecord` it is given, and the triggers plugin passes the same record to two more events.
  After a MUD line, the data of `ev_to_client_data_modify` hangs under a trigger event.
- **Split commands hang under the line that was replaced** (RS-3). The pieces of `say a|say b` have the
  original line as their parent, and that line is no longer in the `NetworkData`.
- `BaseDictRecord.addupdate` stores a clone of the whole record, not a copy of its dict (RS-6).
- Test coverage of the six non-trivial files in `libs/records/` runs from 33.09% (`clientdata.py`) to 84.07%
  (`records.py`) in the whole suite. The processing records' `_exec_`, `seperate_commands`,
  `copy_attributes`, record eviction and every locked path of `TrackedUserList` have no test (Q4, RS-11).

**Key Findings:**

- 11 new defects and changes (RS-1 to RS-11), listed under [New Defects](#new-defects). The Q1
  gaps, the Q2 `NetworkData` parent gap, `get_update`, locked-write handling and the per-update cost
  are already filed (#47, #48, #49, #81); this audit adds measurements and cases to them.
- The code disagreed with the docs in 11 places; 9 are fixed in [Record System](record_system.md) and
  [Data Flow](data_flow.md), and 2 are code comments (RS-10) (Q5).
- The existing benchmark is `tests/benchmarks/test_bench_networkdataline.py`; run it with
  `doit benchmark`.

---

## How This Was Verified

Claims below are tagged **verified** (run against the code, output saved), **read** (from reading the
code, not executed) or **unverified**.

Verification used throwaway scripts, deleted afterwards and not part of the repository:

- a mutation script that applies each operation to each record type and counts the updates it adds
  (no plugins needed, Q1);
- a tree script that boots the real plugin system in-process (`PluginLoader().load_plugins_on_startup()`,
  as `MudProxy.run` does without the listeners and the event loop) and runs each data path the way its
  real entry point builds it, then walks the descendants and checks the parent rules (Q2);
- a memory script that drives the MUD to client path with 15 lines per round under `tracemalloc`, takes
  a census after every batch, and times the tree query (Q3), plus small scripts for the retention
  mechanisms and for the API stats keys.

The saved outputs are listed beside each table. Coverage comes from `doit coverage` and from a narrow
`pytest --cov` run of `tests/libs/records`. The existing benchmark was run with `doit benchmark`.

**Scale of the memory run.** The plan was 500-round batches until `NetworkDataLine` reached the cap,
then 1,000 more rounds. The run used 250-round batches and 1,500 rounds in total (267.9 s of fill, under
the five-minute limit, so it was not scaled down). `NetworkDataLine` reached the cap at the 500 round
census, `LogRecord` at the first. `ProcessDataToClient` and `NetworkData` never filled, which matters for
Q3.

**Limits.** The memory numbers are `tracemalloc` figures for Python allocations, not the resident size of
the process. The call stack in the script is shallow (6 lines per stack), so a deeper stack in the real
proxy costs more per record than shown here (**verified**: 6 stack lines per update in the script; the
real depth was not measured). Round time under `tracemalloc` was 162 to 190 ms; that is the cost of
tracing, not of the records (the benchmark below has the real figure). An earlier run kept its own
census lists alive between batches, which pinned records and overstated retention; it was discarded, and
every number on this page is from the corrected run.

Environment: Python 3.12.12, pytest-benchmark 5.3.0, 12th Gen Intel Core i7-12650H, 2026-11-09.

---

## Status of the Known Items

Every item in the issue's list, with its current state.

| Item from the issue | Status | Where |
| :--- | :--- | :--- |
| Requirements: what to record, keep and cost | **Open**, an ADR is planned. This audit feeds it. | #79 |
| Replace `AttributeMonitor`, `UpdateRecord` and `UpdateManager` with pydatatracker | **Open.** Q1 gives the behaviour the replacement has to match; Q2 to Q5 cover what survives it. | #43 |
| Missed mutations and lock bypasses | **Open and confirmed** (verified, Q1). New cases: `+=` and `*=` change a locked list while logging a refusal; `+=` stores raw `str` items; `BaseListRecord` and `BaseDictRecord` track none of the plain mutators. | #47, #48 |
| Display and lookup bugs | **Open and confirmed**: `get_update` raises `AttributeError` for a child's update and returns `None` for a hit (two bugs); `str()` of a telnet line raises `TypeError`. `check_for_change` also raises and has no caller. | #49 |
| Per-update capture cost | **Open.** Measured here: a monitored attribute change costs 74.8 microseconds; the stacks are 497 MiB of the 1,145 MB traced in the memory run. | #81, #80 |
| Retention | **Open.** Q3 describes what is kept, and what outlives the cap. | #82 |
| Protocol traffic not tracked | **Open**, not re-audited. | #83 |
| Update flags as an enum | **Open**, comment on #79. Q6 row 9 adds the three other string-typed fields. | #79 |
| Already fixed and closed | #44, #45, #84. Not re-checked. | n/a |

---

## Q1: Which Mutations Are Recorded?

Output: `out-q1.txt` from the mutation script. "Tracked" means the operation added an `UpdateRecord`
(flag in brackets). "Respects lock" is tested after `lock()`: **yes** means the change was refused and an
`Info` update says so, **no** means the data changed anyway. The checking rules are in
[Attribute Monitoring](record_system.md#attribute-monitoring).

### `NetworkDataLine`

Monitored attributes (**verified**): `parents`, `line`, `send`, `is_prompt`, `had_line_endings`,
`prelogin`, `preamble`, `color`, `was_sent`. `lock()` locks `line`, `send`, `is_prompt`,
`had_line_endings`, `prelogin`, `preamble`, `color` and `line_modified`; `original_line` is locked at
creation.

| Operation | Tracked | Respects lock | Issue |
| :--- | :--- | :--- | :--- |
| Reassign `line`, `send`, `is_prompt`, `had_line_endings`, `prelogin`, `preamble`, `color` | Yes (`Modify`) | Yes | |
| Reassign the same value again | No update (by design) | n/a | |
| Reassign `was_sent` | Yes (`Modify`) | **No**: not locked | By design: `src/bastproxy/libs/net/client.py` and `src/bastproxy/libs/net/mud.py` set it after the line is locked (**verified** by `grep`) |
| Reassign `line_modified` | **No**: not monitored | Yes (locked) | #48 |
| Reassign `line_type`, `originated`, `split_from` | **No** | **No**: neither monitored nor locked | #48 |
| Reassign `original_line` | n/a | Yes (always locked; each try logs an `Info`) | |
| `add_line_endings()`, `fix_double_command_seperator()`, `format()` | Yes (`Modify`, through `line`) | Yes | |
| `copy_attributes(new)` | Monitored attributes: yes (**read**; the values in the probe were equal). `line_type`, `originated`: no | **No** for `line_type` and `originated` (both changed on a locked target); 4 refusals logged for the rest | #48 |
| `add_parent(p)` (default `reset=True`) | The reset (`parents = []`) is tracked when the list was not empty (`Modify` "parents attribute changed"); the append that follows is not | n/a | #48 |
| `add_parent(p, reset=False)` | **No**: in-place append | n/a | #48 |
| `add_parent(p)` with a class other than `NetworkData` or `NetworkDataLine` | Ignored silently | n/a | Q6 row 9 |

### `NetworkData` (`TrackedUserList`)

| Operation | Tracked | Respects lock | Issue |
| :--- | :--- | :--- | :--- |
| `data[i] = x` (int index), `insert`, `append`, `extend` | Yes (`Modify`) | Yes | |
| `data[a:b] = [...]` | Raises `TypeError` before the lock check | n/a | |
| `pop`, `remove`, `del data[i]`, `del data[a:b]`, `clear`, `sort`, `reverse` | **No** | **No** | #47 |
| `data += [...]`, `data *= n` | **No** when unlocked | **No**, and worse: the list changes **and** an `Info` "Attempted to update a locked attribute" is logged (**verified**: a locked list went from 2 to 3 items, then to 6) | #47 |
| `data += ["raw string"]` | Stores a raw `str` in a `NetworkData` that is meant to hold only `NetworkDataLine` (**verified**: item types `NetworkDataLine`, `str`) | n/a | #47 |
| `data.data = []` | **No** when unlocked | Yes | #47 |
| `data.data.append(line)` (in place) | **No** | **No** | #47 |
| Parent of a line given as a `NetworkDataLine` object, via `append`, `insert`, `data[i] = line` | **No parent** (`parent` `None`, `parents` `[]`) | n/a | #47 (**verified**) |
| Parent of a line via `extend`, the constructor, or any `str` argument | Set (`parent` is the `NetworkData`) | n/a | |

`NetworkData` updates store no copy of the data (**verified**: 16 updates after 15 appends, none with a
data copy).

### `BaseListRecord` and `LogRecord`

| Operation | Tracked | Respects lock | Issue |
| :--- | :--- | :--- | :--- |
| `replace(different data)`, `clean()`, `add_line_endings()` | Yes (`Modify` "replace", with a copy of the data) | n/a: no lock exists | |
| `replace(same data)` | No update (by design) | n/a | |
| `color_lines()` | Silent no-op when `plugins.core.colors` is not loaded | n/a | Q6 row 12 |
| `append`, `l[i] = x`, `extend`, `insert`, `pop`, `del`, `clear`, `sort`, `reverse` | **No** | n/a | #47 (it names only `TrackedUserList`) |
| `.data = [...]`, `.data.append(...)` | **No** | n/a | |
| `level` and every other plain attribute | **No** (only `parents` is monitored) | n/a | |

`BaseListRecord` overrides no list mutator: its class body defines only `replace`, `clean`,
`color_lines`, `add_line_endings`, `addupdate` and the formatting helpers (**verified**).

### `BaseDictRecord` (`EventDataRecord`, `CmdArgsRecord`)

All eleven operations probed are untracked: `d[k] = v`, `del d[k]`, `update`, `pop`, `popitem`, `clear`,
`setdefault`, `|=`, `d.data = {}`, `d.data[k] = v` and a new key. The class overrides none of them
(**verified**). There is no lock. The docs already say "setting keys is not tracked".

### `BaseRecord` common

| Operation | Tracked | Issue |
| :--- | :--- | :--- |
| `parents = [x]` (reassign) | Yes (`Modify`) | |
| `add_parent(x)` in place | **No**; and the stored "original" is the same list object (**verified**: on a fresh record the original `parents` **is** the live list), so a "changed from ... to ..." display can never show it | #48 |
| `parent = x`, `owner_id = x` | **No** | #48 |
| In-place change to any monitored list attribute | **No**; the stored "original" is the same object (**verified**: `original items ['a', 'b'] live ['a', 'b'] same object: True`) | #48 |

### The four processing records

`ProcessDataToClient`, `ProcessDataToMud`, `SendDataDirectlyToClient` and `SendDataDirectlyToMud` monitor
only `parents` (**verified**). Reassigning `message`, `send_to_clients`, `error`, `preamble`, `client_id` or
`clients`, and `add_client()` or `exclude_client()`, add no update. There is no lock. Whether the processing
records should track their state is a requirement for #79.

---

## Q2: Is the Parent/Child Tree Right?

Output: `out-q2.txt` from the tree script. Each path is built the way its real entry point builds it, the
plugin system is loaded, and the records created during the run are checked against four rules:

- (a) every `NetworkDataLine` in a `NetworkData` is a child of it (`parent` and `parents`);
- (b) every record created inside `_exec_` is reachable from the record being executed;
- (c) no record has a parent from another path;
- (d) `parent` and `parents` agree.

| # | Path | (a) | (b) | (c) | (d) | Result |
| --: | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | MUD to client, as `mud_read` builds it (`NetworkData([])`, then `append(NetworkDataLine(...))`) | **Fail**: 2 of 2 lines have no parent | Fail for the 2 lines | Pass | Pass | **Fail** (#47); and the data of `ev_to_client_data_modify` is under a trigger event (#230) |
| 1b | Same, `NetworkData` built from a list of `str` | Pass | Pass | Pass | Pass | Pass |
| 2 | Client to MUD, `say a\|say b` | **Fail**: the 2 split lines are children of the original line, which is no longer in the `NetworkData` | Pass | Pass | **Fail**: 2 records | **Fail** (#231) |
| 3 | Command `#bp.core.commands.list` | Pass (the 14 output lines and the input line) | Pass | Pass | Pass | Pass |
| 4a | Event raised inside a running record | n/a | Pass | Pass | Pass | Pass |
| 4b | Event raised outside any record | n/a | Pass: the event record is a root | Pass | Pass | Pass |
| 4c | Event raised with `data_list`, inside a record | n/a | Pass | Pass | Pass | Pass |
| 5 | Trigger match on a MUD line, callback creates a `LogRecord` and a `SendDataDirectlyToClient` | **Fail** (line appended as an object, #47) | Pass for the callback's records | Pass | Pass | **Fail** (#47, #230) |
| 6 | Internal message as the login code builds it (`NetworkData([line])` then `append(line)`) | **Fail**: the second line has no parent | Fail for that line | Pass | Pass | **Fail** (#47) |

The active record stack was empty at the end of the script (**verified**: `active record stack empty at
end: True`).

What the tree shows, with the record types as `RMANAGER.format_all_children` prints them:

- **Path 1.** `ProcessDataToClient` has three children: the `NetworkData` (with no line under it), the
  `ProcessRaisedEvent` for `ev_to_client_data_modify` and the `SendDataDirectlyToClient`. The event record
  has two children, the trigger events `event_t_plugins.core.triggers_beall` and
  `event_t_plugins.core.triggers_all`. Its own `EventDataRecord` is not under it: it is under the
  `triggers_all` event (#230). The `NetworkData` has two parents, `ProcessDataToClient` and
  `SendDataDirectlyToClient`, so it is printed under both.
- **Path 2.** `ProcessDataToMud` has three children as in Path 1. Under the `NetworkData` is the original line
  `say a|say b`, and under that line are `say a` and `say b`. The two pieces have `parent` set to the
  `ProcessDataToMud` and `parents` set to the original line, so rule (d) fails (#231).
  `NetworkDataLine.copy_attributes` calls `new_line.add_parent(self)` and
  `NetworkDataLine.add_parent` defaults to `reset=True`, which is how the original line becomes the only
  parent (**read**, consistent with the output).
- **Path 3.** A command creates 87 records, 62 of them `LogRecord`s. `CmdArgsRecord` and the output
  `SendDataDirectlyToClient` are children of the `ev_to_mud_data_modify` `ProcessRaisedEvent` (the
  commands callback runs inside it), and the output `NetworkData` has the event and the
  `SendDataDirectlyToClient` as parents, so it is printed twice.
- **Path 4.** Records created in an event callback are children of the `ProcessRaisedEvent`, which is a
  child of the executing record or a root when none is running. `data_list` reuses one `EventDataRecord`.
- **Path 5.** The callback's `SendDataDirectlyToClient` is a child of the trigger's own `ProcessRaisedEvent`, not
  of the MUD line's `ProcessDataToClient`.

Two `LogRecord`s per executed record have no parent in every path (**verified**: "LogRecords: n, of which
with no parents: 2" in each run). They are the `starttimer` and `finishtimer` records that
`libs.timing` creates in `BaseRecord.__call__` before the record is pushed on the active stack
(**read**: `timing.start` runs before `RMANAGER.start`). They are noise in the store (Q3), not a tree error.

**Compared with [Data Flow](data_flow.md).** The single-command trees there match Paths 1 and 2 except for the
trigger events and the `EventDataRecord` placement (Path 1) and the split case (Path 2). The tree in that
page is a real-MUD session; the trigger events show only with the triggers plugin loaded, which the
probe had. Both pages are corrected to say what the probe shows.

---

## Q3: What Is Kept, and What Does It Cost?

### What `RecordManager` keeps

Read from `RecordManager.add` and `SimpleQueue` (`src/bastproxy/libs/queue.py`):

- One FIFO queue per **class name**, capped at `max_records` (5,000) records each. A new record is enqueued;
  when the queue is over the cap, the oldest is popped and `record_instances` loses its UUID.
- Eviction costs 0.94 microseconds when the queue is full (it is `list.pop(0)` on 5,000 items), against
  0.22 microseconds while filling (**verified**).
- Nothing else removes a record. A record stays until 5,000 newer records of its **own class** have been created.
- Each record holds its updates (a deque of at most 1,000), each update holds a stack, and a
  `BaseListRecord` update holds a copy of the data.

### What outlives eviction

Command: the memory script (`out-q3.txt`), 1,500 rounds of 15 lines, `tracemalloc` on, census after each
batch of 250 rounds, with the census lists released before each `gc.collect()`. "Kept past eviction"
is live `BaseRecord` objects that are not in `record_instances`.

| Rounds | `NetworkDataLine` stored | `ProcessDataToClient` stored | `LogRecord` stored | Records stored | Updates held | Live records | Kept past eviction | Traced MB | Peak MB |
| --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| 250 | 4,066 | 250 | 5,000 | 11,829 | 49,717 | 13,543 | 1,714 | 311.7 | 354.0 |
| 500 | 5,000 | 500 | 5,000 | 15,013 | 70,651 | 20,743 | 5,730 | 482.1 | 552.4 |
| 750 | 5,000 | 750 | 5,000 | 17,263 | 88,151 | 28,243 | 10,980 | 638.4 | 712.2 |
| 1,000 | 5,000 | 1,000 | 5,000 | 19,513 | 105,651 | 35,743 | 16,230 | 825.6 | 915.5 |
| 1,250 | 5,000 | 1,250 | 5,000 | 21,657 | 122,727 | 43,243 | 21,586 | 980.9 | 1,117.0 |
| 1,500 | 5,000 | 1,500 | 5,000 | 22,907 | 129,227 | 50,743 | 27,836 | 1,139.2 | 1,292.9 |

Kept past eviction at the end, by type (**verified**):

| Type | Count | Why it is alive |
| :--- | --: | :--- |
| `NetworkDataLine` | 17,516 | Held by the stored `NetworkData` that contains it. `NetworkData` and `ProcessDataToClient` have 1,501 and 1,500 stored of 5,000, so none was evicted. The referrer walk in `out-q3.txt` shows the `NetworkData` and the line's own updates (**verified**, besides the script's own lists); the holding through `UserList.data` is **read**. |
| `EventDataRecord` | 9,211 | Not evicted records: **clones** (all have a UUID that is in the store). `BaseDictRecord.addupdate` stores `self.copy()`, which for a `UserDict` subclass is `copy.copy(self)`, a second record object with the same UUID and the same `updates` (**verified** in `out-q3e.txt`). #234 |
| `ProcessRaisedEvent` | 1,106 | Evicted from the store (cap 5,000) and still referenced. The holder was not identified. It is **unverified**; `Event.raised_events` keeps the last 10 per event (`Event.MAX_RAISED_EVENTS = 10`, **verified**) and is the likely holder. |
| `LogRecord` | 3 | The most recently evicted and the probe's own. `LogRecord`s are freed at eviction. |

So the effective bound on memory is not 5,000 of anything. It is the point where every type that holds
other records has reached 5,000: here that is 5,000 rounds of 15 lines. That point was **not reached**
(the run stopped at 1,500 rounds and the three slowest stores were 30% full). The figures below are
for the part that was measured; the extrapolation is **unverified**.

### What it costs

| Measure | Value | Source |
| :--- | --: | :--- |
| Traced heap growth per round of 15 lines | about 0.66 MB (1,139.2 MB at round 1,500 minus 482.1 MB at round 500, over 1,000 rounds) | `out-q3.txt` |
| One `NetworkDataLine` (1 update) | 10,334 bytes | `out-q3.txt`, 300 records |
| One `LogRecord` created, not called (1 update) | 9,287 bytes | `out-q3.txt` |
| One plain `BaseRecord` (0 updates) | 3,570 bytes | `out-q3.txt` |
| Updates on a called `LogRecord` | 4, all with a copy of the data | `out-q3.txt` |
| Updates on a `NetworkData` after 15 appends | 16, none with a data copy | `out-q3.txt` |
| Copies of the data held by a `LogRecord` after 20 `replace` calls of 50 lines | 21 updates, 21 copies, 1,050 list items | `out-q3.txt` |
| Top allocation sites (traced, final) | `UpdateRecord.fix_stack` (`update.py` lines 108 and 109) 497 MiB and 39.6 MiB; `BaseRecord.fix_stack` (`base.py` line 182) 70.7 MiB; `API(...)` in `UpdateRecord.__init__` (`update.py` line 48) 55.0 MiB; API stats dicts (`src/bastproxy/libs/api/_apistats.py` line 97) 65.0 MiB | `out-q3.txt` |
| Tree query (`get_all_children_list`) on a root with 9 descendants | 10.89 ms with 3,547 stored records; 98.11 ms with 22,912 | `out-q3.txt` |
| Create 15 `NetworkDataLine` records | median 2.28 ms (about 152 microseconds each) | `doit benchmark`, `out-benchmark.txt` |
| Build a `NetworkData` of 15 lines | median 2.39 ms | `doit benchmark` |
| Change one monitored attribute | median 74.8 microseconds | `doit benchmark` |
| `NetworkData.get_formatted_details` of 15 lines | median 0.978 ms | `doit benchmark` |

The stacks are the cost. A record pays for a creation stack and one more per update, and the stack
strings are the largest allocation site in the run (497 MiB at `update.py` line 108). That the 74.8
microseconds of an attribute change are mostly `traceback.format_stack` is **unverified**: the benchmark
does not separate it. #81 owns the capture cost; the numbers above are
the measurements it asked for in #80. **Any optimisation must have a benchmark in `tests/benchmarks/`
first** (perf-change Step 1); this audit changed no code and added no benchmark.

The tree query scans every stored record at each level of the tree (**read**), and the 9x slowdown
from a nearly empty store to a full one fits that. It runs only from the debug commands and from
`get_formatted_details` (**read**), so it is not on the hot path; it matters when the debug plugin
is used on a long-running proxy.

### API stats grow with every record

The memory table does not include the growth that eviction cannot free. `STATS_MANAGER` keeps, for each
API function, a `detailed_calls` dict keyed by the caller ID (`src/bastproxy/libs/api/_apistats.py`), and a record's
owner ID is `f"{ClassName}:{uuid}"` when none is given. Every record, and every `UpdateRecord`, calls APIs
with its own unique ID.

| Measure | Value | Source |
| :--- | --: | :--- |
| New distinct caller IDs per round of 15 lines | 371, in 20 rounds and again in 40 | `out-q3f.txt` |
| By prefix after 20 rounds | `UpdateRecord` 6,060, `LogRecord` 940, `NetworkDataLine` 300, `ProcessRaisedEvent` 80 | `out-q3f.txt` |
| `detailed_calls` entries across all APIs, per round | 1,613 (48,351 before, 774,207 after 450 rounds) | `out-q3d.txt` |
| Memory at round 1,500 | 65.0 MiB in `_apistats.py` line 97, 12 dicts | `out-q3.txt` |

None of these keys repeats, so the dict only grows. It is not bounded by `max_records`. #232

**Fixed in #232:** records now use their class name as owner ID, so the record keys no longer grow.

---

## Q4: What Is Untested?

`libs/tracking/` is out of scope. `update.py` and `updates.py` are shown for completeness
and left out of the recommendations (#43 deletes them).

**Whole suite.** Command: `uv run doit coverage`; the suite: 4,349 passed, 13 skipped, 0 failed (`coverage.txt`).

```text
Name                                                 Stmts   Miss Branch BrPart   Cover   Missing
src/bastproxy/libs/records/__init__.py                   7      0      0      0 100.00%
src/bastproxy/libs/records/managers/records.py          89     12     24      6  84.07%   62-68, 139->141, 157->159, 187, 212-214, 222-223, 232, 245-246, 258
src/bastproxy/libs/records/managers/updates.py          12      0      2      0 100.00%
src/bastproxy/libs/records/rtypes/base.py              284     87     96     16  62.89%   55, 59->61, 73->exit, 120, 135-137, 170-176, 210, 232-244, 273, 291->293, 293->303, 307, 320-325, 356, 364, 385-392, 396-403, 412-416, 426-433, 497-506, 515-521, 526, 531, 545, 557-576, 595, 599-601, 638-641, 649, 658-663
src/bastproxy/libs/records/rtypes/clientdata.py         94     56     42      3  33.09%   41-65, 74-86, 90-92, 121, 125-128, 132-135, 139-154, 160-166, 207-208, 217, 221-240, 254-257, 266->exit
src/bastproxy/libs/records/rtypes/log.py                37     10      8      2  68.89%   42-43, 52-53, 57-58, 75->74, 79-82
src/bastproxy/libs/records/rtypes/muddata.py            72     40     24      3  40.62%   42-49, 58-60, 64, 68-70, 83-119, 125-138, 171-172, 182->191, 191->exit
src/bastproxy/libs/records/rtypes/networkdata.py       205    101     74     11  43.37%   58, 67, 93->95, 96, 97->exit, 108-110, 120-122, 143-145, 149->exit, 155, 165, 170, 175, 184-196, 205-223, 231-234, 238-246, 255-259, 290-293, 308, 317-318, 320-321, 353-360, 364-371, 376-377, 379-381, 386-400
src/bastproxy/libs/records/rtypes/update.py             81     23     34      9  65.22%   60, 81, 138, 142-148, 159, 161, 163, 170, 180->182, 183-186, 188-193, 197-198
```

**Direct tests only.** Command: `uv run pytest tests/libs/records -p no:randomly --cov=bastproxy.libs.records
--cov-branch --cov-report=term-missing -q` (24 passed, `coverage-narrow.txt`). The difference with the table above
is coverage that comes from other tests, incidentally:

| File | Whole suite | `tests/libs/records` only |
| :--- | --: | --: |
| `records.py` | 84.07% | 37.17% |
| `base.py` | 62.89% | 45.53% |
| `clientdata.py` | 33.09% | 33.09% |
| `log.py` | 68.89% | 66.67% |
| `muddata.py` | 40.62% | 40.62% |
| `networkdata.py` | 43.37% | 39.78% |
| `update.py` (not in the recommendations) | 65.22% | 43.48% |

The missing lines, by symbol (whole suite):

| Lines | Symbol | Why it matters |
| :--- | :--- | :--- |
| `records.py` 222-223 | `RecordManager.add`, the eviction `del` | **Eviction never runs in the suite.** #229 lives here. |
| `records.py` 62-68 | `RecordManager.end`, mismatched record | The warning that is never executed (#46). |
| `records.py` 212-214, 232, 245-246, 258 | UUID collision, `get_types`, `get_records`, `get_record` | Small. |
| `base.py` 170-176 | `BaseRecord.get_update` | #49 lives here. |
| `base.py` 307 | `check_for_change` | Dead and wrong (#49). |
| `base.py` 120 | `_am_locked_attribute_update` | The refusal update for a locked write (#48). |
| `base.py` 385-433 | `TrackedUserList.__setitem__`, `insert`, `append`, `extend`, locked branches | **The lock has no test for any of the four tracked mutators.** |
| `base.py` 557-576, 595, 599-601 | `BaseListRecord.color_lines`, `clean` (bytes, non-string) | Colouring and the error path. |
| `base.py` 135-137, 210, 232-244, 273, 291->293, 293->303 | `one_line_summary`, changed-attribute display, `format_children` (full), `get_formatted_details` branches | Display. |
| `base.py` 320-325, 497-521, 526, 531, 545, 638-663 | `__call__` re-entry; `BaseListRecord` summary, format, `is_io`, `replace` of a non-list; `BaseDictRecord` `TypeError`, summary, format | Display and small guards. |
| `clientdata.py` 41-166 | `ProcessDataToClient.__init__`, `add_client`, `exclude_client`, `can_send_to_client`, `_exec_` | **No test of the MUD to client step.** |
| `clientdata.py` 207-266 | `SendDataDirectlyToClient` constructor events, `can_send_to_client`, `_exec_` | The send step, the client filter. |
| `muddata.py` 83-138 | `ProcessDataToMud.seperate_commands` and `_exec_` | **No test of command splitting.** #231 lives here. |
| `networkdata.py` 184-196 | `NetworkDataLine.copy_attributes` | #231 lives here. |
| `networkdata.py` 205-246, 290-293 | `color_line`, `fix_double_command_seperator`, `format`, `add_preamble` | The format step that every sent line passes. |
| `networkdata.py` 353-400 | `NetworkData.__setitem__`, `insert`, `append` and `extend` | Conversion of `str` to `NetworkDataLine`, the `TypeError` and the parent rule (#47). |
| `log.py` 79-82 | `LogRecord._exec_` `except` branch | #235 lives here. |
| `update.py` and `updates.py` | n/a | Left out; #43 deletes them. |

The suite reaches `RecordManager.add` for creation only. No test passes 5,000 records of a type, so the
retention behaviour described in Q3 is unchecked. #239

---

## Q5: Where the Docs Disagreed With the Code

Corrected in [Record System](record_system.md) and [Data Flow](data_flow.md) in this change. A defect in the code
gets a draft issue, not a doc change that hides it, so the retention rule and the empty-record eviction are left
as the docs intend and described under [New Defects](#new-defects).

| Doc | Section | Said | Code does | Fixed here or issue |
| :--- | :--- | :--- | :--- | :--- |
| Record System | UpdateManager | `uid_mapping` is not trimmed, so a record keeps every update it ever had | `UpdateManager.add` removes the oldest mapping when the deque is full (**verified**: 1,105 adds leave 1,000 in `uid_mapping`; `out-q5.txt`) | Fixed |
| Record System | UpdateRecord, Tracking changes | "a copy of the data" for list and dict records | `NetworkData` updates carry no copy (**verified**); a dict record's "copy" is a clone of the record (#234) | Fixed |
| Record System | List and dict records | `pop`, `+=` and `*=` neither tracked nor stopped by `lock()` | Correct, but a locked `+=` or `*=` **changes the list and logs a refusal** (**verified**); `+=` also stores raw `str` items | Fixed |
| Record System | Parent-child relationships | `NetworkDataLine.add_parent()` keeps only one parent | It keeps one **by default** (`reset=True`); `reset=False` adds more (**verified**) | Fixed |
| Record System | Event records | The same `EventDataRecord` is reused for `data_list` | Also: a record passed by a caller to `raise_event` is **re-parented** to the new `ProcessRaisedEvent` (**verified**, #230) | Fixed (says so; defect is #230) |
| Record System | Record Types | One `ProcessRaisedEvent` row | Two classes exist; only `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` is imported (**verified**: `src/bastproxy/plugins/core/events/plugin/_process_event.py` is not the class used by the live events). The copy in `src/bastproxy/plugins/core/events/plugin/_process_event.py` and the `Event` copy in `src/bastproxy/plugins/core/events/libs/_event.py` are dead (**read**: nothing imports them but a `TYPE_CHECKING` block) | Fixed (note added); event audit Bug #1 |
| Record System | Known Gaps | #47 "lines appended to `NetworkData` get no parent" | True for `append`, `insert` and `data[i] = line` (an object); `extend` and the constructor do set it (**verified**) | Fixed |
| Data Flow | The record tree | Trees without trigger events; the split-command case not shown | Path 1 has two trigger events under `ev_to_client_data_modify` and its data record under the last; Path 2 hangs split lines under the original line (**verified**) | Fixed |
| Data Flow | How changes are tracked | "List and dict records also store a copy of their data" | `BaseListRecord` and `BaseDictRecord` do; `NetworkData` does not | Fixed |
| `src/bastproxy/libs/records/__init__.py` docstring | Public types | Names `EventDataRecord`, `ChangeRecord`, `ChangeManager` | `EventDataRecord` is defined in the events plugin; `ChangeRecord` and `ChangeManager` do not exist (**verified**: `out-q5.txt`) | #238 |
| Module headers | `Filename:` lines | `base.py` says `__init__.py`, `networkdata.py` says `dataline.py`, `update.py` says `change.py`, `clientdata.py` says `toclient.py` | Stale since the files were renamed (**read**) | #238 |

---

## Q6: Patterns and Anti-Patterns

"Keep" means the pattern fits. "Change" means worth an issue. `AttributeMonitor`, `UpdateRecord` and
`UpdateManager` are left out (#43). The plugin audit already covers the string service locator and hidden global state
for plugins ([that table](plugin_system_findings.md#q5-patterns-and-anti-patterns)); those rows add only what is
specific to records.

Commands run (output in `out-q6-greps.txt`):

- `grep -rnE "except( Exception)?:|suppress\(Exception" src/bastproxy/libs/records` found
  `log.py` line 79 and `update.py` line 58 (the second is in a class #43 deletes);
- `grep -rnE "os\.path|\+ ?['\"]/" src/bastproxy/libs/records` found nothing: no string paths;
- `grep -rn "^[A-Z_]* = " src/bastproxy/libs/records` found one module global, `RMANAGER` (`records.py` line 261);
- the other greps are in the output file.

| # | Pattern or anti-pattern | Where | Consistent? | Verdict |
| --: | :--- | :--- | :--- | :--- |
| 1 | **Import-time singleton, hard-wired**: `RMANAGER = RecordManager()` builds an `API` at import (**verified**: `out-q3e.txt`); `BaseRecord.__init__` calls it directly | `records.py` line 261; `base.py` | Yes, no record takes a manager | **Keep for now, decide in #79.** A private `RecordManager()` can be built, but no record registers with it (**read**; the probe had to call `add` by hand), and the benchmark registers three stand-in plugin APIs to run without the plugin system. The right shape depends on what #43 and #79 decide, so no issue yet. |
| 2 | **Subclassed built-in containers with mixed MRO**: `BaseListRecord(UserList, BaseRecord)`, `TrackedUserList(BaseRecord, UserList)`, `BaseDictRecord(BaseRecord, UserDict)`; `__eq__` and `__hash__` patched back | `base.py` | No: the two list classes disagree, and a record is **false when its data is empty** | **Change.** The truthiness is what caused #229; the same trap is in `if parent:` in `BaseRecord.__init__` (**read**). Fixed at the call sites in #229; the class design belongs to #43. |
| 3 | **Lock flags a caller can bypass**: `lock()`, `_am_lock_attribute`, `copy_attributes` unlocking `original_line` | `base.py`, `networkdata.py` | No (Q1: `line_type`, `originated`, `+=`, `pop`) | **Change**, owned by #47 and #48. Comments drafted. |
| 4 | **Class-level one-shot flag plus work in the constructor**: `_SETUP_EVENTS`, `setup_events()` | the four processing records | Yes (4 of 4, **verified**) | **Change** (#236). The first instance registers the events through a plugin API; after a plugin reload the flag is stale. |
| 5 | **`libs` calls `plugins` by string name**: 18 distinct `plugins.core.*` API names in `libs/records` | `rtypes/*.py`, `records.py` (`out-q6-greps.txt`) | Yes | **Keep, document.** The service-locator trade (plugin audit row 6). It is why `NetworkDataLine.noansi` fails without the colors plugin. |
| 6 | **Command pattern**: `__call__` times and pushes the record, subclasses implement `_exec_` | `BaseRecord.__call__` | Yes | **Keep.** `try/finally` keeps the stack right. The `starttimer` and `finishtimer` log records are noise (Q2). |
| 7 | **One class does everything**: identity, tree, update log, formatting, timing | `BaseRecord` (about 320 lines of the 680 in `base.py`) | n/a | **Keep until #43.** The update log and the attribute monitor are what #43 replaces; splitting now would be rework. |
| 8 | **Class-name string checks**: `parent.__class__.__name__ in [...]`, filters by class name | `NetworkDataLine.add_parent`, `RecordManager.get_children`, `BaseRecord.get_all_updates` | Yes | **Change** (#237), with row 9. A subclass of `NetworkData` silently fails the `add_parent` check. |
| 9 | **String-typed discriminators**: `originated`, `line_type`, `message_type`; `Info`/`Modify`/`Set Flag` flags (on #79) | `NetworkDataLine`, `BaseListRecord` | Yes | **Change** (#237). A typo such as `originated="clients"` is neither `fromclient`, `frommud` nor `internal`. The flag enum is on #79. |
| 10 | **Deferred imports to break cycles** | `base.py` line 599 (`LogRecord`), `records.py` lines 62 and 212 | Yes (3 sites, **verified**) | **Keep.** The cycle is by design: `libs/api` imports records and records build an `API` (api audit row 7). |
| 11 | **Catch-all `except Exception` that retries the same call** | `LogRecord._exec_` (`log.py` line 79) | n/a | **Change** (#235). **Verified**: with `level="notalevel"` the retry raises the same `AttributeError`. |
| 12 | **Silent returns** when a plugin is absent | `BaseListRecord.color_lines`, `NetworkDataLine.color_line` | Yes | **Keep.** Guarded by `api.exists`; Q1 shows no update is added, which is the only gap. |
| 13 | **Silent failure by dropping a write** | locked attributes and `TrackedUserList` | Yes | **Change**, owned by #48. |
| 14 | **Dead code**: `check_for_change` (raises `TypeError`, no caller) | `base.py` line 305 | n/a | **Change**, in the comment drafted for #49. |
| 15 | **Type-check escapes**: 2 `# type: ignore` in `networkdata.py`; `bastproxy.libs.records.*` is in the mypy `ignore_errors` override (`pyproject.toml` line 268) | `networkdata.py`, `pyproject.toml` | Whole package | **Keep, tracked by #6.** Do not widen it. |
| 16 | **Strings, not `Path`, for paths** | none found | n/a | **Fits.** |
| 17 | **Untested core paths** | Q4 | n/a | **Change** (#239). |
| 18 | **Per-record `API(...)` and unique owner IDs** | `BaseRecord.__init__`, `UpdateRecord.__init__` | Yes | **Change** (fixed in #232). Constructing the object is cheap since #199; the unique caller IDs are the cost. |
| 19 | **Cap by count, per type** | `RecordManager.add` | Yes | **Change** (#233). |

---

## New Defects

### RS-1: Evicting an empty record leaves it in `record_instances`

**Issue:** #229
**Location:** `src/bastproxy/libs/records/managers/records.py` `RecordManager.add` (line 221).

**Evidence (verified):** `if last_record := self.records[queuename].last_automatically_removed_item:` tests
the evicted record for truth. `NetworkData`, `LogRecord` and `BaseDictRecord` are containers, so one with no
data is false. With `max_records = 2` and an empty `NetworkData` as the oldest record:

```text
after adding empty1, full2, full3 (cap 2): empty1 evicted from queue: True | empty1 still in record_instances: True | bool(empty1): False
after adding full4: full2 evicted from queue: True | full2 still in record_instances: False
```

The same for an empty `LogRecord`. The record stays in `record_instances` for the life of the process, and keeps
its updates and its parents with it. An event raised with no arguments builds an empty `EventDataRecord`
(`event_args = {}` in `_api_event_raise`, **read**), so this is the common case for events, not a corner. The
suite never runs the eviction line (Q4: lines 222-223).

**Fix:** Test `is not None`. Audit `if parent:` in `BaseRecord.__init__` and any other truth test on a record.
Add a test that fills a type past `max_records` with empty and non-empty records.

### RS-2: A shared `EventDataRecord` is re-parented by every event that receives it

**Issue:** #230
**Location:** `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` `ProcessRaisedEvent.__init__`
(`event_data.parent = self; event_data.add_parent(self, reset=True)`); the caller that shares the record is
`_eventcb_check_trigger` in `src/bastproxy/plugins/core/triggers/plugin/_triggers.py`, which passes its own
`event_record` to the `beall` and `all` trigger events.

**Evidence (verified):** Path 1 and Path 5 in Q2. After one MUD line the `ev_to_client_data_modify`
`ProcessRaisedEvent` has no `EventDataRecord` child, and its data is a child of the `triggers_all` event:

```text
     |-> ProcessRaisedEvent   f146829531324aa2b7b0aab9f564f3c4 38.97ms ev_to_client_data_modify 1
     |   |-> ProcessRaisedEvent   4e503986ca3d4abe8f7e0e0de915d24d 2.48ms event_t_plugins.core.triggers_beall 1
     |   |-> ProcessRaisedEvent   2d62fa7121d040d480b54dcc20f8aedb 2.34ms event_t_plugins.core.triggers_all 1
     |       |-> EventDataRecord      ed030cfe9494475486f79456b23d0e1c ev_to_client_data_modify
```

The `beall` event shows no data at all. Any debug view that follows the tree to find "the data of this event" gets
the wrong event.

**Fix:** Give a reused data record several parents (`reset=False`) when it is passed in, or wrap it in a new
record for the inner event. Decide with #79 whether the data record is part of the tree at all.

### RS-3: Split commands are children of the line that was replaced

**Issue:** #231
**Location:** `src/bastproxy/libs/records/rtypes/muddata.py` `ProcessDataToMud.seperate_commands`;
`src/bastproxy/libs/records/rtypes/networkdata.py` `NetworkDataLine.copy_attributes` and
`NetworkDataLine.add_parent`.

**Evidence (verified):** Path 2 in Q2, a client line `say a|say b`:

```text
split lines parent/parents: [('say a', 'ProcessDataToMud:4b4ef7', ['NetworkDataLine:e87aa7'], 'NetworkDataLine:e87aa7'), ('say b', 'ProcessDataToMud:4b4ef7', ['NetworkDataLine:e87aa7'], 'NetworkDataLine:e87aa7')]
```

The pieces have `parent` set to the `ProcessDataToMud` (the active record) and `parents` set to the original
line, which `NetworkData.__setitem__` replaced and which is no longer in the `NetworkData`. The tree prints
the original line under the `NetworkData` and the pieces under it, so the tree shows data that was never sent.
Rule (d) fails for both pieces. `NetworkData.__setitem__` and `insert` set no parent for a `NetworkDataLine`
object (#47).

**Fix:** Have `seperate_commands` give each piece the `NetworkData` as its parent (as `extend` does), drop the
`add_parent(self)` call from `copy_attributes`, and keep `split_from` for the link to the original. Add a test for
`seperate_commands` (Q4: lines 83-119 are untested).

### RS-4: API statistics grow without bound with record traffic

**Fixed in #232:** records use their class name as owner ID. The text below is the audit record.

**Issue:** #232
**Location:** `src/bastproxy/libs/records/rtypes/base.py` `BaseRecord.__init__` (the default `owner_id` and
`API(owner_id=...)`), `src/bastproxy/libs/records/rtypes/update.py` `UpdateRecord.__init__`;
`src/bastproxy/libs/api/_apistats.py` `APIStatItem.add_call` (`detailed_calls`).

**Evidence (verified):** Q3, "API stats grow with every record": 371 new distinct caller IDs per round of 15
lines, none repeated, 65.0 MiB in the stats dicts after 1,500 rounds.

```text
distinct caller keys before: 12143 after 20 rounds: 19564 new: 7421 per round: 371.05
after 40 rounds: 26984 -> per round 371.025
do keys repeat between rounds? new keys in rounds 20-40: 7420
```

#196 made removal prune the stats for an unloaded plugin; nothing prunes the stats for a record. The growth is
proportional to traffic and not capped by `max_records`.

**Fix:** Do not use a per-record UUID as an API owner. Use the class name or the creating owner for the API object, or
collapse the caller ID to its prefix in `detailed_calls`. Add a regression test that creates records and counts the
keys.

### RS-5: Memory is capped by record count per type, not by size

**Issue:** #233
**Location:** `src/bastproxy/libs/records/managers/records.py` `RecordManager.add` (`max_records`).

**Evidence (verified for the part measured):** Q3. Heap growth of about 0.66 MB per round of 15 lines up to
1,139 MB at 1,500 rounds, with `NetworkData` and `ProcessDataToClient` 30% full. 17,516
`NetworkDataLine` records were evicted from the store and alive, held by their stored `NetworkData`. The point
where growth stops (every holding type at 5,000) was not reached; the projection is **unverified**.

**Fix:** Decide the budget in the #79 ADR, then enforce it as bytes or as one global cap, and make a holding record
(`NetworkData`, `ProcessDataToClient`) release its children when it is evicted. **A benchmark in `tests/benchmarks/`
must exist before any optimisation** (perf-change Step 1); the figures here are the baseline.

### RS-6: `BaseDictRecord.addupdate` stores a clone of the record

**Issue:** #234
**Location:** `src/bastproxy/libs/records/rtypes/base.py` `BaseDictRecord.addupdate` (`data = self.copy()`).

**Evidence (verified):**

```text
type(copy): BaseDictRecord | same uuid: True | same updates object: True | copy is registered: False | registered one is original: True
updates on d: 1 | update[0].data type: BaseDictRecord | is a BaseDictRecord: True
```

`UserDict.copy()` of a subclass is `copy.copy(self)`: a second record with the same UUID, the same updates
and the same `parents`. Every update of a dict record holds one, so every `EventDataRecord` has
2 to 3 of them (9,211 clones after 1,500 rounds, Q3), and `gc` counts them as records that are not in the store.

**Fix:** Store `dict(self.data)` (or `self.data.copy()`), as `BaseListRecord.addupdate` stores `self.data[:]`.
Check the debug commands that print `update.data` first.

### RS-7: `LogRecord._exec_` retries the call that failed

**Issue:** #235
**Location:** `src/bastproxy/libs/records/rtypes/log.py` `LogRecord._exec_` (lines 71-82).

**Evidence (verified):** With a level the logger does not have, the retry in the `except` block repeats the same
call and raises the same error:

```text
LogRecord(level='notalevel', sources=['q3e'])() RAISED AttributeError 'Logger' object has no attribute 'notalevel'
```

With no `sources` the method does nothing (#46). If a handler raised after emitting, the retry would emit again
(**read**, not run).

**Fix:** Catch what can fail (`AttributeError` from an invalid level) or nothing. Log a failure once through
the stdlib `logging` module. Add a test for the `except` branch (Q4: lines 79-82).

### RS-8: Event registration happens in record constructors behind a class flag

**Issue:** #236
**Location:** `ProcessDataToClient`, `SendDataDirectlyToClient`, `ProcessDataToMud` and `SendDataDirectlyToMud`
(`setup_events` and `_SETUP_EVENTS` in `clientdata.py` and `muddata.py`).

**Evidence (verified):** all four define `_SETUP_EVENTS = False` in the class body, and each constructor calls
`self.setup_events()`, which calls `plugins.core.events:event.add` the first time (`out-q3e.txt`). The
constructor therefore needs the events plugin, which makes the record unusable in a unit test without a stand-in
(**read**). A reload of the events plugin does not reset the flag (**read**).

**Fix:** Register the four events once from the events plugin or a module function that the loader calls, and
drop the flag.

### RS-9: String-typed `originated`, `line_type` and `message_type`, and class-name checks

**Issue:** #237
**Location:** `NetworkDataLine.__init__`, `is_io`, `internal`, `fromclient`, `frommud`, `add_parent`
(`networkdata.py`); `BaseListRecord.message_type` (`base.py`); `RecordManager.get_children`
(`records.py`).

**Evidence (read, with the Q1 output):** The values are compared with string literals (`"mud"`, `"client"`,
`"internal"`, `"IO"`, `"COMMAND-TELNET"`). `line_type`, `originated` and `split_from` are neither monitored
nor locked (Q1), so the values can change after `lock()`. `add_parent` accepts a parent by
`__class__.__name__`, which a subclass fails.

**Fix:** Use `enum.StrEnum` for the three fields (the update-flag enum is already on #79) and `isinstance` for the parent
check. The deferred imports (Q6 row 10) are why the class-name check exists; a `TYPE_CHECKING` import or a
shared base for "network data" solves both.

### RS-10: Stale module headers and package docstring

**Issue:** #238
**Location:** `src/bastproxy/libs/records/__init__.py` (docstring), and the `Filename:` line of
`base.py`, `networkdata.py`, `update.py`, `clientdata.py`.

**Evidence (verified):** The docstring names `EventDataRecord`, `ChangeRecord` and `ChangeManager`; none is
exported, and the last two do not exist. The headers say `__init__.py`, `dataline.py`, `change.py` and
`toclient.py`.

**Fix:** Rewrite the docstring from `__all__`; correct the four headers. No behaviour change.

### RS-11: No tests for the processing step, command splitting, eviction or the lock

**Issue:** #239
**Location:** Q4 table: `records.py` 222-223; `muddata.py` 83-138; `clientdata.py`
41-166 and 207-266; `networkdata.py` 184-246 and 353-400; `base.py` 170-176, 385-433, 557-576;
`log.py` 79-82.

**Evidence (verified):** The coverage tables in Q4.

**Fix:** Add tests, in this order: eviction past `max_records` (with #229); the lock on each tracked
`TrackedUserList` mutator; `seperate_commands` and `copy_attributes` (with #231); `NetworkData`
conversion and parent rules; the `_exec_` of the four processing records against stand-in plugin APIs, as the
benchmark does; `LogRecord._exec_` failure. `update.py` and `updates.py` are out of scope.

---

## Other Observations

- **Duplicate event classes.** `src/bastproxy/plugins/core/events/plugin/_process_event.py` and
  `src/bastproxy/plugins/core/events/libs/_event.py` define a `ProcessRaisedEvent` and an `Event` that nothing
  imports (**verified** by `grep`: only a `TYPE_CHECKING` block names them). The live ones are in
  `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` and `src/bastproxy/plugins/core/events/plugin/_event.py`. This is Bug #1 in
  [Event System Findings](event_system_findings.md); no issue is drafted here.
- **Timer log records.** Two `LogRecord`s per executed record (`starttimer`, `finishtimer`) have no parent and
  take slots from the `LogRecord` store: 2 of the 21 `LogRecord`s created for the two-line batch in Path 1. A command
  created 62 `LogRecord`s in Path 3 (**verified**). The `LogRecord` store filled in the first 250 rounds of the
  memory run, so debug-level logs push older ones out quickly.
- **`was_sent` is monitored but not locked** on purpose: the network code sets it after sending (Q1).
- **`trigger.register` unpacks its keyword dict.** `_api_trigger_register` in
  `src/bastproxy/plugins/core/triggers/plugin/_triggers.py` passes `*kwargs` to `event.register`, which unpacks the
  keys as positional arguments (**read**, not run; outside this audit's scope, for the triggers audit).
- **Tree queries are debug-only** (Q3), so the 98 ms query on a full store matters only with `plugins.debug.records`.
- **Properties that call plugin APIs** (`noansi`, `colorcoded`, `escapecolor`, `add_preamble`) raise
  `APINotFoundError` when the plugin is absent (**verified** for `add_preamble`:
  `plugins.core.proxy:preamble.color.get is not in the api`; the others **read**).
