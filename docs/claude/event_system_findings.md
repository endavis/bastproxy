---
title: Event System Analysis and Findings
description: Audit of the event system - the status of the earlier findings, plugin unload, priority ordering and failing callbacks, cost, test coverage, docs accuracy and patterns, with defects and a patterns review
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - events
  - review
---

# Event System Analysis and Findings

**Date:** 2026-11-10
**Analyzer:** Claude Sonnet 5.5
**Scope:** The events plugin in `src/bastproxy/plugins/core/events/` (its `libs/` and `plugin/` packages, including
`src/bastproxy/plugins/core/events/plugin/_event.py` and `src/bastproxy/plugins/core/events/plugin/_events.py`) and `RegisterToEvent`: the status of the
earlier findings, what an unload leaves behind, priority ordering and a failing callback, cost, test
coverage, docs accuracy and patterns (audit issue #107). Compared against
[Event System](event_system.md). Base commit `b7f15da`.

The earlier page held 19 numbered findings, four alternative libraries, an implementation plan, three
migration strategies and a testing strategy (1,949 lines at `da2ad82`). That text is replaced by the
status table in Q1. Read the old text with
`git show da2ad82:docs/claude/event_system_findings.md`.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [Status of the Known Items](#status-of-the-known-items)
4. [Q1: Which Old Findings Still Hold?](#q1-which-old-findings-still-hold)
5. [Q2: What Does an Unload Leave Behind?](#q2-what-does-an-unload-leave-behind)
6. [Q3: Priorities, Ordering and a Failing Callback](#q3-priorities-ordering-and-a-failing-callback)
7. [Q4: What Does an Event Cost?](#q4-what-does-an-event-cost)
8. [Q5: What Is Untested?](#q5-what-is-untested)
9. [Q6: Patterns and Anti-Patterns](#q6-patterns-and-anti-patterns)
10. [Where the Docs Disagreed With the Code](#where-the-docs-disagreed-with-the-code)
11. [New Defects](#new-defects)
12. [Other Observations](#other-observations)

---

## Executive Summary

The event system does what [Event System](event_system.md) says for the common case: callbacks run
lowest priority first, one failing callback is logged and does not stop the others, an unload leaves no
registration behind, the history of raises is bounded, and the cost of a raise is small next to the
network work around it. The rest is eleven defects, found by running the code (eight) or reading it (three),
and a page that was behind the code in several places.

- **Priorities are less reliable than the docs say** (#278, #280, #275). A `@RegisterToEvent(priority=...)`
  is stored at 50, whatever it asks for; priority 0 is stored at 50; and a callback registered during a
  raise can be dropped from that raise (Q3).
- **The registration check never matches** (#279). The same function registered twice runs twice, and a
  plugin's disconnect handler grows its registrations by one per call (Q2d, Q3c).
- **A raise from inside the same event resets the outer raise** (#281): done flags are cleared, so callbacks
  run twice (Q3f).
- **Unload is clean for callbacks and plugin instances** (Q2, **verified**, #95 and #127 hold); the `Event`
  objects themselves are never removed, and `event.get` creates one for any name, so the `raise` command
  never reports an unknown event (#283).
- **Two smaller bugs**: `raise_event` with data that is not a dict raises `AttributeError` from its own
  error log (#276), and an `async def` callback never runs and is not reported (#277).
- **Cost** (Q4): a raise costs about 70 to 100 us before any callback; a `data_list` raise costs about 34 us
  per item. No performance defect.
- **Tests** (Q5): the events plugin is 36.0% covered; the register, unregister and unload half has no test
  (#282).

**Key Findings:**

- 11 new defects (ES-1 to ES-11). ES-1 to ES-3 are the Q1 rows for Design #4, Design #2 and Bug #4; ES-4 to
  ES-11 are under [New Defects](#new-defects). All are filed (#275 to #285).
- Of the 19 numbered old findings, 3 are fixed (Bug #1 to #3), 1 is obsolete (Design #1, the claim was
  wrong), 4 are open and filed or tracked (Bug #4, Design #2, #4 and #5), and 11 are not pursued, as is the
  advice section.
- The code disagreed with the docs in 14 places; the page was corrected for all of them (Where the Docs
  Disagreed). Two code comments are wrong and are listed under Other Observations.
- The new benchmark is `tests/benchmarks/test_bench_event_raise.py`; run it with `doit benchmark`.
- The old 1,949-line page is replaced by the Q1 table; read it with
  `git show da2ad82:docs/claude/event_system_findings.md`.

---

## How This Was Verified

Claims below are tagged **verified** (run against the code, output saved), **read** (from reading the
code, not executed) or **unverified**.

Verification used throwaway scripts, deleted afterwards and not part of the repository. Python ran with
`BASTPROXY_HOME` set to a scratch directory.

- Q1 (pass A): a script that builds `Event` objects directly, with stand-in `setting.get` and
  `event.unregister` APIs as in `tests/plugins/core/events/test_event_unload_retention.py`, and
  checks the old bugs one by one (`out-q1_old_findings.txt`, `out-q1b_chain.txt`). Greps for
  `EventArgsRecord` and for threading primitives (`out-grep-eventargs.txt`, `out-grep-threads.txt`).
  The existing events tests were run: 27 passed (`out-pytest-events.txt`).

- Q2 (pass B): a script that boots the real plugin system in-process (`PluginLoader().load_plugins_on_startup()`,
  then `startup` set to False as `bastproxy` does), loads a throwaway user plugin from
  `$BASTPROXY_HOME/plugins` (it imports as `userplugins.<package>.<name>`), and records every event's
  registrations for the plugin before load, after load, after unload, after a load again and after
  `plugin.reload` (`out-q2_unload.txt`). Follow-up scripts cover a core plugin, the repeated
  disconnect registration and what keeps the unloaded modules alive (`out-q2b_core_and_leaks.txt`,
  `out-q2c_module_alive.txt`). The throwaway plugin was deleted afterwards.
- Q3 (pass B): scripts that build `Event` objects directly with stand-in APIs (`out-q3_order.txt`) and a
  boot of the real system to read the live run order (`out-q3g_live_order.txt`).

- Q4 (pass C): the new benchmark `tests/benchmarks/test_bench_event_raise.py`, run with
  `uv run pytest tests/benchmarks/test_bench_event_raise.py --benchmark-enable --benchmark-only -v`
  (`out-bench-event-raise.txt`). Environment: Python 3.12.12, pytest-benchmark 5.3.1 (warmup on, GC
  disabled), Linux 6.17.13-2-pve, 12th Gen Intel Core i7-12650H.
- Q5 (pass C): `uv run doit coverage` (`coverage.txt`: 4,805 passed, 13 skipped) and
  `uv run pytest tests/plugins/core/events --cov=bastproxy.plugins.core.events --cov-branch --cov-report=term-missing -q`
  (`coverage-narrow.txt`: 27 passed).

- Q6 (pass D): greps scoped to `src/bastproxy/plugins/core/events` (`out-q6-grep-catchall.txt`,
  `out-q6-grep-paths.txt`, `out-q6-grep-globals.txt`, `out-q6-grep-api.txt`, `out-q6-grep-ignores.txt`) and a
  read of the package files. The docs pass compared `docs/claude/event_system.md` with the live code by reading,
  plus two greps (`out-docs-checks.txt`).

---

## Status of the Known Items

Every item in the issue's list, with its current state.

| Item from the issue | Status | Where |
| :--- | :--- | :--- |
| #241: remove the dead duplicate `ProcessRaisedEvent` and `Event` classes | **Closed.** Confirmed: only one of each is in the package (**read**, Q1 Bug #1). The page's file list and excerpts now match. | #241 |
| #252: `current_callback` not cleared between items of a `data_list` raise | **Closed, and holds** (**verified**, Q3e: with `data_list` every item ran every callback and the state was clean afterwards). | #252 |
| #246: dict data records on pydatatracker | **Closed.** The `EventDataRecord` excerpt and bullets in [Event System](event_system.md) match the code (**read**). | #246 |
| #236: record events registered once | **Closed.** `RECORD_EVENTS` is registered in `_phook_initialize` (**read**); the page already said so. | #236 |
| #248: processing records off `AttributeMonitor` | **Closed.** The actor of a raise and the `tracking_actor` around each callback are described in the page (**read**). | #248 |
| #127: event history kept unloaded plugins alive | **Closed, and holds** (**verified**, Q2b: the plugin instance is freed after an unload and `gc.collect()`). | #127 |
| #153: bound `raised_events` | **Closed, and holds** (**verified**, Q1 Bug #3: 25 raises leave 10 entries). | #153 |
| #95: plugins imported twice | **Closed, and holds for events** (**verified**, Q2a: the owner matches and no second copy is in `sys.modules`). | #95 |
| Strictness of the typing (Design #5) | **Open**, comment on #6. | #6 |

---

## Q1: Which Old Findings Still Hold?

Each row is one numbered item of the old page. Status is **Fixed** (with the commit and a check against
the current code), **Open** (an issue exists or is filed), **Obsolete** (the finding was wrong or
no longer applies) or **Not pursued** (no issue, with the reason). The old text is at `da2ad82`.

| # | Old finding | Status | Evidence | Issue |
| :--- | :--- | :--- | :--- | :--- |
| Bug #1 | Two identical `ProcessRaisedEvent` classes | **Fixed** | Deleted by 27a4e08 (PR #259). `ProcessRaisedEvent` is now only in `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` and `Event` only in `src/bastproxy/plugins/core/events/plugin/_event.py` (**read**: `find` of the package lists no `_process_event.py` or libs/_event.py (deleted)). | #241 |
| Bug #2 | `EventArgsRecord` renamed to `EventDataRecord` but not everywhere | **Fixed** | Live code was fixed by b4f0427; the `src/bastproxy/libs/records/__init__.py` docstring by 3a9517d (PR #263); the second copy of the files was deleted by 27a4e08. `grep -rn EventArgsRecord src tests docs` finds nothing outside this page (**verified**, `out-grep-eventargs.txt` is empty). | #238, #241 |
| Bug #3 | Unbounded `raised_events` history | **Fixed** | 8a12c75 (PR #159). 25 raises of one event leave 10 entries in an `OrderedDict`, and `raised_count` is 25 (**verified**, `out-q1_old_findings.txt`). `tests/plugins/core/events/test_event_raised_history.py` covers the cap, eviction, a cap of 0, a lowered cap and the setting (27 tests in the package pass, **verified**, `out-pytest-events.txt`). Whether an unloaded plugin is freed is Q2. | #153, #127 |
| Bug #4 | `AttributeError` in `raise_event` when the data is not a dict | **Open** | `Event.raise_event` still formats `self.called_from`, and `Event` has no such attribute. `raise_event("not a dict", "probe")` raises `AttributeError: 'Event' object has no attribute 'called_from'` (**verified**, `out-q1_old_findings.txt`). #253 replaced `LogRecord` with `log_to` and kept the bug. No test covers the branch (**read**: `grep` of `tests` for the message finds nothing). The old fix (use `actor`) is right. | #276 |
| Design #1 | `except Exception` catches `KeyboardInterrupt` and `SystemExit` | **Obsolete** | The claim is wrong: `except Exception` does not catch them. A callback that raises `KeyboardInterrupt` or `SystemExit` propagates out of `raise_event` (**verified**, `out-q1_old_findings.txt`). The handler still swallows every other exception, which Q3 and Q6 cover. | |
| Design #2 | No async support | **Open** | Callbacks are called as `self.func()` and the result is dropped (**read**, `src/bastproxy/libs/callback.py` `Callback.execute`). An `async def` callback registers without a warning, never runs, and only Python warns `coroutine 'A.cb' was never awaited` (**verified**, `out-q1_old_findings.txt`). The old page's proposal (an async event system) is a feature and is not pursued; the silent failure is filed. | #277 |
| Design #3 | No thread safety | **Not pursued** | Nothing in `src` imports `threading`, creates a `Lock` or calls `run_in_executor` (**verified**, `out-grep-threads.txt` is empty); events are raised from the asyncio thread only. | |
| Design #4 | `priorities_done` grows with duplicates; the loop is inefficient | **Open** | The duplicates and the O(n) `in` check are real but cost nothing at the size of a priority list (**read**, `_raisedevent.py` `_exec_once`). The real fault is next to it: `found_callbacks` is overwritten by every priority instead of OR-ed, so a pass ends when the last priority runs nothing. A callback registered at a lower priority during the second pass never runs in that raise: with callbacks at 50 and 99, a callback added at 10 runs, but one added at 5 from inside it does not (**verified**, `out-q1b_chain.txt`: order `['cb50', 'cb99', 'cb10']`). The old recommendation (`set`, `if ... found_callbacks = True`) fixes it. Q3d extends this. | #275 |
| Design #5 | Weak type hints | **Open** | Half the finding is wrong: `X \| None` is the current syntax, and `Optional` is not an improvement. The gaps are real: `raise_event(data_list, key_name)`, `getownerregistrations`, `removeowner`, `isregistered`, `unregister` and `raise_priority` have unannotated parameters, and `priority_dictionary` has no annotation (**read** for the attribute; the parameters **verified**, `out-q1_old_findings.txt`). mypy does not check the package: `bastproxy.plugins.core.*` is under `ignore_errors` in `pyproject.toml` (**verified**, `out-pyproject-mypy.txt`). Covered by the strictness tracking issue. | #6 |
| Enhancement #1 | Event history management (a history class, search, export) | **Not pursued** | The part that mattered, a bounded history, is Bug #3. A richer history has no known user: [Event System](event_system.md) "Event History" says the debug records plugin reads `RMANAGER`, not `raised_events` (**unverified**, repeated from that page). | |
| Enhancement #2 | Wildcard event subscription | **Not pursued** | A feature with no caller; no plugin needs it. | |
| Enhancement #3 | Event middleware and interceptors | **Not pursued** | A feature with no caller; `tracking_actor` and the record tree already identify who ran. | |
| Enhancement #4 | Performance monitoring | **Not pursued** | `raised_count` per event and `execute_time_taken` per raise exist (**read**, `src/bastproxy/plugins/core/events/plugin/_event.py`, `src/bastproxy/libs/records/tracking.py`); Q4 measures the cost instead. | |
| Enhancement #5 | Event replay for debugging | **Not pursued** | A feature with no caller. [Event System](event_system.md) says `RMANAGER` keeps each raise while its tree is retained (**unverified**). | |
| Enhancement #6 | Event schema validation | **Not pursued** | `arg_descriptions` document the keys; enforcing them would break every raiser that adds a key. | |
| Refactoring #1 | Extract a `PriorityManager` | **Not pursued** | Moving the same code; the defects in it (Design #4) are filed on their own. | |
| Refactoring #2 | Dataclass for `Event` configuration | **Not pursued** | Four parameters, two optional; no pain. | |
| Refactoring #3 | `EventError` exception hierarchy | **Not pursued** | The handler logs and continues by design (Q6); an exception type changes nothing it does. | |
| Refactoring #4 | Protocols for the callback and the event | **Not pursued** | One implementation of each; a protocol adds a type with no second user. | |
| Advice | Alternative libraries (blinker, PyPubSub, python-dispatch, a custom asyncio system), implementation phases, migration strategies and a testing strategy | **Not pursued** | A replacement is a design decision for an ADR, not a defect. The testing advice is replaced by Q5, measured. The phases and migrations refer to bugs now fixed or filed above. | |

---

## Q2: What Does an Unload Leave Behind?

A plugin leaves a registration on an event in two ways: a decorated `_eventcb_*` method (registered by
the events plugin when `ev_plugin_loaded` is raised) and a runtime `event.register` call. `ev_plugin_unloaded`
makes the events plugin call `event.unregister.for.owner`, which runs `Event.removeowner` on every event.
This section checks that the cleanup works, that events stay bounded and that nothing keeps the plugin alive.

The throwaway user plugin `plugins.zzpkg.zz107` had two decorated callbacks on one event, one runtime
`event.register`, an `event.add`, and three callbacks on `ev_plugin_unloaded`. Python 3.12, 128 events
known after startup.

| Step | Registrations owned by the plugin | `sys.modules` names with `zz107` |
| :--- | :--- | :--- |
| Before load | none (**verified**) | the three `userplugins.zzpkg.zz107*` modules, imported by discovery; no registration |
| After load | 8 callbacks on 5 events: the two decorated callbacks, the runtime one, three on `ev_plugin_unloaded` and the two `BasePlugin` ones (**verified**) | the same three names |
| After unload | none (**verified**) | none |
| After load again | the same 8 (**verified**) | the same three names |
| After `plugin.reload`, and after 3 more | the same 8; a raise runs each callback once (**verified**) | the same three names |

`out-q2_unload.txt` has the full registration dictionaries.

### Q2a: Does the cleanup work, and does #95 hold?

**Yes** (**verified**). After the unload no event holds a callback of the plugin. `function.owner.get` returns
`plugins.zzpkg.zz107` for both a decorated and a runtime callback, the same string as the `plugin_id` in the
`ev_plugin_unloaded` data, so `removeowner` matches. The plugin is imported under one name only
(`userplugins.zzpkg.zz107...`); no second copy appears under `plugins.` or `bastproxy.plugins.` (**verified**,
`sys.modules` listing). Reloading does not duplicate registrations (8 before, 8 after, a raise runs `a` and `b`
once).

A core plugin behaves the same (**verified**, `out-q2b_core_and_leaks.txt`): `plugins.core.mudcmds` has 3
registrations, one of them on `ev_plugin_unloaded` itself; `plugin.unload` refuses it because it is
required, `plugin.reload` (which allows required plugins) succeeds, and the registrations afterwards equal the
ones before. Every core plugin that is not marked non-reloadable is also marked required, so the public
unload cannot reach it; only `plugin.reload` does.

### Q2b: Is the plugin freed?

**The instance is** (**verified**). A weakref to the plugin instance is dead after `plugin.unload` and
`gc.collect()`, and the instance from before a `plugin.reload` is dead after it. The same holds for the
`mudcmds` instance after its reload. Events keep a history of raises (`raised_events`), but it holds no
callbacks (see Q1 Bug #3).

**The modules are not** (**verified**, `out-q2c_module_alive.txt`). After the unload the three module objects of
the user plugin are still alive, and the stale-module API of the loader lists them. The cause is the parent
package: `sys.modules` still holds `userplugins.zzpkg` and it keeps `zz107` as an attribute. After deleting
that attribute and running `gc.collect()` all three modules are gone. A reload replaces the attribute with
the new import. This is a plugin-loader matter and not an events one, so no event issue is drafted; see
Other Observations.

### Q2c: What stays behind on the events plugin?

- Event objects are never removed (**verified**). After the unload the events `ev_zz107_ev`, `ev_zz107_runtime`,
  `ev_zz107_added`, `ev_plugins.zzpkg.zz107_loaded` and `ev_plugins.zzpkg.zz107_unloaded` are all still in
  `EventsPlugin.events`, with `count()` 0 and the description and `created_by` that `event.add` gave them. A
  plugin that is loaded and unloaded many times should add no new objects, because the names repeat, so the
  dictionary grows with new event names only (**read**; not measured over many reloads).
- A plugin that is registered on `ev_plugin_unloaded` never sees its own unload (**verified**). The three
  callbacks of the throwaway plugin did not run when the plugin itself was unloaded. `BasePlugin`
  raises the event in its `uninitialize` hook, the events plugin's own callback is registered first at priority
  50 and calls `removeowner` for the plugin, and the plugin's callbacks are gone before their turn. They
  asked for priority 1 and 90 and stored at 50 (ES-4), so there is no way to run first.
- The cleanup does not unregister by event: `removeowner` visits every event and unregisters through the
  `event.unregister` API once per callback, which is correct but is O(events x callbacks) per unload (**read**).
  At 128 events this is not a cost worth a measurement.

### Q2d: What the unload probe found

- ES-5: the registration check is broken, so repeated registrations duplicate. It showed up here: three
  `event.register` calls for one runtime callback took the event from 1 to 4 callbacks and the callback ran
  4 times per raise (**verified**, `out-q2_unload.txt`), and calling `_eventcb_baseplugin_disconnect` three
  times took a plugin's registrations on `ev_libs.api_character_active` from 1 to 4 (**verified**,
  `out-q2b_core_and_leaks.txt`). The cleanup on unload does remove all copies.
- ES-4: the decorator priority is ignored. See Q3b.


---

## Q3: Priorities, Ordering and a Failing Callback

The run order comes from `ProcessRaisedEvent._exec_once`: it takes the priority keys, sorts them, and for each
runs `Event.raise_priority`, looping until a pass runs nothing. A callback is run once per raise, tracked with
a flag per callback that `reset_event` clears at the end.

### Q3a and Q3c: Order

- **Priorities run lowest first** (**verified**, `out-q3_order.txt`). Callbacks at 99, 50, 1 and 0 ran `p1, p50, p0, p99`.
  Priority 0 is stored at 50 (ES-6): `Event.register` does `prio or 50`, and `0` is falsy. The stored priorities
  were `[1, 50, 99]`.
- **Within one priority, the order is registration order** (**verified**). Registered 2, 0, 3, 1, they ran
  `c2, c0, c3, c1`. The dictionary is insertion-ordered; the code relies on it and does not say so.
- **The same function registered twice is stored twice** (**verified**): `register` returned `True` both
  times, the callback ran twice, and `isregistered` returned `False` (ES-5). With another priority the third
  registration also ran.
- Priority sorting runs on every pass of every raise (**read**). Q4 measures its cost.

### Q3b: Does `@RegisterToEvent(priority=...)` work?

**No** (**verified**). The decorator stores `priority`; `_api_event_register_by_func` passes it as
`priority=prio` to `event.register`, which reads `kwargs.get("prio", 50)`. On the real system a user plugin
with `priority=10` and `priority=70` was stored at 50 for both, and the events plugin's own
`@RegisterToEvent(event_name="ev_plugin_loaded", priority=1)` is stored at 50 (`out-q2_unload.txt`,
`out-q2b_core_and_leaks.txt`). A runtime `event.register(..., prio=30)` is stored at 30. In `src` two
decorators ask for a priority other than 50, both 1 (`out-grep-priority-decorators.txt`). The visible
effect is on `ev_plugin_loaded`: the live run order is commands, events, settings, all at 50, where the events
plugin asked to be first (**verified**, `out-q3g_live_order.txt`). Whether that order breaks anything is
**unverified**. This is ES-4.

### Q3d: Registering during a raise

Pass A verified that a callback registered during the second or later pass at an already visited priority is
dropped from that raise (#275, Q1 Design #4). The cases below are for a callback registered in the
first pass. `reg` runs at 50 and registers `late`; `last` runs at 99 (**verified**, `out-q3_order.txt`).

| `late` registered at | With `last` at 99 | Without `last` | Warning logged |
| :--- | :--- | :--- | :--- |
| 10 (lower) | `reg, last, late` | `reg, late` | none |
| 50 (same) | `reg, last, late` | `reg, late` | "called out of order" at 50 |
| 70 (between) | `reg, last, late` | `reg, late` | none; "processed 3 times" without `last` |
| 120 (above `last`) | `reg, last, late` | not probed | "processed 3 times" |

In every case `late` runs in the raise it was registered in, and
in none of them does it run before the callback at the higher priority: it runs in a second pass, after the
99 callback. The comment in `_exec_once` says the new registration is "processed in the same order as the other
functions", which is not true. The "out of order" warning is logged only when the priority was already visited
in an earlier pass, so a registration at 10 or 70 runs out of order without a warning. `count()` rose by one in
each case. A new priority key is seen only on the next pass, because the key list is taken at the start of a
pass (**read**).

### Q3e: A failing callback

- **The other callbacks still run** (**verified**). With callbacks at 10, 20 (raises `RuntimeError`) and 30 the
  order was `a, boom, b`, and `raise_event` returned the `ProcessRaisedEvent`.
- **The error is logged once, at ERROR, with `exc_info`** (**verified**): `raise_event - event ev_q3e with
  function boom raised an exception`.
- **State is clean afterwards** (**verified**): `current_callback` and `active_event` are `None`, all done
  flags are `False`, and the next raise runs all three again (#252 holds).
- **With `data_list`, failing on item 2 of 3**, every item ran every callback: `i1, after, i2, after, i3,
  after`, one error logged, `current_callback` `None` (**verified**).
- **The caller never sees a callback's error** (**verified**; **read** for the cause): `raise_priority` catches
  `Exception`. It does not catch `BaseException`, so `KeyboardInterrupt` and `SystemExit` propagate (Q1 Design #1).
- **An error outside the `try` does reach the caller** (**verified**). `_exec_once` reads the
  `log_savestate` setting through `setting.get` before any callback, outside the `try`. With `setting.get`
  raising, `raise_event` raised `RuntimeError` to the caller, no callback ran, the `finally` still cleared
  `active_event` and `current_callback`, and the failed raise stayed in `raised_events`. The next raise
  worked. The setting API is in a core plugin that cannot be unloaded, so this needs a settings failure to
  occur; it is a robustness note and not a defect.

### Q3f: Unregistering during a raise, and raising the same event again

- **A callback can unregister another one** (**verified**). Unregistering a callback at a later priority and
  one at the same priority (registered after it) both worked: the victim did not run. This is safe because
  `raise_priority` iterates a list copy and checks the callback is still registered before running it. A
  callback may also unregister itself, and the rest of the raise went on.
- **Empty priorities are kept** (**read**): `unregister` deletes the callback, not its priority key, so a
  priority that became empty stays in `priority_dictionary` and is visited on every pass. Not measured.
- **A callback that raises its own event again breaks the outer raise** (**verified**). The inner raise ends with
  `reset_event` and `finally`, which act on the shared `Event`: the outer raise's done flags are cleared, so
  `other` ran twice and `cb` ran a second time, and `active_event` was `None` for the rest of the outer raise.
  A callback that re-raises on every run made the outer loop run until a cap I set stopped it (30 calls); that
  it would otherwise never end is **read**, not run to the end. This is ES-7.


---

## Q4: What Does an Event Cost?

`tests/benchmarks/test_bench_event_raise.py` is informational and asserts no target. Each case raises through a
real `Event`, so it builds the `EventDataRecord` and `ProcessRaisedEvent` the live path builds, under
`tracking_actor`; `setting.get` is a stand-in that returns False; the record store is empty at the start and
restored afterwards. Every callback has its own owner id (ES-5 cannot match) and none raises an event (ES-7
cannot apply). The `event_stack` cases time `list(event_stack.get())`, which is what `event.stack.get`
does, inside `raised_event(...)` blocks (the push `_api_event_raise` makes); they do not time the `self.api(...)`
call around it. The benchmark also passes as a plain test (6 passed, **verified**).

Run: `uv run pytest tests/benchmarks/test_bench_event_raise.py --benchmark-enable --benchmark-only -v`, one run
on a development machine, 200 rounds of 1 iteration (2,000 for the stack reads). Environment: Python 3.12.12,
pytest-benchmark 5.3.1, Linux 6.17.13-2-pve, 12th Gen Intel Core i7-12650H, `warmup=True`, GC disabled.

| Case | Min | Median | Mean | IQR |
| :--- | ---: | ---: | ---: | ---: |
| Raise, 0 callbacks | 54.1 us | 67.1 us | 88.3 us | 57.0 us |
| Raise, 10 no-op callbacks over priorities 10, 50, 90 | 85.4 us | 97.8 us | 102.3 us | 11.0 us |
| Raise, `data_list` of 15 with `key_name="line"`, 1 callback | 465.3 us | 506.6 us | 510.5 us | 28.6 us |
| Raise, `raised_events` already at `MAX_RAISED_EVENTS` (10), 1 callback | 57.2 us | 66.5 us | 71.6 us | 8.3 us |
| `list(event_stack.get())`, depth 1 | 98 ns | 112 ns | 120 ns | 22 ns |
| `list(event_stack.get())`, depth 10 | 102 ns | 111 ns | 118 ns | 16 ns |

All figures **verified** (`out-bench-event-raise.txt`) and from a single run, so read them as orders of
magnitude. The 0-callback case has the widest spread (IQR 57 us), so its median and the full-history median
are not distinguishable.

What the numbers say:

- **A raise costs about 70 to 100 us before any callback runs** (median 67 us with none, 98 us with ten). The
  ten callbacks add about 31 us, about 3 us each (**verified** difference of medians; the per-callback split
  is arithmetic, not a separate measurement). Where the first 67 us goes (the two records and their updates, the `setting.get` stand-in, the
  `log_to` call, the priority sort) was **not profiled** (**unverified**). The sort and the key-list copy per priority (**read**) are small next to it for 3
  priorities; the benchmark does not vary the priority count.
- **A `data_list` raise costs about 34 us per item** (506.6 us / 15, median, **verified** total; the division
  is arithmetic). Each item (**read**, `_exec_multi` and `_exec_once`) sets `line` on the shared
  `EventDataRecord`, adds an `Invoked` update that formats `dict(self.event_data)` into a string, calls
  `setting.get`, makes a `log_to` call, runs the priority loop and ends with `reset_event`. This is the cost the proxy pays per MUD line and it dominates
  everything else measured here.
- **The history cap costs nothing measurable.** A raise with the history full (66.5 us) is no slower than one
  with an empty history (67.1 us); the `popitem` that evicts the oldest raise is lost in the noise. The cost
  of keeping 10 raises is memory, not time, and #153 bounds it.
- **Reading the event stack is about 0.1 us at either depth.** The stack is a tuple in a context variable; the
  read is a dictionary lookup and a copy of at most 10 names (**read**, `src/bastproxy/libs/context.py`). Depth does not show up in the timings.
- **Per round.** One whole MUD to client round, with the record store at its cap, is timed by
  `tests/benchmarks/test_bench_retention.py` (`test_bench_mud_to_client_round_at_cap`). Take that figure from
  that benchmark rather than from this page; it was not re-timed for the audit.

No performance defect found: nothing here is a candidate for an issue. The ADR-0005 targets are per line
(see `tests/benchmarks/test_bench_eventdatarecord.py`), and this page does not claim a per-line figure.

---

## Q5: What Is Untested?

Two runs (**verified**): `uv run doit coverage` over the whole suite (`coverage.txt`) and
`uv run pytest tests/plugins/core/events --cov=bastproxy.plugins.core.events --cov-branch --cov-report=term-missing -q`
(`coverage-narrow.txt`). Line coverage and branch coverage are combined in the percentages. The events package is
467 statements; the whole suite adds almost nothing to it: the only difference between the two runs in this
package is `src/bastproxy/plugins/core/events/libs/data/_event.py` (85.7% narrow, 100% in the suite), covered by a test outside
`tests/plugins/core/events` (**verified**; which test was not looked up). The suite as a whole is 70.8% against a
29% gate (**verified**).

| File | Statements | Coverage (narrow run) | Missed (narrow run) |
| :--- | ---: | ---: | :--- |
| `src/bastproxy/plugins/core/events/__init__.py` | 7 | 100.0% | none |
| `src/bastproxy/plugins/core/events/libs/_utils.py` | 9 | 90.9% | branch 37->39 |
| `src/bastproxy/plugins/core/events/libs/data/_event.py` | 19 | 85.7% (100% in the suite) | 53-55 |
| `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` | 62 | 82.1% | 64->80, 90-91, 110-118, 121-152 |
| `src/bastproxy/plugins/core/events/plugin/_event.py` | 132 | 68.7% | 67, 75, 81, 108, 114->113, 126-129, 158-214, 282-294, 301 |
| `src/bastproxy/plugins/core/events/plugin/_events.py` | 236 | **36.0%** | 135 statements; the groups are listed below |

**`src/bastproxy/plugins/core/events/libs/_utils.py`.** Missed: a function that already has `event_registration` (a second `RegisterToEvent` stacked on
one method). Covered: the first decoration. Whether any plugin stacks decorators was not checked (**unverified**).
The `_eventcb_` name filter in `get_event_registration_functions_in_object` is in `_events.py` (line 146, missed).

**`src/bastproxy/plugins/core/events/libs/data/_event.py`.** Only `get_attributes_to_format` is missed (display code).

**`src/bastproxy/plugins/core/events/libs/process/_raisedevent.py`.**

| Missed | What it is | Matters? |
| :--- | :--- | :--- |
| 64->80 | the `log` flag is False (a `_savestate` event with `log_savestate` off): the debug line is skipped | Low; the other branch is covered |
| 90-91 | `if len(keys) < 1: ... continue` inside `if keys := ...` | Dead code: `keys` is non-empty there (**read**) |
| 110-118, 121-152 | `get_attributes_to_format`, `format_simple` | Display only; the `Stack:` text is built with `plugins.core.utils` APIs a test would need to stub |

Covered, and the part that matters: the priority loop, `data_list` iteration, the failing-callback path
(`test_raising_callback_owner_freed`) and the `count > 2` warning branch (**verified**: not in the missed list).
The out-of-order branch of `raise_priority` (the `already_done` warning) is not in the missed list, so
something runs it; whether any test asserts on the warning was not checked (**unverified**).

**`src/bastproxy/plugins/core/events/plugin/_event.py`.**

| Missed | What it is | Matters? |
| :--- | :--- | :--- |
| 67 | `get_active_event` | Used by `event.current.record.get`; ES-7 turns on it returning None |
| 75 | `isregistered` body | **Yes.** Never run by any test, so ES-5 (it was never True for a real callback) had no test that would show it; covered since #279 |
| 81 | `isempty` | Low |
| 108 | `register` returns False for a duplicate | **Yes.** The duplicate check is untested; ES-5 showed it never fired for a real callback; covered since #279 |
| 114->113, 126-129 | `unregister` when the function is not found: the error log and `return False` | Medium; the "not found" path is untested |
| 158-214 | `detail` | Display only |
| 282-294 | `raise_event` with data that is neither a dict nor an `EventDataRecord` | **Yes.** The branch uses `self.called_from`, which `Event` does not have, so it raises (ES-2) |
| 301 | `created_by` set from the first raiser | Low |

Covered, and the part that matters: `register` for a new function, `removeowner` including its `current_callback`
branch, the `raised_events` cap (`test_event_raised_history.py`), `reset_event`, and `raise_priority` with a
callback that raises.

**`src/bastproxy/plugins/core/events/plugin/_events.py`: 36.0%.** The tests call methods on stub objects (`EventsPlugin._api_event_raise(plugin, ...)`,
`EventsPlugin._phook_initialize(stub)`), so `EventsPlugin` itself is never constructed and its `__init__` hook
(lines 32-39) is never run (**verified**: missed). What is covered is `_phook_initialize`, `_apply_raised_history_size`,
`_eventcb_raised_history_size_modified`, `_api_event_current_name_get`, `_api_event_stack_get` and the raise and
stack parts of `_api_event_raise`: the pieces #153 and the event stack context change touched.

| Missed lines | Function(s) | Matters? |
| :--- | :--- | :--- |
| 217-220 | `_api_event_get` (creates and stores an unknown event) | **Yes.** ES-8 is in this function |
| 260-275 | `_api_event_register` (reads `kwargs.get("prio", 50)`) | **Yes.** Where ES-4 lives |
| 158-162 | `_api_event_register_by_func` (the `.format(**__dict__)` and `priority=`) | **Yes.** The other half of ES-4 |
| 287-290 | `_api_event_unregister` | **Yes.** The unload path |
| 304-312 | `_api_event_unregister_for_owner` | **Yes.** What cleans up a plugin's events on unload |
| 167-174 | `_eventcb_plugin_unloaded` | **Yes.** The entry to the cleanup; the #95 and #127 protection depends on it |
| 111-129, 134-139, 101-107 | `_register_events_for_plugin`, `_eventcb_plugin_initialized`, `_eventcb_post_startup_plugins_loaded`, `_register_all_plugin_events` | **Yes.** How `_eventcb_` methods get registered at startup and on load |
| 146 | `get_event_registration_functions_in_object` | Yes; the `_eventcb_` prefix filter |
| 185-188, 244-247, 230 | `event.current.record.get`, `event.is.registered`, `event.exists` | Medium; the first is how every callback reads its data |
| 366->369, 370, 373 | `_api_event_raise`: the unknown-caller branches | Low |
| 204-207, 317-345, 393-399, 429-438, 481-512, 523-531, 536-569 | `event.add`, `detail.get.for.plugin`, `event.detail.get`, `_command_detail`, `_command_list`, `_command_owner`, `summary.get.for.plugin` | Display, plus `event.add` which `_phook_initialize` calls |
| 410-418 | `_command_raise` | Medium; its "does not exist" branch is dead (ES-8) |

**What the gap means.** The register, unregister and unload half of the events plugin has no test: the real
registration API (including the decorator path), `event.unregister.for.owner` and `_eventcb_plugin_unloaded`
are exercised by nothing in the suite (**verified**: missed in both runs). Q2 and Q3 checked their behaviour by
probe (**verified**) and found ES-4 and ES-5 in the code the missed lines belong to. Nothing keeps those
results true. #127's regression test (`test_event_unload_retention.py`) stands in a lambda for
`event.unregister` and calls `Event.removeowner` directly, so it covers the `Event` object but not the plugin
method that decides which owner to remove. ES-9 asks for tests for these paths.

---

## Q6: Patterns and Anti-Patterns

"Keep" means the pattern fits. "Change" means worth an issue, and every Change row names it. The plugin audit
already covers the string service locator and hidden global state for plugins
([that table](plugin_system_findings.md#q5-patterns-and-anti-patterns)); the rows below add only what is
specific to the events package.

Commands run, scoped to `src/bastproxy/plugins/core/events` (output saved as `out-q6-grep-*.txt`):

- `grep -rnE "except( Exception)?:|suppress\(Exception|except BaseException"` found one site:
  `src/bastproxy/plugins/core/events/plugin/_event.py` line 262 (`except Exception:  # pylint: disable=broad-except`);
- the path grep (`Path|os\.path|` quoted `a/b` strings) found nothing: no string paths and no `Path` use;
- the module-global grep found only constants (`CANRELOAD`, `PLUGIN_*`) and instance attributes; no mutable
  module global (the registry is `EventsPlugin.events`, an instance attribute);
- the `self.api(` grep found 5 sites in `src/bastproxy/plugins/core/events/plugin/_event.py` and 5 in `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py`, and the rest in
  `src/bastproxy/plugins/core/events/plugin/_events.py` (the listing is in `out-q6-grep-api.txt`);
- the `type: ignore|noqa` grep found one: `src/bastproxy/plugins/core/events/plugin/_event.py` line 303.

| # | Pattern or anti-pattern | Where | Consistent? | Verdict |
| --: | :--- | :--- | :--- | :--- |
| 1 | **Publish/subscribe through string event names**: `event.raise("ev_...")`, `@RegisterToEvent(event_name="ev_...")` | all of `src` | Yes | **Keep.** The loose coupling is the point. A misspelt name raises or registers on a new, empty event with no error (the cost; compare #283). |
| 2 | **Priority ordering, sorted on every pass of every raise** | `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` `_exec_once`; `src/bastproxy/plugins/core/events/plugin/_event.py` `raise_priority` | Mostly: the order holds (Q3a), the inputs do not | **Change** for what feeds it: #278 (decorator priority ignored), #280 (0 stored as 50), #275 (late registration dropped). The sort itself is cheap (Q4) and stays. |
| 3 | **Failure isolation: catch-all in `raise_priority`** | `src/bastproxy/plugins/core/events/plugin/_event.py` line 262 | Yes, the only site | **Keep.** It logs at ERROR with `exc_info` and runs the next callback (**verified**, Q3e); `KeyboardInterrupt` and `SystemExit` are not caught (**verified**). The `setting.get` call in `_exec_once` is outside it (Q3e), which is a note, not a defect. |
| 4 | **Global registry**: `EventsPlugin.events`, `all_event_stack` (a `SimpleQueue` of 300), `Event.MAX_RAISED_EVENTS` as a class attribute the plugin writes, and the `event_stack` context variable in `src/bastproxy/libs/context.py` | `src/bastproxy/plugins/core/events/plugin/_events.py`, `src/bastproxy/plugins/core/events/plugin/_event.py` | Yes | **Change** for the registry only: events are created by any `event.get` and never removed (#283). The context variable is the right tool for the stack (**read**) and stays; the class attribute is shared by all events by design. |
| 5 | **Decorator registration with `_eventcb_` discovery**: `RegisterToEvent` sets a function attribute, `get_event_registration_functions_in_object` collects names that start with `_eventcb_` | `src/bastproxy/plugins/core/events/libs/_utils.py`; `src/bastproxy/plugins/core/events/plugin/_events.py` line 146 | Yes | **Change** for discovery: the prefix filter means a decorator on any other method name is silently ignored (**read**, #284). The decorator itself is **Keep**; its priority argument is the bug (#278). |
| 6 | **Service locator through string API names** inside the event objects: `self.api("plugins.core.settings:setting.get")` in `ProcessRaisedEvent` and `Event` | `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` lines 59, 121 to 143; `src/bastproxy/plugins/core/events/plugin/_event.py` lines 151 to 200 | Yes | **Keep, document.** The service-locator trade, covered by the plugin audit's row 4. It is why a raise fails if the settings plugin is not there (Q3e). |
| 7 | **Silent failures**: `event.register` logs an error and returns when it finds no owner; `Event.register` returns False for a duplicate without a log; `raise_event` logs and returns `None` for bad data | `src/bastproxy/plugins/core/events/plugin/_events.py` line 260 to 266; `src/bastproxy/plugins/core/events/plugin/_event.py` lines 108 and 282 to 296 | No | **Change** for two: the duplicate check never fires (#279); the bad-data log line itself raises `AttributeError` (#276). The no-owner return logs an ERROR with the function and is **Keep**. |
| 8 | **Strings, not `Path`, for paths** | none found | n/a | **Fits.** The path grep found nothing. |
| 9 | **Hidden globals** | none mutable at module level | n/a | **Keep.** `Event.MAX_RAISED_EVENTS` is the one shared mutable value, written from the setting (**read**); `plugin_system_findings.md` row 7 covers the rest. |
| 10 | **Import-time side effects** | `src/bastproxy/plugins/core/events/__init__.py` imports `RegisterToEvent`; `src/bastproxy/plugins/core/events/plugin/__init__.py` imports `EventsPlugin` | Yes | **Keep.** Importing builds no object and registers nothing (**read**). |
| 11 | **Catch-all `except`** | row 3 | Yes | **Keep.** See row 3. |
| 12 | **Type-check escapes**: one `# type: ignore` on `ProcessRaisedEvent(self, data, actor)`, and the whole package under `bastproxy.plugins.core.*` `ignore_errors` in `pyproject.toml` (**verified**, `out-pyproject-mypy.txt`) | `src/bastproxy/plugins/core/events/plugin/_event.py` line 303 | Whole package | **Keep, tracked by #6.** Do not widen it. |
| 13 | **Untested registration and unload paths** | Q5 | n/a | **Change** (#282). |
| 14 | **Work in a callback that cannot be awaited**: `Callback.execute` drops the result | `src/bastproxy/libs/callback.py` | Yes | **Change** (#277). |
| 15 | **State on the shared `Event` for one raise** (done flags, `current_callback`, `active_event`) | `src/bastproxy/plugins/core/events/plugin/_event.py` | Yes | **Change** (#281). A nested raise of the same event shares it. |
| 16 | **Dead code**: `if len(keys) < 1: ... continue` inside `if keys := ...` | `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` lines 90 to 91 | n/a | **Keep.** Harmless (**read**); it falls under the cleanup of #275 if that rewrites the loop. |

---

## Where the Docs Disagreed With the Code

Corrected in [Event System](event_system.md) in this change. Where the code is wrong, the page now says so and
points at the issue; the code is not hidden behind the doc. Tags: **verified** (a script or grep ran, output
saved) or **read** (compared by reading).

| # | Section | Said | Code does | Fixed here or issue |
| --: | :--- | :--- | :--- | :--- |
| 1 | Event Class, excerpt | `Event.__init__` ended at `raised_count` | Also sets `owner_id`, `api`, `raised_events`, `current_callback`, `active_event`, and the class has `MAX_RAISED_EVENTS` (**read**, `src/bastproxy/plugins/core/events/plugin/_event.py` lines 32 to 62) | Fixed |
| 2 | ProcessRaisedEvent, excerpt | `__init__` set five attributes | Also calls `BaseRecord.__init__`, `event_data.add_receiving_event(self)`, sets `id` and adds an `Init` update (**read**, `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` lines 25 to 36) | Fixed |
| 3 | RegisterToEvent, excerpt | Only `__init__` shown; `priority` described as the callback priority | `__call__` appends to `event_registration`; only `_eventcb_*` methods are collected (**read**); the priority is stored at 50 whatever it is (**verified**, Q3b) | Fixed (note added); defect #278 |
| 4 | Registering example | `@RegisterToEvent(..., priority=1)` runs first | Stored at 50 (**verified**, Q3b) | Fixed (comment added); #278 |
| 5 | Event Registration | The metadata "is processed during plugin initialization" | Registered when the post-startup event is raised, then on `ev_plugin_loaded` for later loads, which returns early while the proxy starts (**read**, `src/bastproxy/plugins/core/events/plugin/_events.py` lines 94 to 140) | Fixed |
| 6 | Event Raising, steps 4 to 5 | Callbacks registered during execution "are processed in subsequent iterations" | True for a first-pass registration, which runs after the higher priorities; one registered from the second pass at a visited priority is dropped from that raise (**verified**, Q3d, Q1 Design #4) | Fixed (caveat added); #275 |
| 7 | Event Raising | No failure behaviour described | A failing callback is logged and the rest run (**verified**, Q3e); bad data returns `None` and the log line raises `AttributeError` (**verified**, Q1 Bug #4) | Fixed (step 7 added); #276 |
| 8 | Priority-Based Execution, `raise_priority` | An excerpt with no `try`, no `tracking_actor` and no warning | The live method has all three (**read**, `src/bastproxy/plugins/core/events/plugin/_event.py` lines 232 to 275). "Lower numbers first" holds (**verified**, Q3a), but priority 0 is stored at 50 (**verified**, Q3a) | Fixed; #280 |
| 9 | Unique Patterns, dynamic registration | Presented as handling late registrations correctly | `found_callbacks` is overwritten by each priority (**verified**, Q1 Design #4) | Fixed (caveat added); #275 |
| 10 | Important Files | Listed five files | Also `src/bastproxy/plugins/core/events/plugin/__init__.py`; and libs/_event.py and plugin/_process_event.py are gone (**read**: the package has seven `.py` files) | Fixed (note on #241 and the API list added) |
| 11 | API names | Did not list the registration, unregister or `event.get` APIs | All are registered with `AddAPI` (**verified**, `out-docs-checks.txt`); the old names `remove.events.for.owner` and `get.event.stack` are not in the page (**verified**, the grep is empty). `event.get` creates any event it is asked for | Fixed (list added); #283 |
| 12 | Actors | Did not say who the `actor` of a raise is | `event.raise` takes `calledfrom` or looks up the caller; it becomes `called_from`, the owner id of a new `EventDataRecord`, and `created_by` of a new event; each callback runs under `tracking_actor` (**read**, `src/bastproxy/plugins/core/events/plugin/_events.py` lines 351 to 383; `src/bastproxy/plugins/core/events/plugin/_event.py` lines 232 to 305) | Fixed (section added, #248) |
| 13 | Integration Points | "Plugins automatically register their `@RegisterToEvent` methods during initialization"; "all its event registrations are removed" | Registration timing as row 5; the `Event` objects stay after an unload (**verified**, Q2c) | Fixed |
| 14 | Data Flow and Common Event Names | `ev_from_mud_event` and `ev_from_client_event` | Neither name exists in `src` (**verified**, `out-docs-checks.txt`); the page now names `ev_to_mud_data_read` and `ev_to_client_data_read` (registered from `RECORD_EVENTS`, **read**) | Fixed |

**Checked and correct** (**read**; no change): the `EventDataRecord` excerpt, `add_receiving_event` and the
"`.data` no longer exists" note (#246); the paragraph on the four record events registered once from
`RECORD_EVENTS` (#236); Event History (`MAX_RAISED_EVENTS`, `raised_history_size`, the default of 10, the clamp of
negative values, `raise_event` returning the record at a cap of 0); the Event Stack and Current Event Record
sections; and the `Event Location` paths. The claim that the debug records plugin reads `RMANAGER` and not
`raised_events` is **unverified**, as it was.

---

## New Defects

The Q1 defects (ES-1 to ES-3, #275 to #277) are listed with their rows above and are not repeated here.

### ES-4: `@RegisterToEvent(priority=...)` is ignored

**Issue:** #278
**Location:** `src/bastproxy/plugins/core/events/plugin/_events.py`, `EventsPlugin._api_event_register_by_func`
(passes `priority=`) and `EventsPlugin._api_event_register` (reads `prio`).
**Evidence (verified):** a user plugin's decorators at priorities 10 and 70 were both stored at 50; the live
order on `ev_plugin_loaded` is commands, events, settings at 50 (Q3b).
**Fix:** read the priority under one name; test the stored priority.

### ES-5: The event system cannot detect an already registered function

**Status:** fixed by #279 (the hash no longer includes `created_time`; `isregistered` matches by function; `Timer` hashes by identity).

**Issue:** #279
**Location:** `src/bastproxy/libs/callback.py`, `Callback.__hash__` (adds `created_time`);
`src/bastproxy/plugins/core/events/plugin/_event.py`, `Event.isregistered` and the duplicate check in
`Event.register`; `src/bastproxy/plugins/_baseplugin/_base.py`, `_eventcb_baseplugin_disconnect`.
**Evidence (verified):** the same function registered twice ran twice and `isregistered` was False; three
disconnect calls took the plugin's registrations on one event from 1 to 4 (Q2d, Q3c).
**Fix:** drop `created_time` from the hash; compare with `call_back == func` in `isregistered`.

### ES-6: Priority 0 is stored as priority 50

**Status:** fixed by #280 (`Event.register` uses `50 if prio is None else prio`).

**Issue:** #280
**Location:** `src/bastproxy/plugins/core/events/plugin/_event.py`, `Event.register` (`prio or 50`).
**Evidence (verified):** a callback registered at 0 ran between the 50 and the 99 callbacks and the stored
priorities were `[1, 50, 99]` (Q3a). No caller in `src` registers at 0 (**read**).
**Fix:** `50 if prio is None else prio`.

### ES-7: Raising an event from one of its own callbacks resets the outer raise

**Status:** fixed by #281 (the done flags move to `ProcessRaisedEvent.done`; `Event.raise_event` saves and restores `active_event` and `current_callback`; `Event.reset_event` is removed).

**Issue:** #281
**Location:** `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` (`_exec_once` calls
`reset_event`) and `src/bastproxy/plugins/core/events/plugin/_event.py` (`Event.raise_event` `finally`,
`Event.reset_event`).
**Evidence (verified):** with a nested raise `other` ran twice and `active_event` was `None` for the rest of
the outer raise (Q3f).
**Fix:** keep the done flags and the active event per raise rather than on the shared `Event`, or refuse a
nested raise of the same event with an error.


### ES-8: `event.get` creates an event for any name, so the raise command never reports an unknown event

**Status:** fixed by #283 (`_command_raise` checks `event.exists` first; `event.get` still creates, for its other callers).

**Issue:** #283
**Location:** `src/bastproxy/plugins/core/events/plugin/_events.py`, `EventsPlugin._api_event_get` (creates and
stores an `Event` for a name it has not seen) and `EventsPlugin._command_raise` (tests the result of
`event.get` for truth).
**Evidence (read):** `_api_event_get` always returns an `Event`, and `Event` defines no `__bool__` or `__len__`,
so the test in `_command_raise` is always true and its "event does not exist" branch cannot run. Events are
never removed (Q2c, **verified**), so every `raise` of a new name adds a permanent `Event`. The branch is
missed by both coverage runs (Q5, **verified**). No probe was run for the command itself.
**Fix:** give the command a lookup that does not create (use `event.exists` first, or add a non-creating get),
and check whether any other caller of `event.get` relies on the creation.

### ES-9: The events plugin's register, unregister and unload paths have no test

**Status:** fixed by #282 (`tests/plugins/core/events/test_events_plugin_registration.py` covers the listed paths; the ES-4 and ES-5 cases are in their own test files).

**Issue:** #282
**Location:** `src/bastproxy/plugins/core/events/plugin/_events.py`: `_api_event_register`,
`_api_event_register_by_func`, `_api_event_unregister`, `_api_event_unregister_for_owner`,
`_eventcb_plugin_unloaded`, `_register_events_for_plugin`, `get_event_registration_functions_in_object`;
`src/bastproxy/plugins/core/events/plugin/_event.py`: `Event.isregistered` and the duplicate branch of
`Event.register`.
**Evidence (verified):** these lines are missed by both coverage runs (Q5, `coverage.txt`,
`coverage-narrow.txt`). `EventsPlugin` is 36.0% covered and `Event` 68.7%.
**Fix:** tests that build an `EventsPlugin` the way the other plugin tests do and cover: a decorated callback
is stored at its priority (fails today, ES-4); registering twice is detected (fixed and tested in #279, ES-5);
`_eventcb_plugin_unloaded` leaves no registration for the unloaded owner; an unknown owner and an unknown
event do not raise. Tests for ES-4 and ES-5 belong with their fixes, not this issue.

### ES-10: `@RegisterToEvent` on a method not named `_eventcb_*` is ignored without a message

**Issue:** #284
**Location:** `src/bastproxy/plugins/core/events/plugin/_events.py`: `get_event_registration_functions_in_object`.
**Evidence (read):** the `find_methods` predicate is `m.__name__.startswith("_eventcb_") and hasattr(m,
"event_registration")`, so a decorated method under any other name is never collected, and nothing logs it.
**Fix:** discover by the `event_registration` attribute alone, or log a warning for a decorated method without the
prefix.

### ES-11: Two code comments in the events plugin are wrong

**Issue:** #285
**Location:** `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py`: `ProcessRaisedEvent._exec_once`;
`src/bastproxy/plugins/core/events/plugin/_event.py`: `Event.raise_priority`.
**Evidence:** the `_exec_once` comment says a callback added during a raise "will be processed in the same order
as the other functions"; it runs in a later pass (**verified**, Q3d). The `raise_priority` comment names an API
`plugins.core.events:get:current:event` that does not exist; the API is
`plugins.core.events:event.current.record.get` (**read**).
**Fix:** correct both comments. Not edited here: the audit changes docs only.

---

## Other Observations

- **Unloaded user plugin modules stay alive** because the parent package (`userplugins.<package>`) keeps the
  submodule as an attribute (**verified**, `out-q2c_module_alive.txt`). A loader matter; `plugin.module.list.stale`
  reports them. No event issue.
- **Event objects are never removed after an unload** (**verified**, Q2c). A reloaded plugin reuses the names, so
  the dictionary grows only with new event names (**read**).
- **A plugin cannot see its own `ev_plugin_unloaded`** (**verified**, Q2c): the events plugin removes its callbacks
  first. With #278 fixed, a priority-1 callback would run first.
- **The out-of-order warning is partial** (**verified**, Q3d): it is logged only for a priority already visited
  in an earlier pass, so a registration at a lower or in-between priority runs late without one.
- **Two code comments are wrong** (**verified** for the first, Q3d). The comment in `_exec_once` says a callback
  added during a raise "will be processed in the same order as the other functions", which is not true (it runs in
  a later pass). A comment inside `raise_priority` mentions an api
  `plugins.core.events:get:current:event` that does not exist (**read**; the API is `event.current.record.get`).
  They are not edited in this audit; see ES-11 (#285).
- **Decorator on a non-`_eventcb_` method is ignored without a message**: see ES-10 (#284).
- **Empty priority keys stay** in `priority_dictionary` after the last callback leaves (**read**, Q3f); they are
  visited on every pass. Not measured.
- **`setting.get` is read outside the `try`** in `_exec_once` (**verified**, Q3e): a settings failure reaches the
  caller of `raise_event`.
- **Shutdown noise** (**unverified**, not investigated): the probe scripts printed "Logging error ... import of
  `bastproxy.libs.api._api` halted" at interpreter exit. Harmless to the probes.
