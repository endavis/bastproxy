---
title: Triggers System Analysis and Findings
description: Audit of the triggers plugin - how a MUD line reaches a trigger, state consistency, failure handling, cost, test coverage, docs accuracy, patterns and a design assessment with alternatives measured
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - triggers
  - review
---

# Triggers System Analysis and Findings

**Date:** 2026-11-11
**Analyzer:** Claude Fable 5.2
**Scope:** The triggers plugin in `src/bastproxy/plugins/core/triggers/`
(`src/bastproxy/plugins/core/triggers/plugin/_triggers.py`: `TriggerItem`, `TriggersPlugin`), its ten APIs and
the matching path (`rebuild_regexes`, `_eventcb_check_trigger`, `process_match`, `TriggerItem.raisetrigger`):
line flow, state consistency, failures, cost, test coverage, docs accuracy, patterns and the design itself
(audit issue #345). Compared against [Triggers System](triggers_system.md). Base commit `4fda9a5`.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [Status of the Known Items](#status-of-the-known-items)
4. [Q1: How Does a Line Reach a Trigger?](#q1-how-does-a-line-reach-a-trigger)
5. [Q2: Is the Trigger and Regex Data Kept Consistent?](#q2-is-the-trigger-and-regex-data-kept-consistent)
6. [Q3: What Happens on a Failure?](#q3-what-happens-on-a-failure)
7. [Q4: What Does a Line Cost?](#q4-what-does-a-line-cost)
8. [Q5: What Is Untested?](#q5-what-is-untested)
9. [Where the Docs Disagreed With the Code](#where-the-docs-disagreed-with-the-code) (Q6)
10. [Q7: Patterns and Anti-Patterns](#q7-patterns-and-anti-patterns)
11. [Q8: Design Assessment](#q8-design-assessment)
12. [New Defects](#new-defects)
13. [Other Observations](#other-observations)

---

## Executive Summary

The triggers plugin works for the one case the repository uses: a plugin adds a trigger whose regex starts at
the beginning of the line, registers a callback, and no other trigger matches the same line. Outside that case
most of the API surface does something other than what its name and the docs say. Fourteen items are proposed
below (TR-1 to TR-14); eleven are defects found by running the code.

- **One regex fires per line, and `priority` is not used** (TR-1). All regexes are joined into one alternation,
  which reports only the first alternative that matches, in the order the regexes were added. Two triggers
  with different regexes never both fire (Q1c).
- **One of the ten APIs does not work.** `group.toggle.enable` changes nothing (TR-4). Before #348,
  `trigger.update` raised `TypeError` on every call (TR-3, fixed); before #347, `trigger.toggle.enable` could
  not enable a trigger that was added disabled (TR-2, fixed).
- **One regex can stop the matcher from being updated** (TR-5). A regex with a named backreference compiles
  alone and breaks the combined pattern; from then on every trigger added is dead, without an error at the
  call that added it. Numeric backreferences and a literal `\?P<x>` are changed silently.
- **A failure inside matching drops the rest of the line's triggers** (TR-7): an `argtypes` conversion that
  raises, or a callback that removes its own trigger, ends `_eventcb_check_trigger` for that line.
- **The `enabled` setting does nothing** (TR-11), `matchcolor` only works for regexes that also match the
  uncoloured text (TR-6), and triggers without a regex, the three built-ins included, raise `KeyError` from
  remove and toggle (TR-8).
- **Unload is clean for triggers and their callbacks** (Q2e, **verified**), except for group entries, which
  are never removed, and for an owner that has a trigger without a regex.
- **Cost** (Q4): matching is cheap at realistic sizes, 6 us for a line that matches nothing against 100
  triggers. The two built-in events raised for every line cost about 250 us with nothing listening, and
  loading 1,000 triggers one by one took 47 s because the combined pattern is recompiled on every add (TR-10).
- **Tests** (Q5): the plugin file is about 30% covered. No API method except `trigger.register` and
  `trigger.unregister` has a test (TR-12).
- **Design** (Q8): change the matcher, keep the API. Match each enabled trigger's own compiled regex in
  priority order; that removes TR-1, TR-5 and TR-6 as classes of bug and makes `priority` and
  `stopevaluating` mean what the docs said. No new dependency is needed (TR-14, needs an ADR).

**Key Findings:**

- 14 proposed issues: 11 defects (TR-1 to TR-11), a test gap (TR-12), a benchmark (TR-13) and the design
  change (TR-14). Each is filed as its own issue, #346 to #359; each entry under [New Defects](#new-defects)
  links its issue and keeps the body it was filed with.
- The code disagreed with [Triggers System](triggers_system.md) in 17 places; the page is corrected for all of
  them, and one line of [Event System](event_system.md) is corrected.

---

## How This Was Verified

Claims below are tagged **verified** (run against the code, output saved), **read** (from reading the code,
not executed) or **unverified**.

Verification used throwaway scripts, deleted afterwards and not part of the repository. Python ran with
`BASTPROXY_HOME` set to the checkout. Environment: Python 3.12.12, `regex` 2026.9.29, Linux 6.17.13-2-pve,
12th Gen Intel Core i7-12650H. Every timing is from a single run and varies with load.

- **Real boot** (Q1, Q2, Q3, the `enabled` setting, the event-raise cost in Q8): scripts that boot the real
  plugin system in-process (`PluginLoader().load_plugins_on_startup()`, then `startup` set to False as
  `bastproxy` does, no listeners), add triggers through the real APIs, and raise
  `ev_to_client_data_modify` with real `NetworkDataLine` objects as a `data_list` with `key_name="line"`, the
  way `ProcessDataToClient` does. A handler on the root logger collected every ERROR record. For unload and
  reload a throwaway user plugin was written under `$BASTPROXY_HOME/plugins` (it loads as
  `plugins.audit345.<name>`) and deleted afterwards (`out-q1_flow.txt`, `out-q2_state.txt`,
  `out-q3_failures.txt`, `out-q8_raise.txt`).
- **Stub harness** (Q4, Q8): a stand-in object with the plugin's real dictionaries, calling the unbound
  `TriggersPlugin` methods as `tests/plugins/core/triggers/test_trigger_mxp.py` does, with the event raise
  replaced by a no-op so that only matching is timed (`out-q4_cost.txt`, `out-q4b_cost.txt`). Prototypes of
  the alternatives ran on the same generated regexes and lines.
- **`google-re2`** (Q8): not a dependency. It was run once with `uv run --with google-re2`, which installs
  nothing into the project (`out-q8_re2.txt`, version 1.1.20251105).
- **TinTin++** (Q8): the installed client's own `#help action`, `#help gag`, `#help regex` and
  `#help substitute` (`out-tt_help.txt`, TinTin++ 2.02.20). Mudlet and MUSHclient are not installed; what is
  said about them is **unverified**.
- **Coverage** (Q5): `uv run doit coverage` (`coverage.txt`: 5,289 passed, 13 skipped) and
  `uv run pytest tests/plugins/core/triggers --cov=bastproxy.plugins.core.triggers --cov-branch --cov-report=term-missing -q`
  (`coverage-narrow.txt`: 9 passed).
- **Greps** (Q6, Q7): scoped to `src/bastproxy/plugins/core/triggers` (`out-q7-greps.txt`) and, for event and
  API names, to `src` and `tests` (`out-docs-checks.txt`).

---

## Status of the Known Items

| Item from the issue | Status | Where |
| :--- | :--- | :--- |
| #257: `trigger.register` passed its keyword arguments positionally | **Fixed, and holds** (**verified**: `tests/plugins/core/triggers/test_trigger_register_kwargs.py` passes; the probes registered callbacks with `prio=1` through `trigger.register`). | #257 |
| #335: the debug line for an unmatched line is built only when logged | **Settled** (**verified**: `tests/plugins/core/triggers/test_trigger_debug_log_lazy.py` passes). | #335 |
| #61: triggers match MXP-stripped text | **Holds** (**verified**: `tests/plugins/core/triggers/test_trigger_mxp.py` passes; `noansi` and `colorcoded` both strip MXP first, **read**). | #61 |
| To check: does turning the `enabled` setting off stop matching? | **No** (**verified**, Q2f). The setting has no effect. | TR-11 |
| To check: does a line that two triggers match fire both, and does order or priority decide? | **Only with the same regex.** With different regexes only the first added fires; `priority` is not read (**verified**, Q1c). | TR-1 |
| To check: which triggers are live when the combined regex fails to compile? | **The ones in the last pattern that compiled.** Triggers added later never fire, and the offending trigger never fires either (**verified**, Q3b). | TR-5 |

---

## Q1: How Does a Line Reach a Trigger?

### Q1a: The path

**Verified** by `out-q1_flow.txt` unless marked.

1. `ProcessDataToClient._exec_` raises `ev_to_client_data_modify` once per record, with every line that is
   from the MUD and is I/O as a `data_list` (**read**, `src/bastproxy/libs/records/rtypes/clientdata.py`).
2. `TriggersPlugin._eventcb_check_trigger` is the callback, registered by its `@RegisterToEvent` decorator at
   priority 50. It runs once per line.
3. A line with `internal` set returns at once: no built-in, no regex.
4. `beall` is raised: `self.triggers[self.beall_id].raisetrigger(event_record)`.
5. The text is `line.noansi`. If it is `""`, `emptyline` is raised and no regex is tried.
6. Otherwise `created_regex["created_regex_compiled"].match(data)` runs. The pattern is
   `(?P<reg_1>...)|(?P<reg_2>...)|...`, one alternative per distinct regex that has an enabled trigger, in the
   order the regexes were first added. The groups that are not `None` are the matched regexes; since the
   alternation is at the top level, that is at most one.
7. `process_match` adds a hit to the regex and loops over `regexes[regex_id]["triggers"]` in list order. For
   each trigger whose `enabled` is true it matches `original_regex_compiled` again, against `line.colorcoded`
   when `matchcolor` is set and `line.noansi` otherwise.
8. On a second-stage match: `groupdict()`, the `argtypes` conversions, `args["matches"] = group_dict`, then
   `raisetrigger(args)`, which counts a hit, sets `line.sendtoclients = False` when `omit` is set, writes
   `trigger_name` and `trigger_id` into `args` and raises `event_<trigger_id>` with `args` as its data.
9. `stopevaluating` breaks the loop of step 7.
10. `all` is raised.

For `HP: 10/20 ok` with one trigger `^HP: (?P<cur>\d+)/(?P<max>\d+)` and `argtypes` of `int`, the callbacks ran
in the order `beall`, `hp` (matches `{'cur': 10, 'max': 20}`), `all`. An `omit` trigger left
`line.sendtoclients` False.

### Q1b: The regex is anchored at the start of the line

**Verified.** The combined pattern is used with `match`, so a regex must match from the first character.
A trigger `orc` did not fire on `You hit orc.` and did fire on `orc hits you.`; `.*orc` fired on the first.
The old page's examples (`r"HP: (\d+)/(\d+)"`, `r"You hit .* for (?P<damage>\d+) damage"`) work only when the
line starts with that text. This is behaviour to document, not a defect on its own; TinTin++ does the opposite
by default (Q8). The page now says so.

### Q1c: Overlapping triggers and priority (TR-1)

**Verified.** Three triggers were added in this order: `^You slash (\w+)` at priority 200,
`^You slash .*` at priority 1, and `^You (?:slash|hit) (?P<who>\w+)\.$` at priority 50. On
`You slash goblin.` only the first one fired. `priority` is assigned in `TriggerItem.__init__` and read only by
`_command_detail` (**read**: the greps find no other use).

Triggers that share a regex do all fire, in the order they were added: `^The (?P<a>\w+) dies\.$` and
`^The (?P<b>\w+) dies\.$` from two owners share `reg_8` (named groups are made unnamed before the lookup) and
both fired on `The elf dies.`, each with its own group name in `matches`.

`stopevaluating` stops only the later triggers on the same regex. With `^STOP here$` added twice, the first
with `stopevaluating`, the second did not fire. Across regexes it decides nothing: a `stopevaluating` trigger
on `^S3 .*` added after a plain `^S3 x$` never ran on `S3 x`, because the earlier regex won.

One trigger can also shadow another by accident. During the probe a trigger `.*orc` added early took the line
`The orc dies.` away from the two `dies` triggers added later.

### Q1d: `matchcolor` (TR-6)

**Verified.** For a line that is a bold red `WARNING` followed by a reset and `: fire`, the two forms are `WARNING: fire` (`noansi`) and
`@RWARNING@x: fire` (`colorcoded`). The combined pattern is always matched against `noansi`; only the second
stage uses `colorcoded`.

| Trigger regex, `matchcolor=True` | Fired? | Why |
| :--- | :--- | :--- |
| `^@RWARNING` | No | Fails the first stage: the uncoloured text has no `@R` |
| `^ALERT` (line `@RALERT@x: fire`) | No | Passes the first stage, fails the second: the coloured text starts with `@R` |
| `.*DANGER.*` | Yes | Matches both forms |

A `matchcolor` trigger that fails the second stage also shadows: a plain trigger `.*ALERT.*` added after
`^ALERT` did not fire on the same line, because the first stage had already chosen the `^ALERT` regex.

### Q1e: Empty lines and the built-ins (TR-8)

**Verified.**

- `""` raises `beall`, `emptyline`, `all`. A line of colour codes only (`ESC[0m`) is empty too. A line of three
  spaces is not: it raises `beall` and `all` only.
- A regex trigger `^$` never fires: the empty-line branch skips the regexes.
- The three built-ins are added with `enabled=False` and are raised for every line anyway; nothing checks the
  flag for them, and the `list` command shows them as disabled.
- They are passed the outer event's `EventDataRecord`, so after one line the record of
  `ev_to_client_data_modify` has the keys `line`, `trigger_id`, `trigger_name` (#230; [Data Flow](data_flow.md)).
- `beall` and `all` are raised whether or not a callback is registered. Q4 has the cost.

### Q1f: Regexes that change meaning in the combination (TR-5)

**Verified.** `^(\w+) says \1$` matches `bob says bob` when compiled alone and did not fire as a trigger: in
the combined pattern `\1` is the first group of the whole alternation, which is another regex's `reg_1`. The
other two cases, a named backreference and a literal `\?P<x>`, are in Q3b.

### Q1g: Not covered here

Prompts and lines without a line ending reach the callback like any other line: `_eventcb_check_trigger` does
not look at how a line ended (**read**). Whether the reader splits a slow line into two partial lines, which
would make a `$`-anchored regex miss, belongs to the network layer and was not probed (**unverified**).

---

## Q2: Is the Trigger and Regex Data Kept Consistent?

**Verified** by `out-q2_state.txt` and `out-q3_failures.txt` unless marked. The calls came from a throwaway
plugin, so the owner lookup was the real one.

### Q2a: Add

- `trigger.add` returns `(True, TriggerItem)` on success and a bare `False` for a duplicate name, a regex that
  does not compile, or no owner (TR-9).
- `TriggerItem.event_name` is always `event_<trigger_id>`. `_api_trigger_add` computes
  `args["event_name"] = f"{owner_id}_trigger_{trigger_id}"` and `TriggerItem.__init__` ignores the argument; a
  caller's own `event_name=` keyword is ignored the same way (TR-9).
- A regex that fails to compile leaves its entry behind: `regexes` grew by one and `regex_lookup_to_id` kept
  the string, though no trigger was stored (TR-10).
- A trigger added with `enabled=False` is stored with an empty trigger list on its regex and is not in the
  combined pattern.

### Q2b: Toggle (TR-2)

Fixed by #347. Before #347, `trigger.toggle.enable` edited `regexes[regex_id]["triggers"]` and never set
`TriggerItem.enabled`, which `process_match` checks. The table is the behaviour before #347.

| Case | `.enabled` after | In the regex list | Fired on its line |
| :--- | :--- | :--- | :--- |
| Added `enabled=False`, then toggled on | False | Yes | **No** |
| Added enabled, then toggled off | True | No | No |
| Then toggled on again | True | Yes | Yes |

So, before #347, a trigger created disabled could never be enabled, and the `list` command and the stats event, which read
`.enabled`, keep the value from creation. An unknown trigger name logs an error and returns `None`.

### Q2c: Group toggle and group data (TR-4)

`trigger_groups` stores trigger ids. `group.toggle.enable` passes each id to `trigger.toggle.enable` as if it
were a name, which builds `t_<owner>_t_<owner>_<name>`. For a group of two, the call logged two
"does not exist" errors, and both triggers still fired afterwards. An unknown group returns `None` without a
message.

Group entries are never removed. After `trigger.remove(..., force=True)` the id was still in the group; after
an unload the group still listed the unloaded plugin's trigger; after a second load and a reload the same id
was in the list three times.

### Q2d: Update (TR-3)

`trigger.update` raised `TypeError: 'TriggerItem' object is not subscriptable` at
`old_value = self.triggers[trigger_id][key]` for `{"omit": True}` and for `{"regex": ...}`. An unknown name
returns `False` with an error log. The rest of the method was read, not run, since it cannot be reached: the
`group` branch indexes `self.triggers[trigger_name]` (a name, not an id) and stores names in a dictionary of
ids, the `regex` branch never updates `TriggerItem.regex` or `regex_id`, and `setattr` runs for any key,
including `regex`, before the new regex is compiled (**read**).

### Q2e: Remove, unload and reload

- `trigger.remove` is refused, with an error log and `False`, while a callback is registered on the trigger's
  event; `force=True` removes it. The trigger's `Event` object stays in the events plugin either way (the
  events audit covers that).
- The regex entry stays with an empty list; `regexes` and `regex_lookup_to_id` only grow (TR-10).
- **Unload is clean for the triggers themselves.** For a plugin with a registered trigger and an unregistered
  one, after `plugin.unload` no trigger of the plugin was left, both regex lists were empty and the combined
  pattern was `""`. All callbacks of `ev_plugin_unloaded` are at priority 50 and run in the order commands,
  events, mudcmds, settings, timers, triggers, watch, so the events plugin has removed the owner's callbacks
  before the triggers plugin asks, and no removal is refused. This depends on that order, not on `force`
  (**read**: `_api_trigger_remove_for_owner` passes no `force`).
- **Load again and reload work** in that case: the triggers are added again, share the old regex ids, and the
  callback fired after the reload.
- **A trigger without a regex breaks it** (TR-8). `trigger.remove` and `trigger.toggle.enable` do
  `self.regexes[self.triggers[trigger_id].regex_id]`, and `regex_id` is `None` for a trigger added without a
  regex, so both raised `KeyError: None`; so did toggling the built-in `all`. On unload the `KeyError` came out
  of `_eventcb_plugin_unloaded` (logged by the event system) and ended the loop in
  `trigger.remove.for.owner`: the triggers after the bad one in dictionary order stay. In the probe the
  leftover trigger was first in the dictionary on the next unload, so the reload removed nothing and every
  `trigger.add` of the reloaded plugin failed with "already exists".
- `trigger.register` and `trigger.unregister` raised `KeyError` for an unknown trigger (TR-9).
- The triggers plugin sets `can_reload_f = False`; `plugin.reload` on it returned `False` with
  "cannot be unloaded".

### Q2f: The `enabled` setting (TR-11)

With the setting True a line fired its trigger. After `setting.set("plugins.core.triggers", "enabled", False)`
the same line fired it again. `_eventcb_enabled_modify` registers and unregisters `_eventcb_check_trigger` on
`ev_libs.net.mud_from_mud_event`; that event exists only because of this registration (priority 1, raised 0
times), and nothing in `src` or `tests` raises it (`out-docs-checks.txt`). The decorator registration on
`ev_to_client_data_modify` was still there after both changes.

### Q2g: Hit counts

`TriggerItem.hits` counts every raise (#252 holds: after the Q1 probe `beall` had 22 hits and `all` 20, the
difference being the two lines that failed in Q3c). `regexes[id]["hits"]` counts first-stage matches, so it
also counts a line whose triggers all failed the second stage (**read**).

---

## Q3: What Happens on a Failure?

**Verified** by `out-q3_failures.txt` and `out-q1_flow.txt`.

### Q3a: A regex that does not compile

`trigger.add("bad", "^(abc")` logs the error with the traceback and returns `False`. No trigger is stored and
the matcher is unchanged. The regex table keeps the entry (Q2a).

### Q3b: A regex that compiles alone and breaks the combined pattern (TR-5)

`^(?P<w>\w+) says (?P=w)$` compiles and matches `bob says bob` on its own. The named-group strip turns it into
`^(\w+) says (?P=w)$`, so the combined pattern has a reference to a group that no longer exists.

1. `trigger.add` returned `(True, item)`. The only sign was an error log from `rebuild_regexes`,
   "Could not compile created regex", with `unknown group`.
2. `created_regex["created_regex"]` held the new string; `created_regex_compiled` was still the previous
   pattern.
3. A trigger added before it kept firing. A trigger added after it (`^after (?P<y>\w+)$`) **never fired**; its
   `trigger.add` also returned success, with the same error log. The backreference trigger itself never fired.
4. Removing the earlier trigger returned `True` and logged the compile error again; its alternative stayed in
   the stale matcher, pointing at an empty trigger list.
5. After the backreference trigger was removed, the rebuild succeeded and the later trigger fired.

So one plugin's regex can silence every trigger added after it, for all plugins, until it is unloaded.
If the first rebuild ever fails, `created_regex_compiled` stays `""` and nothing matches (**read**).

The strip also damages a literal: `^tag \?P<b> end$` was stored as `^tag \ end$` and did not fire on
`tag ?P<b> end`.

### Q3c: A failure inside `process_match` (TR-7)

`process_match` runs inside the `ev_to_client_data_modify` callback with no `try`. Anything that raises there
ends `_eventcb_check_trigger` for that line: the event system logs it, the remaining triggers on the regex are
skipped and `all` is not raised.

- **`argtypes`.** `^val (?P<n>\w+)` with `{"n": int}` on `val abc`: `ValueError`, only `beall` ran. An optional
  group that took no part, `^opt(?: (?P<n>\d+))?$` on `opt`: `TypeError` from `int(None)`, only `beall` ran.
- **A callback that removes its own trigger.** With two triggers on the regex, the first one's callback called
  `trigger.remove(..., force=True)`. `process_match` then read `self.triggers[trigger_id].stopevaluating` and
  raised `KeyError`; the second trigger and `all` did not run for that line. The next line was normal.
- **A callback that removes an earlier trigger on the same regex.** With three triggers, the second one's
  callback removed the first; the third was skipped for that line, without an error, because the list being
  iterated had shifted.
- A callback that removed a later trigger did no harm: the one after it still fired.

### Q3d: A callback that raises

Isolated, as the events audit found. With a raising callback at priority 1 and a normal one on the same
trigger, the error was logged, the normal callback ran, the next trigger on the regex ran and `all` ran.

---

## Q4: What Does a Line Cost?

**Verified** (`out-q4_cost.txt`, `out-q4b_cost.txt`, `out-q8_raise.txt`). Single run; see
[How This Was Verified](#how-this-was-verified) for the environment.

**Matching alone.** `_eventcb_check_trigger` on the stub harness with N enabled triggers on generated,
`^`-anchored regexes of six shapes (damage, tells, arrivals, channels, skills, status), each with one or two
named groups. The event raise is a no-op, so the figures are the regex work and the Python around it, in
microseconds per line.

| Enabled triggers | Line matches nothing | Matches the first regex | Matches the last regex |
| ---: | ---: | ---: | ---: |
| 10 | 1.8 | 7.4 | 7.9 |
| 100 | 6.0 | 31.1 | 34.7 |
| 1,000 | 53.2 | 273.1 | 324.9 |
| 5,000 | 267.9 | 1,382.3 | 1,761.9 |

The cost grows with N in every column. A matching line costs about five times a non-matching one, and most of
that is `match_data.groupdict()`, which builds a dictionary with one entry per regex: the same `match` followed
by `match.lastgroup` took 9.7 us at 1,000 triggers for the first regex, against 273.1.

**The events around it.** On the booted system, one `ev_to_client_data_modify` raise for one line:

| Measurement | Microseconds |
| :--- | ---: |
| Whole raise, line matches no trigger | 788.4 |
| Whole raise, line matches one trigger with one callback | 951.5 |
| The same two, with the `beall` and `all` raises replaced by a no-op | 535.0 and 696.0 |
| `TriggerItem.raisetrigger` alone, no callback registered | 106.3 |
| `TriggerItem.raisetrigger` alone, one callback | 111.3 |

So the two unconditional built-in raises cost about 250 us per line with nothing registered on them, and each
match costs about 110 us to deliver as an event. At 100 triggers the matching is a few percent of the per-line
cost at most; the event raises are the cost (TR-8).

**Rebuilds.** `rebuild_regexes` compiles the whole combined pattern on every change. One rebuild, with the
`regex` module's cache emptied first: 0.9 ms at 10 triggers, 8.7 ms at 100, 89.3 ms at 1,000, 447.2 ms at 5,000.
Adding N triggers one by one, as plugins do, therefore costs N growing compiles: 0.01 s for 10, 0.48 s for 100
and **46.57 s for 1,000**, during which the event loop is blocked. The 5,000 case was not run (TR-10).

---

## Q5: What Is Untested?

**Verified** by the two coverage runs. The narrow run reports
`src/bastproxy/plugins/core/triggers/plugin/_triggers.py` at 28.77% (353 statements, 234 missed) and the full
`doit coverage` run at 30.18% (229 missed). The existing tests call two methods on stubs.

**Covered:** `TriggerItem.__init__` and `raisetrigger` (hits); `_api_trigger_register` and
`_api_trigger_unregister` for an id that exists; the main path of `_eventcb_check_trigger` and of
`process_match` (one trigger, one regex, with and without `matchcolor`, MXP modes, the lazy debug line).

**Not covered, by symbol:**

| Symbol | What no test runs |
| :--- | :--- |
| `TriggerItem.raisetrigger` | The `omit` branch |
| `_phook_init_plugin`, `_phook_initialize` | All of it: the built-ins and the setting |
| `_eventcb_enabled_modify`, `_eventcb_plugin_unloaded` | All of it |
| `rebuild_regexes`, `find_regex_id`, `create_trigger_id`, `create_regex_id` | All of it |
| `_api_trigger_register`, `_api_trigger_unregister` | The branch that builds an id from a name |
| `_api_trigger_add`, `_api_trigger_update`, `_api_trigger_remove`, `_api_trigger_get`, `_api_trigger_remove_for_owner`, `_api_trigger_toggle_enable`, `_api_trigger_toggle_omit`, `_api_group_toggle_enable` | All of it |
| `process_match` | A disabled trigger, a failed second-stage match, `argtypes`, `stopevaluating`, an unknown regex id |
| `_eventcb_check_trigger` | No event record, an internal line, an empty line, no compiled pattern |
| `_command_list`, `_command_detail`, `_eventcb_triggers_ev_plugins_stats` | All of it |

**What the gap means.** Every defect in this page is on a line no test runs. TR-3 fails on its first statement
after the lookup, for any input; one test calling `trigger.update` would have caught it. The existing tests
build their own combined pattern, so `rebuild_regexes` and the named-group strip, where TR-1 and TR-5 live,
have never run under test. This is TR-12.

---

## Where the Docs Disagreed With the Code

Corrected in [Triggers System](triggers_system.md) in this change. Where the code is wrong, the page now says
what the code does and names the defect; it does not hide the defect behind the doc. Tags: **verified** (a
probe or grep ran, output saved) or **read**.

| # | Section | Said | Code does | Fixed here or issue |
| --: | :--- | :--- | :--- | :--- |
| 1 | Overview | Triggers support "priority ordering" and "efficient regex compilation" | `priority` is not used (**verified**, Q1c); the combined pattern is recompiled on every change (**verified**, Q4) | Fixed; TR-1, TR-10 |
| 2 | TriggerItem Class | `regex` is the "Compiled regex"; `event_name = ""`; `enabled = True`; nine attributes | `regex` is a string; `event_name` is `event_<trigger_id>`; also `api`, `original_regex_compiled`, `priority`, `hits`, `trigger_id` (**read**) | Fixed |
| 3 | TriggersPlugin Class | An `__init__` with four dictionaries; `regexes` holds "Compiled regexes" | A plugin hook; also `can_reload_f`, `latest_regex_id`, the three built-in ids and `created_regex`; `regexes` holds strings, trigger lists and hits (**read**) | Fixed |
| 4 | Creating Triggers | Unanchored examples such as `r"HP: (\d+)/(\d+)"` | Matched from the start of the line (**verified**, Q1b) | Fixed (note added) |
| 5 | Creating Triggers | `priority=10  # High priority` | Stored, not used (**verified**, Q1c) | Fixed; TR-1 |
| 6 | Responding to Triggers | `success, trigger = ...trigger.add(...)` with no caveat | A failure returns a bare `False` (**verified**, Q2a) | Fixed (note added); TR-9 |
| 7 | Trigger Matching | Six steps: "checks all enabled triggers", "matches against line (with or without color)" | One regex is chosen per line; the built-ins; two stages; `matchcolor` only in the second (**verified**, Q1) | Fixed (rewritten); TR-1, TR-6 |
| 8 | Regex Optimization | Named groups "identify which trigger matched" | They identify which regex matched, and only the first; backreferences change meaning (**verified**, Q1f, Q3b) | Fixed (rewritten); TR-5 |
| 9 | Common APIs | `trigger.update`, `trigger.toggle.enable` and `group.toggle.enable` listed as working | See Q2b to Q2d (**verified**) | Fixed; TR-2 (fixed by #347), TR-3, TR-4 |
| 10 | Built-in Triggers | "automatic triggers", no mention of `enabled` | Added with `enabled=False`, raised for every line anyway; `emptyline` rules; `^$` never fires (**verified**, Q1e) | Fixed; TR-8 |
| 11 | Commands | A `#bp.triggers.listgroups` command | The plugin has `_command_list` and `_command_detail` only (**read**; the greps find no other `AddParser`) | Fixed (removed) |
| 12 | Trigger Groups | The group toggle example | Changes nothing (**verified**, Q2c) | Fixed (note added); TR-4 |
| 13 | Best Practices | "Remove triggers in uninitialize hook"; "Use priority to control matching order" | Removed on unload (**verified**, Q2e); priority not used | Fixed; TR-1 |
| 14 | Stop Evaluating | "Stop checking other triggers after this matches", `priority=1  # Check first` | Stops later triggers on the same regex only (**verified**, Q1c) | Fixed; TR-1 |
| 15 | Match with Color | "Match including color codes" | Must also match the uncoloured text (**verified**, Q1d) | Fixed; TR-6 |
| 16 | Dynamic Trigger Updates | The `trigger.update` example | Raises `TypeError` (**verified**, Q2d) | Fixed (note added); TR-3 |
| 17 | Integration Points, Trigger Properties, Performance Notes | "Triggers removed when plugin unloads"; "`priority`: Match priority (lower = earlier)"; "Disabled triggers don't impact performance" | True for triggers, not for groups or no-regex triggers (**verified**, Q2e); not used; a disabled trigger's regex stays in the pattern while another enabled trigger uses it, and the built-ins cost the same either way (**read**, Q4) | Fixed; TR-4, TR-8 |

A new section, "The `enabled` Setting", was added for TR-11.

**In another page:** [Event System](event_system.md), Network Events, listed
`ev_libs.net.mud_from_mud_event` as "Data received from mud". Nothing raises it (**verified**, Q2f). The line
now says so.

**Checked and correct** (**read**; no change): the callback examples that read `matches` from
`event.current.record.get`; the `argtypes` examples; the Gagging Lines example (`omit=True`, **verified** in
Q1a); the `list` and `detail` commands; the Regex Tips; "Multiple triggers with same pattern share compiled
regex", in the sense of sharing one alternative.

---

## Q7: Patterns and Anti-Patterns

Greps, all scoped to `src/bastproxy/plugins/core/triggers` with `--include=*.py` (`out-q7-greps.txt`):

- `grep -rnE 'except( Exception| BaseException)?:'`: 2 matches
- `grep -rnE 'Path|os\.path'`: none
- `grep -rnE '^[A-Za-z_]+ = |^global |^[A-Z_]+: '`: the five `PLUGIN_*` constants and `__all__`
- `grep -rnE 'print\('`: 3 matches; `grep -rnE 'sys\.exit'`: 1 match
- `grep -rnE 'self\.api\('`: 29 matches
- `grep -rnE 'type: ignore|noqa|pylint: disable'`: 4 matches, all `pylint: disable`
- `grep -rnE 'raise '`: none; `grep -rnE 'return False|return None'`: 9 matches

| # | Pattern | Where | Consistent? | Verdict |
| --: | :--- | :--- | :--- | :--- |
| 1 | **One combined alternation for all triggers** | `TriggersPlugin.rebuild_regexes`, `_eventcb_check_trigger` | Yes | **Change (TR-14).** It makes one `match` call per line, which is what it is for, but it is the cause of TR-1, TR-5 and TR-6 and of the rebuild cost in TR-10. Q8 compares the alternatives. |
| 2 | **Triggers delivered as raised events** (observer): one event per trigger, callbacks registered on it | `TriggerItem.raisetrigger`, `_api_trigger_register` | Yes | **Keep.** It gives callbacks priorities, isolation of a failing callback (Q3d) and the `detail` display for free, and it is the plugin-facing contract. It costs about 110 us per match (Q4); what should change is raising `beall` and `all` with no listener (TR-8). |
| 3 | **Ids built from strings**: `t_<owner>_<name>`, `reg_<n>` | `create_trigger_id`, `create_regex_id` | No | **Change (TR-4, TR-9).** `reg_<n>` is a counter and is fine. The trigger id is the cause of TR-4 (an id passed where a name is expected) and of the two-way lookup in `trigger.register`, which accepts either. Owner ids contain dots and names can contain anything, so an id cannot be split back into its parts. Key triggers by `(owner_id, name)` or pass ids and names as different parameters. |
| 4 | **The matcher registered twice**: by decorator on one event and by hand on another | `_eventcb_check_trigger`, `_eventcb_enabled_modify` | No | **Change (TR-11).** The hand registration is on an event nothing raises. |
| 5 | **`TriggerItem` as an attribute bag** with one behaviour | `TriggerItem` | No | **Change (TR-2, TR-3).** State that belongs to the item (`enabled`, group membership, the regex) is also kept in three plugin dictionaries and they drift (Q2b, Q2c). `trigger.update` treats it as a dictionary. Make it a dataclass that owns its state, with the plugin's indexes derived from it. |
| 6 | **Parallel indexes that only grow** | `regexes`, `regex_lookup_to_id`, `trigger_groups` | Yes | **Change (TR-4, TR-10).** Nothing removes an entry (Q2c, Q2e). |
| 7 | **Silent failures**: log an error and return `False` or `None`; no exception | `_api_trigger_add`, `_api_trigger_update`, `_api_trigger_remove`, `_api_trigger_toggle_enable`, `_api_trigger_toggle_omit`, `_api_group_toggle_enable`, `rebuild_regexes` | No | **Change (TR-5, TR-9).** `AGENTS.md` asks for an error with context. Three shapes are in use: `False`, `None` with a log, and nothing at all (an unknown group). `rebuild_regexes` is the costly one: the caller is told the add worked. Two APIs raise `KeyError` by accident instead (`trigger.register`, `trigger.unregister`). |
| 8 | **Catch-all `except Exception`** around `re.compile` | `_api_trigger_add`, `_api_trigger_update` | Yes | **Change (TR-9), small.** Catch `re.error`, as `rebuild_regexes` does. |
| 9 | **Import-time side effect**: `print` and `sys.exit(1)` when `regex` is missing | module top of `_triggers.py` | No other plugin file was checked | **Change (TR-9).** `regex` is a declared dependency; an `ImportError` from the import says the same thing without ending the process from inside an import. |
| 10 | **`print` for an error** | `_api_trigger_add` (no owner) | No | **Change (TR-9).** `_api_trigger_remove` logs the same condition. |
| 11 | **Service locator through string API names** | 29 `self.api(...)` calls; `TriggerItem` builds its own `API(owner_id=...)` | Yes | **Keep.** The project-wide trade covered by the plugin audit ([Plugin System Findings](plugin_system_findings.md)) and the API audit. `TriggerItem` needing an `API` object only to raise one event is tight coupling, and it is why the tests replace `item.api`; TR-14 passes the raise function in. |
| 12 | **Tight coupling to event order**: unload cleanup works because the events plugin runs first at the same priority | `_eventcb_plugin_unloaded`, `_api_trigger_remove_for_owner` | n/a | **Change (TR-8).** Pass `force=True` from `trigger.remove.for.owner`, so the cleanup does not depend on registration order. |
| 13 | **String paths instead of `Path`** | none | n/a | **Keep.** The package touches no path. |
| 14 | **Hidden global state** | none at module level; all state is on the plugin instance | Yes | **Keep.** |
| 15 | **Typing**: the package is under a mypy `ignore_errors` override (`bastproxy.plugins.core.*` in `pyproject.toml`) and has no annotations | whole file | Yes | **Keep here.** Tracked by #6. mypy would have reported TR-3. |

---

## Q8: Design Assessment

### What a trigger system has to get right

1. **Every trigger that matches a line fires**, in an order the author controls, and one trigger can stop the
   rest.
2. **A trigger's regex means what it means alone.** Adding another plugin's trigger must not change it.
3. **A bad trigger hurts only itself.**
4. **The cost per line is small** next to the rest of the line's processing, and adding or removing a trigger
   is cheap.

The current design fails 1 (TR-1), 2 (TR-5, TR-6) and 3 (TR-5, TR-7), and meets the first half of 4. Those are
not coding slips in a sound design: a top-level alternation reports one alternative, and joining regexes
changes their group numbering. Fixing them inside the combined-regex design means a second pass over all
other regexes after the first hit, which is alternative (i) with extra machinery.

### The alternatives, measured

Prototypes were scratch code outside `src`, run on the Q4 regexes and lines (`out-q4b_cost.txt`,
`out-q8_re2.txt`). Microseconds per line, matching only, in the order no match / first regex / last regex.

| Design | 100 triggers | 1,000 triggers | 5,000 triggers |
| :--- | ---: | ---: | ---: |
| Current: combined alternation, `groupdict`, second match | 6.0 / 31.1 / 34.7 | 53.2 / 273.1 / 324.9 | 267.9 / 1,382.3 / 1,761.9 |
| Combined alternation with `lastgroup` only (finds one regex, no groups) | 4.5 / 1.2 / 4.6 | 49.0 / 9.7 / 46.4 | 262.4 / 57.4 / 356.1 |
| (i) Each trigger's own compiled regex, in priority order | 22.1 / 21.0 / 18.3 | 247.7 / 201.1 / 187.5 | 1,296.7 / 1,056.4 / 1,273.6 |
| (ii) First-word prefilter, then (i) inside the bucket | 3.8 / 7.6 / 4.9 | 37.8 / 54.8 / 36.8 | 197.4 / 285.9 / 195.0 |
| (iv) `google-re2`, combined alternation with `lastgroup` | 4.4 / 56.3 / 50.3 | 43.9 / 8,296.6 / 3,184.6 | 298.3 / 234,409.0 / 114,272.2 |
| (iv) `google-re2`, each trigger's own regex | 92.5 / 98.3 / 96.9 | 933.9 / 957.7 / 939.1 | 4,641.1 / 4,886.4 / 4,504.6 |
| (iv) `google-re2` `Set` (reports which patterns match, no groups) | 0.4 / 0.5 / 0.5 | 0.5 / 0.5 / 0.5 | failed to compile with default options |

Notes on the table:

- **(i)** costs about 0.2 to 0.25 us per trigger per line, whatever the line. It is slower than the current
  design on a line that matches nothing (4 to 5 times) and faster on a line that matches.
- **(ii)** indexes a regex by its literal first word (`^You `, `^\[orc3\] `). In the generated set one regex in
  six starts with a group and cannot be indexed; those are tried on every line, and they are nearly all of the
  remaining cost (167 of 1,000). A real trigger set may have more or fewer of them; this was not measured on
  real plugins, because the repository has one trigger.
- **(iii) Direct callbacks instead of an event per match.** A direct call of the callback took 0.09 us against
  111.3 us for `raisetrigger` with one callback (Q4). The event buys callback priorities, the isolation of a
  failing callback, records, and the `detail` command's event display.
- **(iv)** `google-re2` 1.1.20251105 rejected a numeric backreference, a lookahead and a lookbehind
  (**verified**), so it cannot be the only engine. Its Python binding was slower per call than `regex` on these
  short patterns. Its `Set` was the fastest thing measured and does report every matching pattern, but it
  failed to compile 5,000 patterns with default options (a larger memory budget was not tried), and it gives no
  groups, so a second match is still needed. Linear-time matching is its documented property; this page gives no
  figure for it.

### Comparison

| | Current | (i) Per trigger, priority order | (ii) Prefilter + (i) | (iv) `google-re2` |
| :--- | :--- | :--- | :--- | :--- |
| Overlapping matches | First-added regex only (TR-1) | All fire | All fire | `Set`: all reported; combined: first only |
| Priority and stop | Not used; stop is per regex | Natural: sort by priority, break on stop | Needs a merge of bucket and unindexed lists by priority | As (i) after the `Set` |
| A regex means what it means alone | No (TR-5, TR-6) | Yes | Yes | Yes, but backreferences and lookaround are rejected |
| A bad regex | Can freeze the matcher (TR-5) | Rejected at `trigger.add`, affects nothing else | Same | Same |
| Multi-line output | No | No, but a trigger can keep state between lines; nothing is shared | Same | Same |
| Cost per line, 100 triggers | 6 to 35 us | 18 to 22 us | 4 to 8 us | 0.5 us for the `Set`, plus a second match |
| Cost of add or remove | A recompile of everything (Q4) | One compile, one sorted insert | Same, plus one index entry | A `Set` is recompiled whole |
| Worst case on hostile text | Backtracking engine: no linear bound by design | Same engine | Same engine; the prefilter narrows which regexes see a line | Linear in the length of the line, by its documentation |
| Writing and debugging | A trigger's behaviour depends on every other trigger | Each trigger can be tested alone with `re.match` | As (i); the prefilter must never drop a real match | Two regex dialects to explain |
| New dependency | No | No | No | **Yes: needs the owner's approval** |

### How established clients do it

- **TinTin++ 2.02.20** (**verified**, the installed client's `#help action`): "Actions are ordered
  alphabetically and only one action can trigger at a time. To change the order you can assign a priority,
  which defaults to 5, with a lower number indicating a higher priority." So: one action per line, chosen by
  priority, then by name. A pattern matches anywhere in the line unless it starts with `^` (`#help regex`:
  "^ force match of start of line"), and "If the message starts with a ~ color codes must be matched". Gags are
  a separate list: `#gag {string}` "Removes any line that contains the string". Substitutions are a third list
  with their own priority (`#help substitute`).
- **Mudlet** (**unverified**: from memory of its public documentation, not checked here): triggers are tried
  in tree order, every matching trigger fires, a trigger can be a chain that gates its children, and there are
  multi-line and multi-condition triggers.
- **MUSHclient** (**unverified**, same basis): triggers are tried in ascending "sequence" order; each has a
  "keep evaluating" flag, without which matching stops at the first hit; "omit from output" gags the line; a
  multi-line option matches over a set number of recent lines.

The common points are an explicit order (priority or sequence), a per-trigger decision whether to continue,
and gagging as a property or its own list. bastproxy's API already has all three as parameters (`priority`,
`stopevaluating`, `omit`); only the matcher does not implement the first two. TinTin++'s one-action rule is the
nearest to what bastproxy does today, but there the winner is chosen by priority.

### Recommendation: change parts of it

**Keep** the API, the per-trigger events and the `regex` module. **Replace the matcher** with alternative (i):

1. Keep each enabled trigger in a list sorted by `(priority, order added)`.
2. For each line, match each trigger's own compiled regex (against `colorcoded` for `matchcolor`, `noansi`
   otherwise), raise its event on a match, and stop the line when a matching trigger has `stopevaluating`.
3. Wrap each trigger's match, conversion and raise in its own `try`, and iterate over a copy of the list.
4. Raise `beall`, `all` and `emptyline` only when a callback is registered on them.

Reasons:

- It fixes TR-1, TR-5 and TR-6 by removing their cause, and makes TR-7 a local `try`. `rebuild_regexes`, the
  regex table, the named-group strip and the second-stage match all go; `enabled` is the only state that says
  whether a trigger runs (TR-2).
- The cost is acceptable. At 100 triggers it is about 20 us per line against 6 to 35 us now, inside a per-line
  cost of several hundred microseconds that step 4 lowers by about 250 us (Q4). Loading stops being quadratic
  (TR-10).
- It needs no new dependency.
- Alternative (ii) is the follow-up if a benchmark with a real trigger set shows (i) is too slow at the sizes
  people run: it is an index in front of (i), not a different design. It should not be built before the
  benchmark exists (TR-13).
- `google-re2` is not recommended now: it cannot run every regex, it adds a second dialect, and at realistic
  sizes matching is not where the time goes. Whether a linear-time engine is wanted for other reasons is part
  of the private follow-up to Q4, and would need the owner's approval as a dependency.
- Direct callbacks are not recommended: the event is the contract plugins use, and its cost is paid only on a
  match.

**Whether a regex is anchored** stays as it is (`match`): changing it to `search` would change which lines
existing regexes match. The ADR for TR-14 should record that choice.

### Migration path

All ten APIs keep their names and signatures. The only caller in the repository,
`src/bastproxy/plugins/test/triggers/plugin/_triggerex.py` (`trigger.add`, `trigger.register`), needs no
change (**verified**, `out-docs-checks.txt`: no other caller in `src`).

| API | After the change |
| :--- | :--- |
| `trigger.add` | Same arguments and return. `priority` and `stopevaluating` start to work as documented. A regex that does not compile is still refused. |
| `trigger.register`, `trigger.unregister` | Unchanged: they register on `event_<trigger_id>`. |
| `trigger.get` | Returns the item. `TriggerItem.regex_id` has no meaning any more: keep the attribute as `None` for one release, then remove it. `TriggerItem.regex` stays as an alias of `original_regex`. |
| `trigger.update` | Starts to work (TR-3): changing `regex` is one compile, changing `priority` one re-sort. |
| `trigger.remove`, `trigger.remove.for.owner` | Unchanged; the latter passes `force=True`. |
| `trigger.toggle.enable`, `trigger.toggle.omit` | Unchanged; enable sets `TriggerItem.enabled`. |
| `group.toggle.enable` | Starts to work (TR-4). |

**Behaviour that changes for existing plugins** and belongs in the commit as a `BREAKING CHANGE:` footer:

- Two triggers with different regexes that match one line both fire. A plugin that relied on an earlier
  trigger hiding a later one must set `stopevaluating` on the earlier one.
- Triggers run in `priority` order (lower first), then in the order added. All current triggers have the
  default 100, so their relative order stays.
- `stopevaluating` stops every later trigger for the line, not only those on the same regex.
- `#bp.triggers.detail` loses the "Regex (w/o Groups)" and "Regex ID" lines, and the stats lose the regex
  counts.

This is TR-14. It changes a core plugin's matching semantics, so it needs an ADR.

---

## New Defects

Each entry is open and filed as the issue it names. The issue body it was filed with is given with each, with
the fields of the matching template in `.github/ISSUE_TEMPLATE/`. Line references are to
`src/bastproxy/plugins/core/triggers/plugin/_triggers.py` at the base commit. TR-1, TR-5 and TR-6 are removed
by TR-14; they are listed separately because they are observable bugs today and can be closed against it.

### TR-1: Only the first-added matching regex fires, and `priority` is ignored

**Status:** open
**Issue:** #346
**Location:** `TriggersPlugin.rebuild_regexes`, `TriggersPlugin._eventcb_check_trigger`; `TriggerItem.priority`.
**Evidence (verified):** Q1c: of three overlapping triggers at priorities 200, 1 and 50, only the first added
fired; `stopevaluating` on a later regex had no effect.
**Fix:** TR-14.

> **Proposed issue (bug):** `bug: only the first-added trigger regex fires for a line; priority is ignored`
>
> **Bug Description:** All trigger regexes are joined into one alternation. A line that several triggers with
> different regexes match fires only the one whose regex was added first. `priority` is stored and never read.
> **Steps to Reproduce:** Add `a` with `^You slash (\w+)` at priority 200, then `b` with `^You slash .*` at
> priority 1; register a callback on each; send the MUD line `You slash goblin.`
> **Expected vs Actual Behavior:** Expected: both fire, `b` first. Actual: only `a` fires.
> **Environment:** base commit `4fda9a5`, Python 3.12.12, `regex` 2026.9.29.
> **Error Output:** none.
> **Additional Context:** Triggers System Findings, Q1c. Removed by the matcher change (TR-14).

### TR-2: `trigger.toggle.enable` does not set `TriggerItem.enabled`

**Status:** fixed by #347
**Issue:** #347
**Location:** `TriggersPlugin._api_trigger_toggle_enable`; `TriggersPlugin.process_match` (the `enabled`
check); `_command_list`, `_eventcb_triggers_ev_plugins_stats`.
**Evidence (verified):** Q2b: a trigger added with `enabled=False` and toggled on never fired; a trigger
toggled off still showed `enabled=True`.
**Fix:** set the attribute in the toggle and derive the regex list from it; one source of truth.

> **Proposed issue (bug):** `bug: trigger.toggle.enable cannot enable a trigger added with enabled=False`
>
> **Bug Description:** The toggle edits the regex's trigger list but not `TriggerItem.enabled`, which
> `process_match` checks and `list` and the stats display.
> **Steps to Reproduce:** `trigger.add("t", r"^starts off$", enabled=False)`, register a callback,
> `trigger.toggle.enable("t", True)`, send `starts off`.
> **Expected vs Actual Behavior:** Expected: the callback runs and `list` shows the trigger enabled. Actual:
> it never runs; `enabled` stays False. In the other direction a disabled trigger is listed as enabled.
> **Environment:** as TR-1. **Error Output:** none.
> **Additional Context:** Triggers System Findings, Q2b.

### TR-3: `trigger.update` raises `TypeError` on every call

**Status:** fixed by #348
**Issue:** #348
**Location:** `TriggersPlugin._api_trigger_update`.
**Evidence (verified):** Q2d: `TypeError: 'TriggerItem' object is not subscriptable` for `{"omit": True}` and
for a new regex. **Read:** the group branch uses a name as an id; the regex branch does not update `regex` or
`regex_id` and sets the attribute before compiling.
**Fix:** `getattr`; validate the keys; compile before changing anything; move the trigger between regex and
group entries by id. Tests for each key.

> **Proposed issue (bug):** `bug: trigger.update raises TypeError for any existing trigger`
>
> **Bug Description:** `_api_trigger_update` reads `self.triggers[trigger_id][key]`; `TriggerItem` is not
> subscriptable. The code after that line has further errors (group handling by name, `regex` and `regex_id`
> not updated).
> **Steps to Reproduce:** from a plugin, `trigger.add("t", r"^x$")` then `trigger.update("t", {"omit": True})`.
> **Expected vs Actual Behavior:** Expected: the trigger's `omit` is True. Actual: `TypeError`.
> **Environment:** as TR-1.
> **Error Output:** `TypeError: 'TriggerItem' object is not subscriptable` at `_api_trigger_update`.
> **Additional Context:** Triggers System Findings, Q2d. No test calls this API.

### TR-4: `group.toggle.enable` changes nothing, and group entries are never removed

**Status:** open
**Issue:** #349
**Location:** `TriggersPlugin._api_group_toggle_enable`; `trigger_groups` in `_api_trigger_add` (the only
writer) and `_api_trigger_remove` (no cleanup).
**Evidence (verified):** Q2c: two "does not exist" errors and both triggers still firing; the same id three
times in a group after unload, load and reload.
**Fix:** toggle by id; remove the id from its group in `trigger.remove`; do not append an id twice.

> **Proposed issue (bug):** `bug: group.toggle.enable toggles nothing and trigger groups keep removed triggers`
>
> **Bug Description:** The group holds trigger ids; the toggle passes them on as names, so each lookup builds
> a doubled id and fails. `trigger.remove` leaves the id in the group, so groups keep stale and repeated ids
> across unload and reload.
> **Steps to Reproduce:** add two triggers with `group="g"`, call `group.toggle.enable("g", False)`, send
> their lines; then unload and load the plugin and inspect `trigger_groups["g"]`.
> **Expected vs Actual Behavior:** Expected: neither fires; the group has each id once. Actual: both fire and
> two errors are logged; ids pile up.
> **Environment:** as TR-1.
> **Error Output:** `toggletrigger - trigger t_<owner>_<name> (maybe <owner>) does not exist`, once per member.
> **Additional Context:** Triggers System Findings, Q2c.

### TR-5: A regex that is valid alone can break or change the combined pattern

**Status:** open
**Issue:** #350
**Location:** `TriggersPlugin.rebuild_regexes` (keeps the previous compiled pattern on `re.error`);
the strip `re.sub(r"\?P\<.*?\>", "", ...)` in `_api_trigger_add` and `_api_trigger_update`.
**Evidence (verified):** Q3b: after adding a named-backreference trigger, `trigger.add` returned success for
it and for a later trigger, and neither ever fired; a removed trigger stayed in the stale matcher. Q1f: a
numeric backreference never matched. Q3b: a literal `\?P<b>` was cut from the pattern.
**Fix:** TR-14 removes the combination. Without it: compile the candidate combined pattern before accepting a
trigger and refuse the add on failure; refuse backreferences; strip names with a parser, not a `sub`.

> **Proposed issue (bug):** `bug: one trigger regex can stop all later triggers from firing`
>
> **Bug Description:** Named groups are made unnamed with a text substitution and all regexes are joined. A
> named backreference then refers to a missing group and the combined pattern does not compile;
> `rebuild_regexes` logs it and keeps the old pattern, while `trigger.add` reports success. Every trigger added
> afterwards, by any plugin, is dead until the offending one is removed. Numeric backreferences point at the
> wrong group, and a literal `\?P<x>` is removed from the pattern.
> **Steps to Reproduce:** add `^(?P<w>\w+) says (?P=w)$`, then add `^after (?P<y>\w+)$` with a callback; send
> `after a`.
> **Expected vs Actual Behavior:** Expected: the second trigger fires, or the first add is refused. Actual:
> both adds return `(True, item)`; neither trigger ever fires.
> **Environment:** as TR-1.
> **Error Output:** `Could not compile created regex` with `unknown group at position ...`, logged on every
> later add and remove.
> **Additional Context:** Triggers System Findings, Q1f and Q3b.

### TR-6: A `matchcolor` trigger must also match the uncoloured text

**Status:** open
**Issue:** #351
**Location:** `TriggersPlugin._eventcb_check_trigger` (first stage on `noansi`); `TriggersPlugin.process_match`
(second stage on `colorcoded`).
**Evidence (verified):** Q1d: `^@RWARNING` and `^ALERT` never fired on coloured lines; a later plain trigger
was shadowed.
**Fix:** TR-14 (one match per trigger, on the text its flag names).

> **Proposed issue (bug):** `bug: matchcolor triggers with a colour code in the regex never fire`
>
> **Bug Description:** The first-stage match is always on the text without colour codes; `matchcolor` only
> selects the text for the second stage. A regex written for the colour-coded text fails the first stage; a
> regex written for the plain text can fail the second, and then hides later triggers on the line.
> **Steps to Reproduce:** add `^@RWARNING` with `matchcolor=True`; send a line whose first word is a bold red
> `WARNING`.
> **Expected vs Actual Behavior:** Expected: it fires. Actual: it never does.
> **Environment:** as TR-1. **Error Output:** none.
> **Additional Context:** Triggers System Findings, Q1d.

### TR-7: An exception while a line's triggers run drops the rest of that line's triggers

**Status:** open
**Issue:** #352
**Location:** `TriggersPlugin.process_match` (the `argtypes` conversion; the iteration over the live
`regex["triggers"]` list; `self.triggers[trigger_id].stopevaluating` after the raise).
**Evidence (verified):** Q3c: `ValueError` and `TypeError` from `argtypes`, and `KeyError` after a callback
removed its own trigger, each ended the line's processing with only `beall` raised; removing an earlier
sibling skipped the next trigger without an error.
**Fix:** iterate over a copy; read the trigger once per iteration; wrap one trigger's conversion and raise in a
`try` that logs the trigger and the line and continues; skip the conversion of a group that is `None`.

> **Proposed issue (bug):** `bug: an argtypes conversion error or a self-removing callback skips the rest of the line's triggers`
>
> **Bug Description:** `process_match` has no error handling and iterates a list that callbacks can change. A
> conversion that raises, or a callback that removes its trigger, raises out of `_eventcb_check_trigger`: the
> remaining triggers and the `all` trigger do not run for that line.
> **Steps to Reproduce:** add `^val (?P<n>\w+)` with `argtypes={"n": int}` and a second trigger on the same
> regex; send `val abc`. Or: two triggers on one regex, the first one's callback calling
> `trigger.remove(name, force=True)` on itself.
> **Expected vs Actual Behavior:** Expected: the failing trigger is logged and the others run. Actual: nothing
> after it runs for that line.
> **Environment:** as TR-1.
> **Error Output:** `raise_event - event ev_to_client_data_modify with function _eventcb_check_trigger raised
> an exception` with `ValueError`, `TypeError` or `KeyError`.
> **Additional Context:** Triggers System Findings, Q3c.

### TR-8: Triggers without a regex: `KeyError` from remove and toggle, and the built-ins are raised for every line

**Status:** open
**Issue:** #353
**Location:** `TriggersPlugin._api_trigger_remove`, `TriggersPlugin._api_trigger_toggle_enable`
(`self.regexes[...regex_id]` with `regex_id` None); `TriggersPlugin._api_trigger_remove_for_owner` (no `force`,
no `try`); `TriggersPlugin._phook_initialize` and `_eventcb_check_trigger` (the built-ins).
**Evidence (verified):** Q2e: `KeyError: None` from both APIs and from toggling `all`; an unload that left the
owner's triggers behind and a reload whose adds all failed. Q1e: the built-ins fire with `enabled=False`. Q4:
about 250 us per line for `beall` and `all` with no listener. The shared event record is #230.
**Fix:** guard `regex_id is None`; pass `force=True` and continue past a failing removal in
`trigger.remove.for.owner`; raise a built-in only when its event has a callback; decide what `enabled` means
for a built-in and make `list` show it.

> **Proposed issue (bug):** `bug: triggers without a regex cannot be removed or toggled, and the built-in triggers are raised for every line with no listener`
>
> **Bug Description:** `trigger.remove` and `trigger.toggle.enable` index `regexes` with the trigger's
> `regex_id`, which is `None` for a trigger added without a regex. On plugin unload the `KeyError` stops
> `trigger.remove.for.owner`, so the owner's other triggers can stay and a reload then fails to add them. The
> three built-in triggers are such triggers; they are added disabled but raised for every MUD line, two events
> per line even when nothing is registered on them.
> **Steps to Reproduce:** from a plugin, `trigger.add("n", None)` then `trigger.remove("n")`; or unload a
> plugin that has such a trigger and reload it.
> **Expected vs Actual Behavior:** Expected: the trigger is removed; unload removes all of the owner's
> triggers; a built-in with no listener costs nothing. Actual: `KeyError: None`; leftovers; about 250 us per
> line.
> **Environment:** as TR-1.
> **Error Output:** `KeyError: None` at `_api_trigger_remove` or `_api_trigger_toggle_enable`.
> **Additional Context:** Triggers System Findings, Q1e, Q2e and Q4. Related: #230.

### TR-9: The trigger APIs report errors in four different ways

**Status:** open
**Issue:** #354
**Location:** `TriggersPlugin._api_trigger_add` (returns `False` or a tuple; `print` when no owner; dead
`args["event_name"]`; `except Exception`); `_api_trigger_register`, `_api_trigger_unregister` (`KeyError`);
`_api_trigger_update`, `_api_trigger_toggle_enable`, `_api_trigger_toggle_omit`, `_api_group_toggle_enable`
(log and `None`, or nothing); `TriggerItem.__init__` (ignores `event_name`); the module's import fallback
(`print` and `sys.exit(1)`).
**Evidence (verified):** Q2a, Q2e; `out-q7-greps.txt`. **Read:** the import fallback and the `print`.
**Fix:** one contract: return a value of one shape or raise a named exception; log instead of `print`; remove
the `event_name` parameter; catch `re.error`; let a missing `regex` raise `ImportError`.

> **Proposed issue (refactor):** `refactor: give the trigger APIs one error contract`
>
> **Current Code Issue:** `trigger.add` returns `(True, item)` or a bare `False`, so `success, trigger = ...`
> raises `TypeError` on failure. `trigger.register` and `trigger.unregister` raise `KeyError` for an unknown
> trigger. The toggles log and return `None`; an unknown group is silent. `trigger.add` prints when it finds no
> owner, computes an `event_name` that `TriggerItem` ignores, and catches `Exception` around `re.compile`. The
> module calls `sys.exit(1)` at import when `regex` is missing.
> **Proposed Improvement:** Decide one contract and apply it to all ten APIs: a consistent return shape for
> `trigger.add`, a named exception or a logged `False` for "no such trigger", no `print`, no dead parameter,
> `except re.error`, and a plain `ImportError`.
> **Success Criteria:** each API has a test for its failure path; no `print(` or `sys.exit` in the package;
> `_triggerex.py` handles a failed add without `TypeError`.
> **Additional Context:** Triggers System Findings, Q2a, Q2e and Q7 rows 7 to 10.

### TR-10: The combined pattern is recompiled on every change, and the regex table only grows

**Status:** open
**Issue:** #355
**Location:** `TriggersPlugin.rebuild_regexes` and its callers `_api_trigger_add`, `_api_trigger_remove`,
`_api_trigger_toggle_enable`, `_api_trigger_update`; `TriggersPlugin.find_regex_id`.
**Evidence (verified):** Q4: one rebuild takes 89.3 ms at 1,000 triggers; adding 1,000 triggers one by one took
46.57 s. Q2a, Q2e: `regexes` and `regex_lookup_to_id` keep entries for removed triggers and for regexes that
failed to compile.
**Fix:** TR-14 removes the rebuild. Without it: mark the pattern dirty and rebuild on the next line; remove a
regex entry when its last trigger goes; create the entry only after the compile succeeds.

> **Proposed issue (bug):** `bug: adding triggers recompiles the whole combined regex each time, blocking the event loop`
>
> **Bug Description:** Every add, remove or toggle compiles the alternation of all regexes. Adding N triggers
> is N compiles of a growing pattern. The regex table is never pruned.
> **Steps to Reproduce:** add 1,000 triggers with distinct regexes one after another and time it.
> **Expected vs Actual Behavior:** Expected: time roughly linear in N. Actual: 0.48 s for 100, 46.57 s for
> 1,000 (single run), on the event loop.
> **Environment:** as TR-1; 12th Gen Intel Core i7-12650H.
> **Error Output:** none.
> **Additional Context:** Triggers System Findings, Q4 (Rebuilds), Q2a and Q2e.

### TR-11: The `enabled` setting has no effect

**Status:** open
**Issue:** #356
**Location:** `TriggersPlugin._eventcb_enabled_modify`; the decorator on `_eventcb_check_trigger`.
**Evidence (verified):** Q2f: a trigger fired with the setting False; `ev_libs.net.mud_from_mud_event` has one
registration and was raised 0 times; nothing in `src` or `tests` raises it.
**Fix:** check the setting at the top of `_eventcb_check_trigger`, or register and unregister on
`ev_to_client_data_modify`; remove the dead event name.

> **Proposed issue (bug):** `bug: the triggers plugin's enabled setting does not stop matching`
>
> **Bug Description:** Changing `enabled` registers or unregisters the matcher on
> `ev_libs.net.mud_from_mud_event`, which nothing raises. The matcher's real registration, on
> `ev_to_client_data_modify`, is never touched.
> **Steps to Reproduce:** add a trigger with a callback; set `plugins.core.triggers` `enabled` to False; send
> a matching line.
> **Expected vs Actual Behavior:** Expected: no trigger fires. Actual: it fires.
> **Environment:** as TR-1. **Error Output:** none.
> **Additional Context:** Triggers System Findings, Q2f.

### TR-12: The trigger APIs and the regex bookkeeping have no tests

**Status:** open
**Issue:** #357
**Location:** the symbols in the Q5 table.
**Evidence (verified):** Q5: both coverage runs miss them.
**Fix:** tests through the real methods for add, remove, update, get, the toggles, groups,
`remove.for.owner`, `rebuild_regexes`, the built-ins, `argtypes`, `stopevaluating`, the commands and the stats
event; the fixes for TR-1 to TR-11 bring their own regression tests.

> **Proposed issue (chore):** `chore: test the trigger APIs and the matching paths that have no test`
>
> **Chore Type:** Other (tests)
> **Description:** `src/bastproxy/plugins/core/triggers/plugin/_triggers.py` is about 30% covered. Only
> `trigger.register`, `trigger.unregister` and the single-trigger matching path have tests.
> **Proposed Changes:** add tests for every API method, `rebuild_regexes`, `find_regex_id`, the built-in
> triggers, `argtypes`, `stopevaluating`, `omit`, `_command_list`, `_command_detail` and the stats event.
> **Success Criteria:** each symbol in the findings page's Q5 table has a test; the tests use the real
> `TriggersPlugin` methods, not a hand-built combined pattern.
> **Additional Context:** Triggers System Findings, Q5. Best done together with, or after, TR-14, so that the
> tests describe the matcher that stays.

### TR-13: There is no trigger benchmark

**Status:** open
**Issue:** #358
**Location:** `tests/benchmarks/` (no trigger file).
**Evidence (read):** the directory has benchmarks for the API, events, records, logging and
`NetworkDataLine`, and none for triggers. The Q4 and Q8 figures come from scratch scripts.
**Fix:** a benchmark of the per-line matching cost at several trigger counts and of adding N triggers.

> **Proposed issue (chore):** `chore: add a trigger matching benchmark`
>
> **Chore Type:** Other (benchmark)
> **Description:** The audit measured the per-line cost and the cost of adding triggers with throwaway
> scripts. A permanent benchmark is needed before the matcher is changed and to decide whether a prefilter is
> worth building.
> **Proposed Changes:** a `test_bench_trigger_match.py` next to the existing benchmarks: `_eventcb_check_trigger`
> per line at 10, 100 and 1,000 triggers for a line that matches nothing and one that matches, and the time to
> add 100 triggers.
> **Success Criteria:** `doit benchmark` runs it; the figures in the findings page can be reproduced from it.
> **Additional Context:** Triggers System Findings, Q4 and Q8.

### TR-14: Replace the combined-regex matcher with per-trigger matching in priority order (needs an ADR)

**Status:** open
**Issue:** #359
**Location:** `TriggersPlugin.rebuild_regexes`, `find_regex_id`, `_eventcb_check_trigger`, `process_match`;
`TriggerItem`.
**Evidence (verified):** Q8: the comparison table and the measurements; TR-1, TR-5, TR-6 and TR-10 follow from
the combination.
**Fix:** the recommendation and migration path in Q8.

> **Proposed issue (refactor, needs an ADR):** `refactor: match each trigger's own regex in priority order instead of one combined regex`
>
> **Current Code Issue:** All regexes are joined into one alternation. It reports one regex per line, in the
> order added (TR-1); it changes the meaning of backreferences and can fail to compile, freezing the matcher
> (TR-5); it forces a second match and breaks `matchcolor` (TR-6); and it is recompiled on every change
> (TR-10). `priority` and cross-regex `stopevaluating` cannot be implemented on it without a second pass.
> **Proposed Improvement:** Keep the enabled triggers sorted by `(priority, order added)`. For each line match
> each trigger's own compiled regex on the text its `matchcolor` flag names, raise its event, stop on
> `stopevaluating`. Isolate each trigger in a `try` and iterate over a copy. Raise the built-ins only when they
> have a callback. Remove the regex table, the named-group strip and `rebuild_regexes`. Keep all ten APIs and
> their signatures. Record in an ADR: the per-trigger design, that regexes stay anchored at the start of the
> line, the semantics of `priority` and `stopevaluating`, and that no new dependency is taken.
> **Success Criteria:** two overlapping triggers both fire, in priority order; `stopevaluating` stops later
> triggers for the line; a regex with a backreference works; adding 1,000 triggers takes time linear in the
> count; the per-line cost at 100 triggers stays within the benchmark's budget (TR-13); the ten APIs keep
> working for `_triggerex.py` unchanged; the commit carries a `BREAKING CHANGE:` footer for the behaviour
> listed under the migration path; the ADR is linked from the triggers page.
> **Additional Context:** Triggers System Findings, Q8. Closes TR-1, TR-5 and TR-6 and the rebuild half of
> TR-10. Measured: about 20 us per line at 100 triggers and 190 to 250 us at 1,000 for the per-trigger design,
> against 6 to 35 us and 53 to 325 us now. A first-word prefilter is a later option, not part of this issue.

---

## Other Observations

- **The file header names the wrong path** (`# Filename: plugins/core/triggers/_triggers.py`; the package
  `__init__` files say `_init_.py`). Cosmetic.
- **`regexes[id]["hits"]` counts first-stage matches**, including lines where no trigger passed the second
  stage, so "Total Regex Hits" in the stats can exceed "Overall Trigger Hits" for reasons other than shared
  regexes (**read**).
- **The stats' memory figures** use `sys.getsizeof` on the two dictionaries, which measures the dictionary
  tables and not the triggers in them (**read**).
- **`_command_detail` takes a trigger id**, not a name, and `_command_list`'s `match` argument filters on the
  id or on an exact owner id (**read**).
- **The docstring of `_api_trigger_add`** says "this function returns no values"; it returns a tuple or
  `False`. The comments on `trigger_groups` ("a list of trigger_names") and `rebuild_regexes` ("Rebuild a regex
  for priority") do not describe the code (**read**).
- **The shipped example plugin** `src/bastproxy/plugins/test/triggers/plugin/_triggerex.py` unpacks the result
  of `trigger.add` and so raises `TypeError` in `initialize` if the add fails, for example on a second
  initialize after an unload that left the trigger behind (**read**; TR-8, TR-9).
