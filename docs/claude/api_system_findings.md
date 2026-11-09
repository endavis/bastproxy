---
title: API System Analysis and Findings
description: Audit of API registration, removal, call cost, caller tracking and the patterns the API system uses, with defects and a patterns review
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - api
  - review
---

# API System Analysis and Findings

**Date:** 2026-11-08
**Analyzer:** Claude Sonnet 5.5
**Scope:** The API system in `src/bastproxy/libs/api/` (`_api.py`, `_addapi.py`, `_apiitem.py`,
`_apistats.py`, `_functools.py`): registration, override, removal, call cost, owner and caller
tracking, test coverage and patterns (audit issue #105). Compared against [API System](api_system.md).
Base commit `39520f6`.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [Status of the Known Items](#status-of-the-known-items)
4. [Q1: Register, Override and Remove](#q1-register-override-and-remove)
5. [Q2: What Does a Call Cost?](#q2-what-does-a-call-cost)
6. [Q3: Owner and Caller Tracking](#q3-owner-and-caller-tracking)
7. [Q4: What Is Untested?](#q4-what-is-untested)
8. [Q5: Where the Docs Disagreed With the Code](#q5-where-the-docs-disagreed-with-the-code)
9. [Q6: Patterns and Anti-Patterns](#q6-patterns-and-anti-patterns)
10. [New Defects](#new-defects)
11. [Other Observations](#other-observations)

---

## Executive Summary

The core works. A lookup costs about 0.2 microseconds, a whole call about 2 microseconds, and a
startup of all bundled plugins made 108,776 API calls without one unknown caller. Removing a
plugin's class APIs on unload is complete: after unloading a bundled test plugin its `_class_api`
entries were gone and the instance was collected. The four fixes the issue lists (#91, #95, #99,
#100) hold up.

The gaps are in the paths the happy case does not cover, and in two costs nobody had measured:

- **The unknown-caller path costs about 1.3 ms per call**, roughly 650 times a normal call
  (AS-5). It builds `inspect.stack()`, a stack dump and a `LogRecord`, and logs twice. Startup
  never takes it; any code that calls an API from outside an object with an `owner_id` does.
- **Every `API(...)` object builds 14 `APIItem`s** (AS-6). That is 7.5 microseconds and about
  5 KB, and every record (`LogRecord`, `UpdateRecord`, ...) builds one (fixed in #199). After startup 12,470
  `API` objects were alive, 11,904 of them owned by `UpdateRecord` and `LogRecord`.
- **`API.add` returns `True` when it refuses a duplicate** (AS-1), and a test asserts it.
- **`api.toplevel.remove` raises** for an instance API and for any function that was added
  without `@AddAPI` (AS-2). No code does either today, so this is latent. Stats, the `addedin`
  keys and force-overrides by another owner also survived an unload (AS-3, fixed in #196).
- **`libs.api:caller.owner.get` returns the owner of the API object it was called through**
  unless the caller passes an ignore list (AS-4). `libs.timing` calls it without one, so every
  timer is recorded as started by `bastproxy.libs.timing`.
- **`api.detail.get` and `api.list.formatted` crash** for two `lru_cache`-wrapped fuzzy APIs and
  for an API with no description (AS-7). The detail and list code is untested: `_api.py` is at
  49.56% and `_apiitem.py` at 38.10% line coverage (Q4).
- **Dead surface**: `API.stats`, `force=`, `instance=True`, `overwritten_api`, the
  `bastproxy.` strip in `API.get` and a 100-line `test()` function have no user in `src`
  (AS-8).

**Key Findings:**

- 11 defects (AS-1 to AS-11), listed under [New Defects](#new-defects).
- No security finding.
- [API System](api_system.md) is corrected where it disagreed with the code (Q5).
- Benchmarks are in `tests/benchmarks/test_bench_api.py`; run them with `doit benchmark`.

---

## How This Was Verified

Claims below are tagged **verified** (run against the code, with the output summarised),
**read** (from reading the code, not executed) or **unverified**.

Verification used throwaway scripts that boot the real plugin system in-process (the same steps as
`MudProxy.run` without the listeners and the asyncio loop: `PluginLoader().load_plugins_on_startup()`),
then load, unload and reload a bundled test plugin and snapshot the registries before and after,
plus small classes for the caller-detection cases. The scripts were deleted afterwards; they are
not part of the repository. Counts come from `grep` and from the live registry at the base
commit. Timings come from `tests/benchmarks/test_bench_api.py` run with `doit benchmark`. Coverage
comes from `doit coverage`, run before the benchmark file was added so that the benchmark does not
count as a test of the code it times.

Environment: Python 3.12.12, pytest-benchmark 5.3.0, 12th Gen Intel Core i7-12650H, 2026-11-08.

---

## Status of the Known Items

Every item in the issue's "Known so far" list, with its current state.

| Item from the issue | Status | Where |
| :--- | :--- | :--- |
| Missing APIs raise a bare `AttributeError` that callers cannot tell apart from one raised inside the API | **Fixed** (verified: `API.get` raises `APINotFoundError`, a subclass of `APIException` and `AttributeError`, `src/bastproxy/libs/exceptions.py`). No caller catches `AttributeError` to detect a missing API: the six `except AttributeError` in `src` are `getattr` lookups (`_base.py` twice, the events and commands plugins, `get_api_functions_in_object`) and one in `src/bastproxy/libs/tracking/utils/attributes.py` (**read**). The subclassing is kept for old callers; nothing in `src` relies on it. | #91, PR #152 |
| Two `lru_cache`s keyed on callables kept unloaded plugins alive | **Fixed** (verified: the `libs/api` caches are gone and `tests/libs/test_api_cache_references.py` guards it; a bundled test plugin I unloaded was collected). **Not fixed outside `libs/api`**: the fuzzy plugin puts `@lru_cache` on two methods (`src/bastproxy/plugins/core/fuzzy/plugin/_fuzzy.py`, **read**), which keys the cache on `self`. Latent, because core plugins are not unloaded. It also breaks `APIItem.detail` (AS-7). | #100, PR #114 |
| Names follow no single convention: 173 `@AddAPI` decorators, mixed verb-first and object-first | **Fixed** by [ADR-0004](../decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md) and the rename series ending at `39520f6`. Verified: `LEGACY_NAMES` in `tests/plugins/test_api_name_grammar.py` is `{}`, and `tests/plugins/test_api_names_exist.py` checks literal names against the registry. The count: `grep -rn "AddAPI(" src/bastproxy --include=*.py \| wc -l` gives 174, one of which is the docstring example in `_addapi.py`, so there are still 173 decorators. `info/api_naming_analysis.md` is not stale: it opens with a "Superseded by ADR-0004" banner and is kept for history. | #99, PR #173 and #161 to #172 |
| Instance APIs (`_instance_api`) override class APIs in `API.get` | **Still present, by design, and unused**: verified that `grep -rn "instance=True" src/bastproxy --include=*.py` finds only the docstring in `_addapi.py` and the 14 built-ins in `API.__init__`. No plugin declares an instance API (AS-8). | Q1, AS-2 |
| `owner_id` prefix handling strips a leading `bastproxy.` | **Removed in #202**; both strips were live (Q3, AS-9). Plugins no longer import under two names (#95), so the strip is not a plugin concern. | #95, PR #109 |

---

## Q1: Register, Override and Remove

### Registering

`API` holds one process-wide class registry, `API._class_api` (`dict[str, APIItem]`, a `ClassVar`),
and each `API` object holds `_instance_api`. A name is `"<toplevel>:<name>"`.

| Step | Code | Notes |
| :--- | :--- | :--- |
| Decorate | `AddAPI.__call__` (`_addapi.py`) sets `func.api = {"name", "description", "instance", "addedin": {}}` on the **function object** | `addedin` is shared by every instance of the class and is mutated later (see Removing). |
| Discover | `API.get_api_functions_in_object(base, recurse=True)` walks `dir(base)`, keeps bound methods whose `__name__` starts with `_api_` and that have `.api`, and recurses one level into every other attribute | **read**. A decorated method not named `_api_*` is silently ignored. |
| Add | `API._api_api_add_for_object(toplevel, item)` formats `name` and `description` with `func.__self__.__dict__`, records the name in `func.api["addedin"][toplevel]` (class APIs only), then calls `libs.api:api.add` | The plugin base class calls it three times per plugin (`_base.py`: `_phook_base_init_add_apis`, `_phook_base_init`, `_phook_base_post_initialize_setup`); the `addedin` check makes the second and third calls skip what is registered (**read**). One scan of the events plugin took 0.36 ms (**verified**), so about 1 ms per plugin load. |
| Register | `API.add` builds an `APIItem` and stores it in `_class_api`, or calls `API._api_instance` for `instance=True` | Same function again: returns `True` and does nothing. |

### Overriding

| Case | Result (verified) |
| :--- | :--- |
| Class API, same name, different function, no `force` | Logs an error and **returned `True`** when audited; the first function stays registered (AS-1, fixed in #194: now returns `False`). Fixed in #209: `_api_api_add_for_object` records the name in `addedin` only when `add` returned `True`, so a refused add can be retried. |
| Instance API, same name, different function, no `force` | Logs an error and returns `False`. The two paths disagree. |
| Class API with `force=True` | Replaces the entry and keeps the old one in `overwritten_api`. |
| Lookup order | `API.get` checks `_instance_api` first, then `_class_api`. |
| Who uses `force=True` or `instance=True` | Nobody in `src` (verified by `grep`). Only tests and the docstring do. |
| A second owner force-overrides `p.victim:f`, then its own toplevel is removed | Before #196 the override stayed: removal was by toplevel name only and `overwritten_api` was never restored (verified then). Since #196 removal also scans for entries owned by the removed toplevel in other toplevels, restores `overwritten_api` or deletes the entry (AS-3). |

### Removing

`_phook_base_unitialize_hook` (priority 100, `_base.py`) calls `libs.api:api.toplevel.remove` with
the plugin ID, after the unloaded events are raised. `API._api_api_toplevel_remove` deletes every
`_class_api` and `_instance_api` key that starts with `"<toplevel>:"` and removes the name from
`func.api["addedin"][toplevel]`.

Unload probe on `plugins.test.cmddec` (**verified**; the first try on `plugins.core.watch` was refused
by the loader because core plugins cannot be unloaded):

```text
before unload   class APIs 8   stats entries 1
unload returned True
after unload    class APIs 0   stats entries 2   instance collected: True
shared function addedin[plugins.test.cmddec] = []   (key kept, 18 toplevels on the function)
reload          class APIs 8   stats entries 2
stats count for plugins.test.cmddec:data.directory.get across the reload: 1 -> 2
```

| Registry | Removed on unload? | Result |
| :--- | :--- | :--- |
| `API._class_api` | Yes | **Verified** clean. |
| `API._instance_api` of the plugin's `API` object | Not individually | Dies with the object; the plugin instance was collected (**verified**). The 14 built-in `libs.api:` entries are never removed on their own. |
| `@AddAPI(instance=True)` methods | **Raises** `ValueError` | **Verified** (AS-2): `add_for_object` appends to `addedin` only when `not instance`, but removal calls `.remove(api_name)` for instance keys too. The class keys are deleted first and the instance key is left behind. |
| Functions added without `@AddAPI` | **Raises** `AttributeError` | **Verified** (AS-2): removal reads `func.api` for every key. `_pluginm.py` adds `plugin.state.save.all` this way (`can_reload_f` is false there, so it is never removed), and `libs.asynch:task.add` is another (its toplevel is never removed). |
| `STATS_MANAGER.stats` | Yes, since #196 | Before #196 (**verified**) stats survived the unload and kept counting after a reload (AS-3). |
| `func.api["addedin"][toplevel]` | Yes, since #196 | Before #196 (**verified**) an empty list stayed for every toplevel ever loaded. |

Stats and the shared function attribute were the "incomplete removal" the issue asked about; the
registry itself was clean. #196 prunes both.

---

## Q2: What Does a Call Cost?

One call, `api("<toplevel>:<name>")(args)`, is `API.get` (a dict lookup), then
`APIItem.__call__`, which runs `get_caller_owner_id()` (a walk up the call stack) and
`STATS_MANAGER.add_call` (two dict updates), then the function.

Results from `tests/benchmarks/test_bench_api.py` (**verified**), sorted by median:

- Date: 2026-11-08; Python 3.12.12; pytest-benchmark 5.3.0; 12th Gen Intel(R) Core(TM) i7-12650H.
- Command: `uv run doit --verbosity=2 benchmark` (the task is `uv run pytest tests/benchmarks/ --benchmark-enable --benchmark-only -v`, `tools/doit/benchmark.py`). The whole run: 17 passed, 1 skipped, 27.80 s.
- Ops/sec is the tool's `OPS` column (1 / mean).

| Case | What it times | Median (ns) | Ops/sec | Rounds |
| :--- | :--- | ---: | ---: | ---: |
| (a) baseline | the raw function, no API | 36.2 | 27,388,508 | 192,981 |
| (c) `get`, instance hit | found in the first dict | 210.7 | 4,720,041 | 51,419 |
| (h) `STATS_MANAGER.add_call` | known caller | 216.0 | 4,599,942 | 52,027 |
| (b) `get`, class hit | instance miss, then class hit | 228.6 | 4,187,655 | 44,910 |
| (g) `get_caller_owner_id()` | owner one frame up | 1,017.9 | 975,005 | 103,616 |
| (e) full call, known caller | `api(name)(1)` in a method of an object with `owner_id` | 2,006.4 | 482,275 | 48,657 |
| (d) `get`, miss | raises `APINotFoundError`, inside `pytest.raises` | 2,381.2 | 416,901 | 49,966 |
| (f) full call, caller 20 frames below the owner | same, through 20 plain frames | 4,904.0 | 202,379 | 113,163 |
| (j) `API(owner_id=...)` | construction, 14 instance APIs | 7,504.8 | 127,964 | 185,873 |
| (i) full call, unknown caller | module-level call: warning, stack dump, `LogRecord` | 1,313,884.4 | 610 | 50 |

What the numbers say (arithmetic on the medians above):

- A lookup is cheap: 0.21 to 0.23 microseconds. The miss is dearer (2.4 microseconds) because it
  builds an f-string message and an exception, and the case includes `pytest.raises`; read it as
  an upper bound.
- **The stack walk is half the call.** `get_caller_owner_id` is 1.02 microseconds of the 2.01 for
  a full call. Lookup, walk and stats add up to 1.46; the other 0.54 is `APIItem.__call__` and the
  calling frames.
- **Depth costs about 145 ns per frame.** Twenty extra frames below the owner added 2.90
  microseconds (4.90 against 2.01). `get_caller_owner_id` reads `frame.f_locals` on every frame;
  on Python 3.12 that builds a dict snapshot for each one (**unverified**: I did not measure the
  `f_locals` part alone). Real call sites sit under asyncio and event dispatch, so they may be deeper
  than the benchmark's two or three frames (**unverified**).
- **The unknown-caller path is 655 times a normal call** (1,313,884 against 2,006 ns). A
  separate measurement of its parts at 40 frames deep, in a plain script (**verified**, depth
  differs from the benchmark): `inspect.stack()[1][3]` 517 microseconds, `stackdump` 83,
  `LogRecord(stack)()` 259, the `logger.warning` call 1. The `inspect.stack()` call is in the
  warning's argument list, so it runs even when the level filters the message. Both a
  `logging` warning and a `LogRecord` warning are emitted per call. The benchmark runs under
  pytest's log capture, so the absolute figure is an upper bound for a quiet logger. Startup made
  0 such calls in 108,776 (**verified**), so this is a cost of the exception, not of the rule.
- **Construction is 7.5 microseconds and about 5.2 KB.** `API.__init__` builds 14 `APIItem`s; all
  14 have a description, so `inspect.getcomments` is not called (**verified**: 0 calls). The 5.2 KB
  comes from `tracemalloc` over 1,000 objects (**verified**, approximate). The same probe counted
  12,470 live `API` objects after startup: 9,559 owned by `UpdateRecord`, 2,345 by `LogRecord`, 106
  by `ProcessRaisedEvent` and 126 by event objects (**verified**). At 5.2 KB that is about 65 MB
  (arithmetic, **unverified** as a process total). See AS-6 (fixed in #199).
- Over a startup, 108,776 calls at about 2 microseconds is about 0.22 s of call overhead
  (arithmetic). The call path is not what makes the proxy slow.

---

## Q3: Owner and Caller Tracking

### How the caller is found

`get_caller_owner_id` (`_functools.py`) walks `frame.f_back` from its own frame. For each frame
with a local named `self` that is not an `APIItem`, it takes `self.owner_id` if the object has a
truthy one that is not in the ignore list, otherwise `self.api.owner_id` if `self.api` is an
`API`. The first match wins. No match gives `"unknown"`, a warning and (in `add_call`) a stack
dump.

### What it matches (verified with small classes)

| Case | Result |
| :--- | :--- |
| A plugin method calls an API | The plugin ID (through `self.api.owner_id`). |
| A helper object with its own `owner_id` (a `Callback` or `PersistentDict` stand-in) sits between | The helper's compound ID, for example `plugins.probe.pl:Callback:cb`. The helper counts as the caller, not the plugin that created it. |
| A closure with no `self` | Falls through to the enclosing method's `self`. |
| A module-level call | The `API` object's own `self` is not on the stack, so `unknown`. |
| `libs.api:caller.owner.get` with no ignore list | **The owner of the `API` object it was called through** (AS-4). The bound method `_api_caller_owner_get` is a frame whose `self` is that `API`. |
| Same, with `ignore_owner_list=[own plugin id]` | The real caller. This is how triggers, mudcmds, timers, events and watch call it (13 call sites), and why it works for them. |
| `libs.timing:timing.start` called from `plugins.probe.caller` | Recorded `owner_id` is `bastproxy.libs.timing`. `src/bastproxy/libs/timing.py` calls `caller.owner.get` with no ignore list (AS-4). |

`APIStatItem.add_call` groups by `caller_id.split(":")[0]`. That recovers the plugin from
`plugins.example.myplugin:Timer:name`, but a module owner such as `bastproxy.libs.net.client:<uuid>`
becomes `bastproxy.libs.net.client`, so `calls_by_caller` mixes plugin IDs with module names
(AS-9).

### `libs.api:function.owner.get`

`_api_function_owner_get` reads `tcallable.__self__.plugin_id` and swallows `AttributeError`.
Verified: it returns `unknown` for a plain function, for a bound method of an object that has an
`owner_id` but no `plugin_id`, and for every `libs.*` API (for example
`libs.plugins.loader:plugin.list`, whose `APIItem.owner_id` is `bastproxy.libs.plugins.loader`).
It returns the plugin ID for a bound method of a plugin. Its one user is the events plugin
(`event.register`), so a callback registered from a library object gets owner `unknown`
(**read**: I did not run an event registration from a library object).

### The `bastproxy.` prefix and the two import names

Owner IDs seen on live `API` objects after startup (**verified**): plugin IDs (`plugins.core.*`;
no plugin's own `API` uses a `bastproxy.plugins...` ID), the record classes (`UpdateRecord`, `LogRecord`,
`ProcessRaisedEvent`) and seven names that start with `bastproxy.`:
`bastproxy.libs.asynch`, `.libs.plugins.loader`, `.libs.plugins.reloadutils`,
`.libs.records.managers.records`, `.libs.timing`, `.plugins.core.events.plugin._event` and
`.plugins.core.log.libs._custom_logger`. They are modules that pass `__name__`, and so
the strip exists. After #95 a plugin has one import name, and plugin owner IDs are plugin IDs,
so the strip is not about plugins any more.

- The strip in `_api_api_add_for_object` is **live**: `src/bastproxy/libs/timing.py`, `src/bastproxy/libs/plugins/reloadutils.py`
  and `src/bastproxy/libs/plugins/loader.py` pass `__name__` as the toplevel, and it becomes `libs.timing` etc.
  Without the strip those APIs would register under `bastproxy.libs.timing:...`. (26 class
  `APIItem`s have an owner that starts with `bastproxy.`, **verified**; not all of them come
  through this path.)
- The strip in `API.get` was **not dead** (correction of an earlier claim here that it was dead in
  `src` and tests): the loader's nine `self.api(f"{__name__}:...")` calls built
  `bastproxy.libs.plugins.loader:...` and resolved only through that strip. #202 made them literal
  `libs.plugins.loader:...` strings and removed the strip.
- The simpler design is explicit toplevel strings in those three modules, which makes both strips
  unnecessary (AS-8, AS-9).

---

## Q4: What Is Untested?

`doit coverage` (the whole suite: 4,210 passed, 13 skipped, 1 failed; the failure is
`test_markdown_links` on the new table-of-contents link, added before the page it points to, and
unrelated to this code). Lines for `src/bastproxy/libs/api/`:

```text
Name                                  Stmts   Miss Branch BrPart   Cover   Missing
src/bastproxy/libs/api/__init__.py        3      0      0      0 100.00%
src/bastproxy/libs/api/_addapi.py         9      0      0      0 100.00%
src/bastproxy/libs/api/_api.py          350    175    100      8  49.56%   250->257, 254->257, 268->exit, 289->291, 362-368, 443-448, 505-507, 533-553, 649-656, 680, 728, 754-758, 789-822, 844-859, 882-891, 920-929, 957-962, 980-984, 1005-1025, 1045-1070, 1092-1168
src/bastproxy/libs/api/_apiitem.py       64     35     20      1  38.10%   96->99, 137-139, 156, 175-224, 240, 256
src/bastproxy/libs/api/_apistats.py      40      7     12      0  82.69%   88-90, 151, 172-174
src/bastproxy/libs/api/_functools.py     38      0     14      2  96.15%   77->81, 107->123
```

The missing lines, by symbol:

| Lines | Symbol | Why it matters |
| :--- | :--- | :--- |
| 250->257, 254->257 | `_api_api_add_for_object`, the `bastproxy.` strip | The live strip (Q3) has no test. |
| 289->291 | `_api_api_add_for_object`, `if not instance` | The instance branch that AS-2 depends on. |
| 649-656 | `_api_api_toplevel_remove`, instance loop | **AS-2 lives here.** |
| 505-507, 533-553 | `API.add` `ImportError` fallback; `_api_instance` duplicate and `force` paths | AS-1, and the instance override rules. |
| 680 | `API.get` strip | The dead strip (AS-8). |
| 362-368 | `add_events` | Two event definitions, covered only by startup. |
| 443-448 | `_api_data_get` | Used by every list and detail path. |
| 728, 957-962, 980-984, 1005-1025, 1045-1070 | `_api_api_list_in_toplevel` instance keys, `get_top_level_api_list`, `get_full_api_list`, `_api_data_list`, `_api_api_list_formatted` | **AS-7** (`IndexError` for an empty description) was not caught here. |
| 754-758 | `_api_api_exists` plugin-loaded check | The "its plugin is loaded" rule in the docs has no test. |
| 789-822, 844-859, 882-891, 920-929 | `_api_api_detail_get`, `format_stats`, `_stats_for_specific_caller`, `_stats_overall` | The whole stats display. |
| 1092-1168 | `test()` | Not a test; see below. Removed in #201. |
| `_apiitem.py` 175-224 | `APIItem.detail` | **AS-7** (`TypeError` for `lru_cache`-wrapped methods) was not caught here. |
| `_apiitem.py` 137-139, 156, 240, 256 | `count`, `stats`, `__repr__`, `__str__` | Small. |
| `_apistats.py` 88-90, 151, 172-174 | `ImportError` fallback, `get_all_stats`, `get_stats` | Small. |

`test()` in `_api.py` (about 100 lines from `def test() -> None`) is a `print`-driven self-test
that pytest does not collect and nothing in `src` or `tests` calls (**verified**: no match for
`api.test()`); it is dead code (AS-8). The covered paths include the unknown-caller branch of
`add_call`, which is why its cost went unnoticed. `tests/libs/test_api.py` has 20 tests. (`test()`
was deleted in #201.)

---

## Q5: Where the Docs Disagreed With the Code

Corrected in [API System](api_system.md) in this change:

| Section | Said | Code |
| :--- | :--- | :--- |
| API Class | `stats` is "Global statistics tracking API usage" | `API.stats` was an unused `ClassVar` (**verified**: nothing read it; deleted in #201). Statistics live in the module-level `STATS_MANAGER` (`_apistats.py`). |
| API Class | Listed `_class_api`, `_instance_api`, `stats`, paths and one flag | The class also holds `startup`, `shutdown`, `quiet_mode`, `LOG_IN_UTC_TZ`, `proxy_start_time`, `command_split_regex` and `is_character_active`; each `API` object also builds 14 built-in instance APIs. |
| APIItem Class | Showed `self.owner_id = owner_id` and the description as given | `owner_id or "unknown"`; the description is always a list of lines (split from a string, or taken from the comment above the function); `count`, `stats` and `detail` exist; calling it records the call. |
| AddAPI Decorator | Metadata "processed during plugin initialization" | Also: `addedin` is mutated on the shared function; a decorated method must be named `_api_*` or discovery skips it. |
| API Statistics | Per-plugin grouping | Grouped by the text before the first `:` of the caller ID, so module owners appear under their module name; stats are never removed (AS-3). |
| 5. API Discovery | `BasePlugin.__initialize__()` calls `libs.api:api.add.for.object` | There is no such method. Three hooks call it: `_phook_base_init_add_apis` (priority 1), `_phook_base_init` (75) and `_phook_base_post_initialize_setup` (91). |
| 5. API Discovery | "Scans the plugin object for methods with the `api` attribute" | A `dir()` scan, one level of recursion into attributes, names starting `_api_` only, names formatted with the object's `__dict__`. |
| 6. API Removal | "Removes all APIs with the top-level name" | Called from `_phook_base_unitialize_hook` (priority 100); raises for instance APIs and undecorated functions; leaves stats, empty `addedin` keys and other owners' overrides (AS-2, AS-3). |
| 4. Class vs Instance | Instance APIs "used for per-instance customization" | No plugin declares one (verified). The only instance APIs are the 14 `libs.api:` built-ins on every `API` object, which is why `libs.api:*` names are not in `_class_api`. |
| Automatic Caller Detection | "Typically a plugin ID" | First frame whose `self` is not an `APIItem` and has an `owner_id` or `api.owner_id`; any helper object counts; `unknown` triggers a warning and a stack dump; `caller.owner.get` needs an ignore list (AS-4). |
| API Overwriting | `force=True` overwrites and keeps `overwritten_api` | Also: a duplicate without `force` returns `False` (it returned `True` for class APIs before #194); the overwritten API was not restored before #196 (it is now); nothing in `src` uses `force` (AS-1, AS-3, #201). |
| Common APIs | Loader list presented as complete | A selection. Every `libs.api:` name written on the page was checked against the live registry and exists, as do the loader and events names. The page's `my.plugin` and `some.plugin` names are placeholders. |
| Best Practices, usage 3 | "Cache frequently-used API lookups if performance is critical" | A lookup is 0.2 microseconds of a 2 microsecond call, and a cached `APIItem` goes stale on reload, so the advice is reworded with the numbers. |
| Naming (section 1) | Already matches ADR-0004 (updated by the rename series); examples checked | Unchanged. |
| Calling APIs | `APINotFoundError` | Already correct (fixed by #91); the same sentence now names the `get_class` argument. |

The 14 `libs.api:` instance names and the names in "Common APIs" were compared with the live
registry by a probe (**verified**).

---

## Q6: Patterns and Anti-Patterns

"Keep" means the pattern fits. "Change" means worth an issue. The plugin audit already covers
decorator registration, the string service locator and hidden global state for the plugin system;
those rows link to [that table](plugin_system_findings.md#q5-patterns-and-anti-patterns) and add
only what is specific to the API code.

| # | Pattern or anti-pattern | Where | Consistent? | Verdict |
| --: | :--- | :--- | :--- | :--- |
| 1 | **String-keyed service locator**: `self.api("<toplevel>:<name>")(...)` | `API.get`, `__call__ = get` in `_api.py` | Yes, 173 decorated APIs and every cross-plugin call | **Keep.** Covered by plugin audit row 4, with its name-existence test (`tests/plugins/test_api_names_exist.py`). Measured here: a lookup is 0.21 to 0.23 microseconds and a miss raises `APINotFoundError` (#91, fixed). |
| 2 | **Process-wide registry** as a `ClassVar` | `API._class_api` (`_api.py`) | Yes | **Keep.** Covered by plugin audit row 7. The part that is not covered is removal by toplevel name instead of by owner (AS-3, #196). |
| 3 | **Module-level singleton and class-level flags** | `STATS_MANAGER = StatsManager()` (`_apistats.py`), `API.startup`, `shutdown`, `quiet_mode`, `is_character_active`, path attributes | Yes | **Keep** the flags (plugin audit row 7). **Change** the dead `API.stats` `ClassVar` (deleted in #201) and the stats lifetime: remove one, give the other a removal policy (AS-8, #201; AS-3). |
| 4 | **Caller detection by stack inspection** | `get_caller_owner_id` (`_functools.py`), `APIItem.__call__` | Mechanism yes; results no (any object with an `owner_id` matches; `caller.owner.get` returns the wrong owner without an ignore list) | **Change.** The idea (attribute stats to an owner without passing it in every call) is worth keeping and costs 1 microsecond. Fix the `caller.owner.get` result (AS-4, #197) and the unknown path (AS-5, #198). |
| 5 | **Decorator registration through mutable function attributes** | `AddAPI.__call__` (`_addapi.py`), `addedin` mutated by `_api_api_add_for_object` and `_api_api_toplevel_remove` | Yes | **Keep the decorator** (plugin audit row 3). **Change the `addedin` bookkeeping**: it is shared state on the function, it is only maintained for class APIs, and that asymmetry is AS-2 (#195). |
| 6 | **Four copies of one `dir()` scan** | `get_api_functions_in_object` (`_api.py`), the events plugin's `_events.py`, the commands plugin's `_commands.py`, `_get_plugin_hook_functions` in `_base.py`, each with `except AttributeError: continue` | Same shape, four slightly different filters | **Change (low).** One scanner taking a predicate (AS-11, #204). |
| 7 | **Deferred imports to dodge cycles, with `print` fallbacks** | `from bastproxy.libs.records import LogRecord` inside `API.add`, `_api_instance`, `_api_api_add_for_object`, `_api_api_toplevel_remove` and `APIStatItem.add_call`; `except ImportError: print(...)` in `API.add`, `_api_instance` and `add_call` | Yes | **Change (low).** The fallback in `API.add` is the only path that returns `False` (AS-1, #194); a `print` is not a log. `libs/api` importing `libs.records` is a cycle by design (records build an `API`), so the real fix is to log through the stdlib `logging` module as `get_caller_owner_id` already does. Not filed separately. |
| 8 | **Silent failure by suppression** | `contextlib.suppress(AttributeError)` in `_api_function_owner_get`; `suppress(KeyError)` in `_api_api_detail_get`; `except AttributeError: continue` in the scan | The first hides that most `libs.*` APIs have no owner (Q3) | **Change (low).** Return the owner from `APIItem.owner_id` when the function has no `plugin_id` (AS-9, #202). The `KeyError` suppressions are fine. |
| 9 | **Silent failure by success value** | `API.add` returns `True` for a refused duplicate | n/a | **Change** (AS-1, #194). AGENTS.md says "log errors and raise"; this logs and reports success. |
| 10 | **Type-check escapes** | 12 `# type: ignore` in `_api.py`, 1 in `_addapi.py`, 0 in the other files (**verified** by `grep -c`); `bastproxy.libs.api.*` is in the mypy `ignore_errors` override in `pyproject.toml` | Whole package | **Keep, tracked by #6.** The `ignore_errors` override makes the comments inert today. Do not widen it. The decorator's `func.api` attribute is the cause of most of them; a `Protocol` for "function with `.api`" would remove them. |
| 11 | **Import-time side effects** | `STATS_MANAGER = StatsManager()`; `src/bastproxy/libs/timing.py` builds `API(...)` and `TIMING = Timing()` at import and registers APIs | Yes | **Keep** for `STATS_MANAGER` (an empty dict, no I/O). The registering imports are the architecture. |
| 12 | **Tight coupling: `libs` calls `plugins` by name** | `_api_api_exists` calls `libs.plugins.loader` APIs; `_stats_*` call `plugins.core.utils:table.format`; `API.add_events` and `_api_character_active_set` call `plugins.core.events` | Yes | **Keep, document.** The framework layer reaching into plugins by string name is the service-locator trade (plugin audit row 6). It breaks if the plugin is absent, for example in a unit test; `tests/libs/test_api.py` stubs them. |
| 13 | **Per-object construction of a heavy helper** | `API(owner_id=...)` in 31 constructor call sites in `src` (**verified** by `grep -rnE "(^\|[ (=])(BASE)?API\(owner_id"`), including `src/bastproxy/libs/records/rtypes/base.py` for every record | Yes | **Change** (AS-6, #199). Fixed in #199. |
| 14 | **Dead and misleading surface** | `API.stats`, `test()`, `force=`, `instance=True`, `overwritten_api`, the `get` strip | n/a | **Change** (AS-8). Fixed in #201: `API.stats` and `test()` deleted; `force` and instance APIs kept. |
| 15 | **Strings, not `Path`, for paths** | `API.BASEPATH` and friends are `Path`; API names are not file paths | Yes | **Fits.** |
| 16 | **Untested display and removal paths** | Q4 | n/a | **Change** (AS-10, #203): add tests; AS-2 and AS-7 each carry their own regression test. |
| 17 | **Two owner namespaces** | Plugin IDs against `bastproxy.` module names in stats and `function.owner.get` | No | **Change** (AS-9). |
| 18 | **Display crashes on odd input** | `APIItem.detail`, `_api_api_list_formatted` | n/a | **Change** (AS-7, #200). |

---

## New Defects

### AS-1: `API.add` reports success when it refuses a duplicate

**Issue:** #194
**Location:** `src/bastproxy/libs/api/_api.py` `API.add` (class path), `API._api_instance`.

**Evidence (verified):** Adding `probe.h1:x` twice with different functions and no `force`:

```text
first add returned True
duplicate add (different function, no force) returned True | registered func returns 1
duplicate INSTANCE add returned False
```

The error is logged and the first function stays, but the caller is told it worked. `False`
comes back from the class path only in the `except ImportError` branch, which also `print`s.
`tests/libs/test_api.py::TestAPIOverwriting::test_api_add_duplicate_without_force_fails` asserts
`True` and says so in its docstring.

**Fix:** Return `False` (or raise) for a refused class API, as the instance path does, and decide
whether the one caller that ignores the result (`_api_api_add_for_object`) should log it. The
existing test asserts the old behaviour, so changing it is a decision for the maintainer, not part
of a refactor.

**Fixed in #194:** `API.add` now returns `False` for a refused class duplicate, as the instance path does, and the `ImportError` fallbacks in `API.add`, `_api_instance` and `APIStatItem.add_call` log through the stdlib `logging` module instead of `print`. The test above now asserts `False` (maintainer-approved), and `tests/libs/test_api.py` restores the shared `API._class_api` and `STATS_MANAGER.stats` around every test. The text above describes the behaviour before the fix.

### AS-2: `api.toplevel.remove` raises for instance APIs and for undecorated functions

**Issue:** #195
**Location:** `src/bastproxy/libs/api/_api.py` `_api_api_toplevel_remove` (instance loop) and
`_api_api_add_for_object` (`if not instance`).

**Evidence (verified):** A plain object with one `@AddAPI(..., instance=True)` method and one
class method, added with `libs.api:api.add.for.object` and removed with `api.toplevel.remove`:

```text
addedin {'probe.h3': []} {'probe.h3': ['h3.cls']}
remove RAISED ValueError list.remove(x): x not in list
class keys after []
instance keys after ['probe.h3:h3.inst']
```

A function added with `libs.api:api.add` but not decorated:

```text
remove undecorated bound method RAISED AttributeError 'function' object has no attribute 'api'
class key left: True
remove plain function RAISED AttributeError 'builtin_function_or_method' object has no attribute 'api'
```

Today nothing hits it: no `@AddAPI(instance=True)` user exists, and the two manual adds in `src`
(`_pluginm.py`, `libs/asynch`) belong to toplevels that are never removed. Through the base hook the
`ValueError` would abort `uninitialize` part-way, after the `unloaded` events were raised.

**Fix:** Append to `addedin` for instance APIs too (or do not use it for them), skip functions
with no `.api`, and delete every key before reporting an error. Add tests for both cases (lines
649-656 are uncovered).

**Fixed in #195:** `_api_api_toplevel_remove` now tolerates instance APIs and functions with no `.api`
(via `_discard_addedin`) and always deletes every key; regression tests are in
`tests/libs/test_api.py::TestToplevelRemove`.

### AS-3: Stats, `addedin` keys and overrides outlive the plugin

**Issue:** #196. **Fixed in #196**: removal now prunes the stats, deletes the `addedin` entry and
undoes the removed owner's force-overrides in other toplevels (restoring `overwritten_api`, or
deleting the entry). The evidence below is from before the fix.
**Location:** `_apistats.py` `StatsManager.stats`; `_api.py` `_api_api_toplevel_remove`, `API.add`.

**Evidence (verified):** After unloading `plugins.test.cmddec` the registry held 0 of its APIs and
the stats manager 2 entries for it (it had 1 before; the unload itself called two of its APIs). After the reload, the same
`APIStatItem` carried on: the `data.directory.get` count went from 1 to 2. `addedin[plugins.test.cmddec]`
stayed as an empty list. An API force-overridden by another owner stays after that owner's
toplevel is removed, still owned by it (probe: `p.victim:f` stays owned by `p.over`).

**Fix:** Decide the policy and write it down: either drop the stats for a removed key (and say that
reload resets counts) or keep them on purpose and prune only names that no longer exist. Remove
`addedin` keys when the list empties. Remove by owner as well as by toplevel, restoring
`overwritten_api`, or remove `force` (AS-8; #201 kept `force`).

### AS-4: `libs.api:caller.owner.get` returns the owner of the API it was called through

**Issue:** #197 (fixed: `get_caller_owner_id` skips every `API` frame, and `libs.timing` passes its own API owner as the ignore list; the findings below describe the code at audit time)
**Location:** `_api.py` `_api_caller_owner_get`; `src/bastproxy/libs/timing.py` `_api_timing_start`,
`_api_timing_finish`.

**Evidence (verified):**

```text
timing.start called by plugins.probe.caller -> recorded owner_id: bastproxy.libs.timing
caller.owner.get via caller's api, invoked inside Other.who: plugins.probe.caller (Other is the real caller)
with ignore_owner_list=[self id]: plugins.probe.outer (expected plugins.probe.outer)
```

`_api_caller_owner_get` is itself a frame with an `API` as `self`, so with nothing to ignore it
matches that. The thirteen call sites in triggers, mudcmds, timers, events and watch pass
`ignore_owner_list=[self.plugin_id]`, which is why they work. `src/bastproxy/libs/timing.py` does not, so the
`owner_id` stored for each timer, and the `sources` of its `LogRecord`s, is always the timing module.

**Fix:** Skip the `_api_caller_owner_get` frame (and every `API` frame) in
`get_caller_owner_id`, so no ignore list is needed to get the caller. Add a test that calls
`caller.owner.get` with no list from an object with an `owner_id`.

### AS-5: The unknown-caller path costs about 1.3 ms per call and logs twice

**Issue:** #198
**Location:** `_functools.py` `get_caller_owner_id` (`inspect.stack()[1][3]`), `_apistats.py`
`APIStatItem.add_call`.

**Evidence (verified):** Benchmark (i) median 1,313,884 ns against 2,006 ns for a known caller (Q2).
At 40 frames: `inspect.stack()` 517 microseconds, `stackdump` 83, `LogRecord` 259. Each call
emits a `logging` warning and a `LogRecord` warning with the full stack. A startup made 0 such
calls in 108,776, so this is latent; a plugin that calls an API from a thread, a callback with no
owner or a library helper pays it on every call, and the stack dump goes to the log each time.

**Fix:** Use `sys._getframe(1).f_code.co_name` (or nothing) instead of `inspect.stack()`, and
emit the stack dump once per API name and caller rather than per call. Keep the stats entry.

**Fixed in #198:** `get_caller_owner_id` reads the calling function's name from the frame
(`inspect.currentframe().f_back.f_code.co_name`, read only on the unknown path, with the frame deleted so it forms no reference cycle) instead of `inspect.stack()`, and `APIStatItem.add_call`
logs the stack dump once per API and caller id (`_dumped_callers`); the call is still counted. Benchmark (i)
median went from 1,292,888 ns to 24,423 and 25,312 ns in two runs (`doit benchmark_compare` against the saved baseline,
same machine; the first round, which logs the dump, is in the mean, not the median). The text
above describes the behaviour before the fix.

### AS-6: Every `API` object builds 14 `APIItem`s, and every record has one

**Issue:** #199
**Location:** `_api.py` `API.__init__`; `src/bastproxy/libs/records/rtypes/base.py` and
`update.py`.

**Evidence (verified):** Benchmark (j): 7.5 microseconds per `API(...)`; `tracemalloc` over 1,000
objects about 5.2 KB each. Live `API` objects after startup: 12,470, of which `UpdateRecord`
9,559 and `LogRecord` 2,345. 31 constructor call sites in `src`.

**Fix:** The 14 built-ins are bound methods of the object, which is why each object needs its own.
Resolve the `libs.api:` names in `API.get` from a fixed method table (no `APIItem` per object),
or give records a shared `API`. Measure with `test_bench_api_construct` before and after. This
overlaps the record cost work in #81 and #106; check them before starting.

**Fixed in #199:** The 14 built-ins live in a class-level table, `BUILTIN_APIS`
(`_builtins.py`). `API._instance_api` is an `InstanceAPIs` mapping: construction binds and
registers nothing, and a built-in is bound and wrapped in an `APIItem` the first time it is
resolved. Enumeration, `del` (which hides a built-in for that object only) and overrides work as
they did on the dict. Benchmark (j) `test_bench_api_construct` median went from 8,126 ns to
259 ns (`doit benchmark_compare` against the saved baseline, same machine). The text
above describes the behaviour before the fix.

### AS-7: `api.detail.get` and `api.list.formatted` crash on some APIs

**Issue:** #200
**Location:** `_apiitem.py` `APIItem.detail` (`inspect.getsourcefile`); `_api.py`
`_api_api_list_formatted` (`api_data.description[0]`); `src/bastproxy/plugins/core/fuzzy/plugin/_fuzzy.py`.

**Evidence (verified):** `item.detail()` over all 301 class APIs raised for two:

```text
plugins.core.fuzzy:string.match.best  TypeError: module, class, method, function, traceback, frame, or code object was expected, got _lru_cache_wrapper
plugins.core.fuzzy:string.match.top   (same)
```

An API added with no description and no comment above the function has `description == []`, and
`api.list.formatted` raised `IndexError: list index out of range` for it. `APIItem.detail` also
formats the function's docstring with `% tdict`, so a docstring with a literal `%` would raise
(**read**, not run).

**Fix:** Unwrap with `inspect.unwrap` (or `functools.wraps`) before `getsourcefile`; use
`description[0] if description else ""`; use `str.replace` for the docstring fields. Drop the
`lru_cache` on instance methods in the fuzzy plugin (it keys the cache on `self`, the shape #100
removed). Tests for every `detail()` over the live registry belong in AS-10.

### AS-8: Dead surface in `libs/api`

**Issue:** #201
**Location:** `_api.py` (`API.stats`, `test()`, `API.get` strip), `_apiitem.py`
`overwritten_api`, `force=` and `instance=True`.

**Evidence (verified by `grep`):** Nothing reads `API.stats`; the page described it as the global
stats. No `src` file passes `force=True` or declares `instance=True` outside `libs/api`. `test()`
is not called. (The `API.get` strip was live, not dead; see Q3 and #202.)

**Fix:** Delete `API.stats`, `test()` and the `get` strip. Decide whether instance APIs and
`force` are features to keep (then they need users, tests and a removal path, AS-2 and AS-3) or
code to delete.

**Fixed in #201:** Deleted the `API.stats` `ClassVar` and the module-level `test()` function with its
`if __name__ == "__main__"` block, plus the `pprint` and `APIStatItem` imports only they used
(`git diff --numstat`: 107 lines deleted and 1 changed import line in `_api.py`). The `bastproxy.` strip in `API.get` was
already gone through #202. Decision: `force` and instance APIs are kept as supported features, for
three reasons: both are tested; since #196 removing a top-level restores what a force-override
replaced (or deletes the entry when none was saved); and since #199 the `libs.api:` built-ins share
the per-object `_instance_api` store. Added tests for the instance paths that had none: an instance
`force` override keeps `overwritten_api` and calls the new function, and removing the overriding
owner restores or deletes an overridden instance API. See
[api_system.md, API Overwriting](api_system.md#api-overwriting).

### AS-9: Two owner namespaces in stats, and `function.owner.get` knows only plugins

**Issue:** #202
**Location:** `_apistats.py` `APIStatItem.add_call`; `_api.py` `_api_function_owner_get`;
`src/bastproxy/libs/timing.py`, `src/bastproxy/libs/plugins/loader.py`, `src/bastproxy/libs/plugins/reloadutils.py` (`__name__` as toplevel).

**Evidence (verified):** `calls_by_caller` gets `plugins.probe.pl` for a plugin helper and
`bastproxy.libs.net.client` for a module owner. `function.owner.get` returns `unknown` for the
loader's `plugin.list`, whose `APIItem.owner_id` is `bastproxy.libs.plugins.loader`.

**Fix:** Pass explicit toplevel strings instead of `__name__` and drop the `bastproxy.` strip
(this is the one the live strip exists for); have `function.owner.get` fall back to the owner of
the registered `APIItem`. Pick one owner namespace for stats and write it in the docs.

**Fixed in #202:** Library owner IDs and toplevels are explicit strings without the `bastproxy.`
prefix (`libs.timing`, `libs.net.client`). Both strips (`_api_api_add_for_object` and `API.get`)
are removed. `function.owner.get` falls back to the registered `APIItem.owner_id`. The namespace
is written in [api_system.md, Owner IDs](api_system.md#owner-ids). The event name
`ev_bastproxy.libs.plugins.loader_post_startup_plugins_loaded` is unchanged
(`POST_STARTUP_EVENT`).

### AS-10: The display, stats and removal paths of `libs/api` have no tests

**Issue:** #203
**Location:** `tests/libs/test_api.py`, `src/bastproxy/libs/api/`.

**Evidence (verified):** `_api.py` 49.56% and `_apiitem.py` 38.10% (Q4 table).

**Fix:** Add tests for `_api_api_detail_get`, `format_stats`, `_api_data_list`,
`_api_api_list_formatted`, `get_top_level_api_list`, `get_full_api_list` and
`APIItem.detail` over a small registry, plus `detail()` over every class API after a startup
(it would have found AS-7). AS-1 to AS-4 carry their own regression tests.

### AS-11: Four copies of the `dir()` scan

**Issue:** #204
**Location:** `_api.py` `get_api_functions_in_object`; `_events.py` and `_commands.py` (the
`dir(base)` scans for event and command decorators); `_base.py` `_get_plugin_hook_functions`.

**Evidence (read):** Each walks `dir()`, skips `__` names, calls `getattr` inside
`try/except AttributeError`, and filters on a decorator attribute. I read the four; I did not
diff them line by line.

**Fix:** One helper in `libs` that yields `(name, attr)` pairs for bound methods and takes the
predicate, used by the four. Low priority; do it with AS-2, which already touches the scan.

**Fixed in #204:** `bastproxy.libs.scan.find_methods` walks `dir()`, skips `__` names, swallows
only `AttributeError` from `getattr`, and keeps bound methods that pass a predicate. The API,
events and commands scans and `BasePlugin._collect_plugin_hook_functions` (which
`_get_plugin_hook_functions` calls) use it. Each keeps its own filter, return shape and the API's
self-recursion guard. The text above describes the code before the fix.

---

## Other Observations

- **Plugin load scans every attribute three times** (verified): the events plugin took 0.36 ms
  per `get_api_functions_in_object` call, so about 1 ms for the three calls. A `getattr` on a
  property runs its code during the scan (**read**).
- **`get` checks `self._instance_api[api_location]` for truthiness after checking membership**
  (`_api.py`, **read**); harmless.
- **`__call__ = get`** binds at class creation; a subclass that overrides `get` would not change
  calls (**read**). No subclass exists.
- **`_api_api_list_in_toplevel("")` would raise `IndexError`** on `parent_api[-1]` (**read**,
  not run).
- **`_api_data_list` and `_api_api_list_formatted` reuse `api_data` as both the list being
  iterated and the loop's walrus target** (`_api.py`, **read**); it works because the `for`
  already holds the list, but it is easy to break.
- **Security:** none found. The `%` and `.format(**__dict__)` calls take their templates from
  decorators in code, not from input (**read**).

---

**Document Version:** 1.0
**Last Updated:** 2026-11-08
