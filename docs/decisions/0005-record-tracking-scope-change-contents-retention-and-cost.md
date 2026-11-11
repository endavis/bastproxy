---
title: "ADR-0005: Record tracking: scope, change contents, retention and cost"
description: Records track text lines and decoded protocol messages with old value, new value, actor, time and parent; data holders become tracked containers, retention keeps the last N root trees, and capture costs at most 50 us per line created and 20 us per change with stacks off.
date: 2026-11-09
audience:
  - contributors
tags:
  - adr
  - records
---

# ADR-0005: Record tracking: scope, change contents, retention and cost

## Status

Accepted

## Context

The goal is to track all data that moves through the proxy and every change to it. That goal has no written requirement. Nothing says what is recorded, how long it is kept, or what it may cost. Issue #43 (replace the attribute monitor with pydatatracker) needs those answers before it can be judged.

### Measurements

Measured on base commit `f802358`, pydatatracker 0.2.0, Python 3.12.12. A scratch script creates 1,500 lines (`line`, `originated`, `line_modified`; the pydatatracker variants monitor all three) and then changes `.line` once on each, under `tracking_actor("bench")`. Medians of 5 runs. Memory comes from `tracemalloc` over one run (created and changed lines).

```
Python 3.12.12, 1500 lines x 5 runs, median
plain object                         create      0.1 us  change     0.0 us  memory    0.1 KiB/line
bastproxy NetworkDataLine            create     95.9 us  change    42.2 us  memory   10.2 KiB/line
pdt TrackedAttr (defaults)           create     20.7 us  change     6.0 us  memory    6.6 KiB/line
pdt stack on                         create     35.3 us  change     6.4 us  memory   15.2 KiB/line
pdt snapshots on                     create     22.0 us  change     6.4 us  memory    6.6 KiB/line
pdt no init entry, max_changes=10    create     18.5 us  change     6.0 us  memory    5.9 KiB/line
```

- The bastproxy runs create 9,000 `NetworkDataLine` records in total. That is past the 5,000-per-class cap, so they include eviction.
- These figures replace the issue body's (424 us and 228 us, Python 3.14, before #199) and #43's (117 us and 18 us, pydatatracker 0.1.0). Neither older set comes from the same harness, so they are not comparable with these.
- pydatatracker 0.2.0 has stack capture off by default. It takes the actor from a context variable (`tracking_actor`), and it caps history with `tracking_max_changes`.
- ADR-0001 terminates protocols at the proxy and raises one event per decoded message. Recording protocol messages as decoded records, not raw bytes, is consistent with it.

### What the audit found

The record audit (#106, [Record System Audit Findings](../claude/record_system_findings.md)) found that one record class does three jobs:

- a debug trace (the tree, the stacks and the updates);
- a data holder (`NetworkData` holds lines, `LogRecord` holds text);
- an executable step (`BaseRecord.__call__`).

Tracking and retention need different rules for each job.

### The retention problem

- Retention is 5,000 records per class. It counts records, not size.
- Measured: about 0.66 MB per round of 15 MUD lines, and no plateau was reached by 1,500 rounds.
- A record held by a stored holder outlives eviction.
- A unique owner ID per record grew the API statistics without bound. #232 fixed this by using the class name as the owner ID.

### Options considered

**Point 3, the record's jobs.**

- Rejected: keep one class doing all three jobs, with different rules per job. It is a smaller change, but it keeps the single class the audit names as an anti-pattern (Q6).

**Point 4, `LogRecord`.**

- Rejected: keep `LogRecord` as a tracked record. Its changes are formatting steps (`color_lines`, `format`) applied on the way out, and #43's plan already moves log output to plain `logging`.

**Point 6, retention.**

- Rejected: a byte budget. Python cannot measure deep size cheaply; `sys.getsizeof` is shallow.
- Rejected: an update cap alone, with today's per-class count. It leaves the unbounded growth and the holder problem in place.

**Point 7, cost targets.**

- Rejected: 30 us per line created and 10 us per change. This is tighter than the decided numbers.
- Rejected: no hard number. Without one the benchmark has nothing to fail against.

## Decision

The repo admin decided on 2026-11-09:

1. **Scope:** text lines in both directions, internal lines, and protocol messages (GMCP, MSDP, MSSP and telnet negotiation) as decoded records. Protocol messages arrive after #43 (#83). Raw wire bytes are out of scope.
2. **A change record holds:** old value, new value, actor, time and parent record. The actor comes from a context variable, not a stack walk. Stacks are captured only in debug mode or on request (#81).
3. **Split the record's jobs.** Data holders (lines, event data, command arguments) become tracked containers (pydatatracker, per #43). Processing records stay tree nodes that reference them.
4. **`LogRecord` leaves the record system** and uses plain `logging`, per #43. Log lines get no change history. Every data holder that remains is tracked. The lock is enforced on every mutation, including `pop`, `sort` and `+=`.
5. **Data records may have several parents** (design direction for #230). A shared node survives while any tree holding it is live.
6. **Retention:**
    - keep the last N root trees, where N is configurable, and evict each tree whole, children included;
    - cap each record's changes with `tracking_max_changes`;
    - no persistence across restarts. Records stay in memory only (amended by #82, which was not pursued; the network data log keeps the raw I/O).
7. **Cost targets, stacks off:** at most 50 us per line created and 20 us per change, measured by a benchmark in `tests/benchmarks/`.
8. **Enums:** `StrEnum` for update flags and for `originated`, `line_type` and `message_type` (#237). `StrEnum` keeps the stored values readable.
9. **Owner ID:** the class name, already done in #232. Whether records keep API stats at all stays open.
10. **Dependency direction:**
    - Records may call plugin APIs to do their work and to format output.
    - They do not register events in constructors. Registration moves to startup (#236).
    - They read the event stack and the current command from context variables that the events and commands plugins set. They do not call the API when they are created.

## Rationale

- **Scope (1):** one event per decoded message is already how ADR-0001 handles protocols, so decoded records fit the existing design. Raw bytes would add volume without adding a record anyone reads.
- **Change contents (2):** in the measurements, turning stacks on raised memory from 6.6 to 15.2 KiB per line. Stacks are the largest allocation seen in the audit. A context-variable actor gives the same "who changed it" answer without a stack walk.
- **Split jobs (3, 4):** the audit shows tracking covers only some attributes and four `NetworkData` methods today. Making every data holder a tracked container, and keeping processing records as plain tree nodes, gives each job one rule. Locking every mutation closes the gap where a locked list still changed through `pop`, `sort` and `+=`.
- **Parents (5):** `EventDataRecord` is re-parented by every event that receives it, and `CmdArgsRecord` has one parent. A tree with several parents describes that without losing earlier links.
- **Retention (6):** evicting whole trees fixes holders keeping evicted children alive. `tracking_max_changes` bounds each record's history. A count of trees can be set and tested, which a byte budget cannot.
- **Cost (7):** the bastproxy `NetworkDataLine` measured 95.9 us to create and 42.2 us per change. The pydatatracker default measured 20.7 us and 6.0 us. 50 us and 20 us leave headroom over the pydatatracker figures. That headroom is a judgment, not a measurement.
- **Enums (8):** the update flags (`Modify`, `Set Flag`, `Info`) and the discriminators (`originated`, `line_type`, `message_type`) are free-form strings today. A typo passes silently and display code cannot filter on a closed set.
- **Dependencies (10):** the audit found `libs/records` calling plugin APIs by string name and registering events from constructors. Moving registration to startup and reading context variables removes the creation-time coupling without forbidding the calls records need.

## Consequences

- #43 is judged against points 4, 6 and 7 in a comment on #43.
- #43 must now:
    - drop `LogRecord` from the record system;
    - adapt the data holders to tracked containers;
    - take the actor from a context variable;
    - follow the retention design in point 6.
- `tests/benchmarks/test_bench_networkdataline.py` (#80) measures today's `NetworkDataLine`. An implementation of points 2 and 7 is measured against the targets with it, or with a benchmark that replaces it.
- Whether records keep API stats stays open (point 9).
- Implemented by existing issues:
    - #81: stacks configurable;
    - #82: persistence, not pursued;
    - #83: protocol and negotiation records;
    - #230: several parents;
    - #233: retention;
    - #236: event registration;
    - #237: enums;
    - #47 and #48: the lock and in-place mutations.

## Related Issues

- #79 (this decision)
- #43 (replace the attribute monitor with pydatatracker)
- #246 (dict records, slice 2)
- #247 (`LogRecord` replaced by plain logging, slice 3)
- #248 (processing records off `AttributeMonitor`, slice 4; implements points 2 and 10 in [Record System](../claude/record_system.md#updates))
- #249 (retention by root tree, slice 5; implementation in [Record System: RecordManager](../claude/record_system.md#recordmanager))
- #47, #48 (lock and in-place mutations)
- #80 to #85 (follow-ups filed with #79; #80, #84 and #85 are closed; #82, persistence, was not pursued)
- #106 (the record audit)
- #229 to #239 (the audit findings)
- #241
- #83 (telnet negotiation records; implementation in [Record System: Telnet negotiation records](../claude/record_system.md#telnet-negotiation-records))
- #237 (enums; implements point 8 in [Record System](../claude/record_system.md#updates); message_type was removed in #43)

## Related Documentation

- [Record System](../claude/record_system.md)
- [Record System Audit Findings](../claude/record_system_findings.md)
- [Data Flow](../claude/data_flow.md)
- [Logging System](../claude/logging_system.md)
- [ADR-0001: Terminate MUD telnet protocols at the proxy](0001-terminate-mud-telnet-protocols-at-the-proxy.md)
