---
title: Command System Analysis and Findings
description: Audit of the commands plugin - how a client line becomes a command, state consistency across add, reload and unload, failure handling, test coverage, docs accuracy and patterns, with defects and a patterns review
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - commands
  - review
---

# Command System Analysis and Findings

**Date:** 2026-11-12
**Analyzer:** Claude Sonnet 5.5
**Scope:** The commands plugin in `src/bastproxy/plugins/core/commands/`
(`src/bastproxy/plugins/core/commands/plugin/_commands.py`: `CommandsPlugin`;
`src/bastproxy/plugins/core/commands/libs/_command.py`: `CommandClass`;
`src/bastproxy/plugins/core/commands/libs/_utils.py`: the decorators), `src/bastproxy/libs/argp.py`, and the path
that turns client input into a command (`ProcessDataToMud._exec_`, then `ev_to_mud_data_modify`, then
`CommandsPlugin._eventcb_check_for_command`): line to command, state consistency, failures, test coverage, docs
accuracy and patterns (audit issue #108). Compared against [Command System](command_system.md). Base commit
`5a870c5`.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [Status of the Known Items](#status-of-the-known-items)
4. [Q1: How Does a Client Line Become a Command?](#q1-how-does-a-client-line-become-a-command)
5. [Q2: Is the Command State Kept Consistent?](#q2-is-the-command-state-kept-consistent)
6. [Q3: What Happens on a Failure?](#q3-what-happens-on-a-failure)
7. [Q4: What Is Untested?](#q4-what-is-untested)
8. [Q5: Where the Docs Disagreed With the Code](#q5-where-the-docs-disagreed-with-the-code)
9. [Q6: Patterns and Anti-Patterns](#q6-patterns-and-anti-patterns)
10. [New Defects](#new-defects)
11. [Other Observations](#other-observations)

---

## Executive Summary

The commands plugin works for the case the repository uses: a plugin defines `_command_*` methods, the
plugin loads, the client types `#bp.<package>.<plugin>.<command>`, and the command runs and frames its output.
The five items the issue listed as known are all fixed and hold (19 tests pass, and each was re-run against
the real plugin system). Outside that case, several options and checks do not do what their names and the docs
say. Fourteen items are proposed below (CM-1 to CM-14); thirteen are defects found by running the code.

- **Three command options were stored and never read** (CM-1, CM-2, both now fixed). At the audit,
  `show_in_history=False` was ignored, so every found command was recorded in the history, including `list`,
  `history` and `!`, which ask not to be (fixed in #388). `format` and `preamble` were ignored too; they are
  now honoured when a client types the command (fixed in #389).
- **One bad name, description or argument-help string stops a plugin's commands from registering**
  (CM-4). The placeholder `.format(**plugin.__dict__)` calls in `_api_command_add_by_func` are outside any
  `try`. A `KeyError` there ends the loop over the plugin's remaining commands, and when the commands plugin
  itself reloads it ends the loop over the remaining plugins. The plugin still loads; the only trace is an
  ERROR line in the log.
- **A plugin that has no command data makes the lookups raise** (CM-5, fixed in #392; CM-6 is still open).
  `command.data.get`, `command.list.formatted`, `command.help.format`, `command.run` and
  `#bp.core.commands.list <plugin>` indexed `command_data[plugin_id]` directly; they now use
  `.get(plugin_id, {})`. `command.list.formatted` still indexes the `Base` group. Before the fix, for a
  client typing a command, the exception happened inside the event, which contained it: the line was dropped
  and nothing was shown.
- **The history has an off-by-one** (CM-8). It keeps `historysize - 1` entries, and `!` indexes the list
  differently depending on whether it is full.
- **A failure outside `CommandClass.run`'s `try` is silent for the client** (CM-10). Exceptions in
  `find_command` and `format_return_message` are caught by the event system and logged, but the client sees
  nothing and the line is gone.
- **Registration appends duplicates** (CM-7): `commands_list` holds 151 entries against 133 commands after a
  re-add.
- **Tests** (Q4): `_commands.py` is 28.08% covered by the full suite. `find_command*`, the history
  code, the decorators, `command.add.by.func`, `command.data.get` and `command.list.formatted` have no test
  that names them.
- **Typo safety is good** (Q1): 330 mistyped command names were tried against the real command table; none
  resolved to a different command.
- **Docs**: the code disagreed with [Command System](command_system.md) in 23 places; the page is corrected
  for all of them.

**Key Findings:**

- 14 issues: 13 defects (CM-1 to CM-13, #388 to #400) and a test gap (CM-14, #401). Each entry under
  [New Defects](#new-defects) links its issue and carries the body it was filed with.
- The re-entrancy guard on `current_input_event` is almost never the thing that acts (Q2f), and the `else`
  branch in `_api_command_add_by_func` that looked dead is live (Q2a).

---

## How This Was Verified

Claims below are tagged **verified** (run against the code, output saved), **read** (from reading the code,
not executed) or **unverified**.

Verification used throwaway scripts, deleted afterwards and not part of the repository. Python ran with
`BASTPROXY_HOME` set to the checkout. Environment: Python 3.12.12, Linux 7.0.14-28-pve. Every timing is from a
single run and varies with load.

- **Real boot** (Q1, Q2, Q3): scripts that boot the real plugin system in-process
  (`PluginLoader().load_plugins_on_startup()`, then `startup` set to False as `bastproxy` does) and send lines
  through `ProcessDataToMud` with a `NetworkDataLine` whose `originated` is the client, exactly as
  `Client.client_read` does, so separator splitting, the event, the history and the reply all run. The reply
  was captured by replacing `SendDataDirectlyToClient` in the commands module with a recorder that keeps the
  `clients` argument and the lines (`out-q1_flow.txt`, `out-q1b_fuzzy.txt`, `out-q1c.txt`, `out-q2.txt`,
  `out-q2a.txt`, `out-q2b.txt`, `out-q2bbad.txt`, `out-q2c.txt`, `out-q2d.txt`, `out-q3.txt`, `out-q3b.txt`,
  `out-q3c.txt`, `out-q3d.txt`, `out-q5.txt`). ERROR lines the event system logs for a failing callback are
  not visible on the root logger, so they were read from the saved log output (`err-q2.txt`, `err-q3.txt`,
  `err-q3d.txt`).
- **Throwaway plugins** (Q2, Q3): two user plugins written under `$BASTPROXY_HOME/plugins` (they load as
  `plugins.audit108.reent` and `plugins.audit108.badfmt`) and deleted afterwards. The first holds one command
  for each outcome (raises, returns `False`, returns `None`, returns a string, a bare `True`, uses only
  `AddParser`, is decorated but badly named, has `autoadd=False`, sends a nested line). The second holds a
  command whose name has a placeholder the plugin does not have. The bundled `plugins.test.exception` and
  `plugins.test.cmddec` were loaded too.
- **Failure injection** (Q3): `find_command` and `CommandClass.format_return_message` were replaced with
  functions that raise, then put back.
- **Coverage** (Q4): `uv run doit coverage` (`coverage.txt`: 5,606 passed, 13 skipped) and
  `uv run pytest tests/plugins/test_commands_plugin_unload.py tests/plugins/test_commands_plugin_stats.py
  tests/plugins/test_commands_plugin_whitespace.py tests/plugins/test_commands_actor.py
  tests/libs/test_argp.py --cov=bastproxy.plugins.core.commands --cov=bastproxy.libs.argp --cov-branch
  --cov-report=term-missing -q` (`coverage-narrow.txt`: 41 passed). The known-item tests:
  `uv run pytest tests/plugins/test_commands_plugin_unload.py tests/plugins/test_commands_plugin_stats.py
  tests/plugins/test_commands_plugin_whitespace.py` (`out-known-tests.txt`: 19 passed).
- **Greps** (Q4, Q6): scoped to `src/bastproxy/plugins/core/commands` (`out-q6-greps.txt`), to `src` and `tests`
  for the dead-state names (`out-q6-dead.txt`) and to `tests` for the symbols in Q4 (`out-q4-tests.txt`). A
  test "mentioning" a symbol is a text match, not proof that the test exercises it. The grep for #89 is
  `out-known-89.txt`.

---

## Status of the Known Items

| Item from the issue | Status | Where |
| :--- | :--- | :--- |
| #96: removed commands stayed after a reload | **Fixed, and holds** (**verified**, Q2b): unloading a plugin removed its `command_data` entry and every `commands_list` entry; loading it again restored its count. `tests/plugins/test_commands_plugin_unload.py` passes. It is `_api_command_remove_for_plugin` plus `_save_command_data`, PR #115. | #96 |
| #89: internal `plugins.core.commands:run` calls | **Fixed, and holds** (**verified**): `grep -rnE 'core\.commands:run' src` has no match (exit 1, `out-known-89.txt`). The API is `command.run`, which exists (`out-q5.txt`). PR #156. | #89 |
| #92: command counts, stats and a detail view | **Fixed, and holds** (**verified**): `count`, `count_since_reload` and `CommandStats` update as described, `#bp.core.commands.detail` prints them, and counts survive a plugin reload (Q2b). An exception counted one error with `"RuntimeError: boom@Rred"` and a `False` return counted none (`out-q3.txt`). `tests/plugins/test_commands_plugin_stats.py` passes. Exception: counts are lost when the commands plugin is reloaded through the loader API without the reload flag the `reload` command sets (Q2g), which is expected. PR #155. | #92 |
| #52: leading whitespace on a command | **Fixed, and holds** (**verified**): `  #bp.core.commands.list` ran as a proxy command and was not sent to the MUD (`out-q1_flow.txt`). It is `.lstrip()` in `_eventcb_check_for_command` and `run_internal_command_from_event`. `tests/plugins/test_commands_plugin_whitespace.py` passes. PR #76. | #52 |
| #98: the `_command_*` naming rule | **Still enforced in two places, and still silent** (**verified**, Q2a): `get_command_functions_in_object` filters on the prefix and `_api_command_add_by_func` re-checks it. A decorated method called `wrongname` was skipped at load with no log line; the "Function is not a command" warning appears only when `command.add.by.func` is called with it directly. | CM-9 |

The issue also mentions `tests/plugins/core/commands/`. That directory does not exist; the command tests are
flat files under `tests/plugins/`.

---

## Q1: How Does a Client Line Become a Command?

### Q1a: The path

**Verified** by `out-q1_flow.txt` unless marked.

1. `Client.client_read` makes a `NetworkDataLine` from the input with the client as its origin and runs
   `ProcessDataToMud` (**read**, `src/bastproxy/libs/net/client.py`).
2. `ProcessDataToMud._exec_` first calls `seperate_commands`, which splits each client line on
   `api.command_split_regex` (the `cmdseperator` setting of the proxy plugin, `|` by default). It then raises
   `ev_to_mud_data_modify` once per line, with the lines as `data_list`, `key_name="line"` and
   `event_args={"showinhistory": ..., "client_id": ...}` (**read**,
   `src/bastproxy/libs/records/rtypes/muddata.py`).
3. `CommandsPlugin._eventcb_check_for_command` is the callback, registered by `@RegisterToEvent`. It tests
   `line.line.lstrip().startswith(cmdprefix)`. If true it calls `run_internal_command_from_event`; if not,
   `pass_through_command_from_event`.
4. `run_internal_command_from_event` sets `line.send = False` before anything else, calls `find_command` on
   the left-stripped text, sends any help or error page to the client, sets `event_record["showinhistory"]`
   from `find_command`'s third value, and runs the command with the command's own `format` option.
5. The caller adds the line to the history if `showinhistory` is true and the line is not internal, and
   `SendDataDirectlyToMud` sends the lines whose `send` is still true.

### Q1b: The separator splits arguments

The split in step 2 happens before command detection. `#bp.core.commands.detail core.commands.list|look` became
two lines: the `detail` command, then `look`, which went to the MUD. So a command argument can never contain a
single `|` (or whatever the separator is). **Verified.** A doubled separator is not split by the regex
(**read**: `(?<=[^|])\|(?=[^|])`).

### Q1c: The prefix test

Every line that begins with the prefix text is a proxy line, and none of them reaches the MUD, whether or not
it names a command: `#bpfoo` produced an error page and its `send` was False. **Verified.** The four literal
strings `#bp`, `#bp.`, `#bp.plugins` and `#bp.plugins.` print the package list (**verified**; **read** for
the `find_command` check that does it). Longer partial paths print a page for the part that failed: `#bp.core`, `#bp.core.commands` and
`#bp.nope.x.list` each printed a page of a different length (**verified**). By the code the pages list the
plugins of the package, the commands of the plugin and the packages (**read**).

A `cmdprefix` containing a dot never matches: with the prefix set to `#b.p`, `#b.p.core.commands.list` printed
the package error page, because `find_command_split_command_string` splits the line on `.` and looks for an
element equal to the prefix (**verified**; CM-12). The same function deletes the first element equal to the
prefix wherever it is, not only the first element (**read**); with `#bpx.#bp.core.commands.list` the first
element is `#bpx`, so the result was the error page for package `#bpx` (**verified**).

### Q1d: Plugin, package and command matching

- **Package and plugin** use `libs.plugins.loader:plugin.id.match`, which fuzzy-matches the package with
  `token_set_ratio` and `score_cutoff=90` and the plugin among the loaded plugins. `#bp.c.comm.list`,
  `#bp.co.comm.list`, `#bp.core.com.list` and `#bp.cor.pluginm.list` all resolved; `#bp.core.c.list` and
  `#bp.core.p.list` did not (ambiguous) (**verified**, `out-q1b_fuzzy.txt`).
- **Command** uses `plugins.core.fuzzy:string.match.best`: an exact match; else a unique `startswith` match;
  else the best `token_set_ratio` if it is above 80 and unique (**read**,
  `src/bastproxy/plugins/core/fuzzy/plugin/_fuzzy.py`). `l` and `lis` ran `list`, `hist` and `histor` ran
  `history`, `d` ran `detail`, `h` found nothing (it starts both `help` and `history`) (**verified**).
- **Does a near-miss run a different command?** No, in the run that was tried. For every command of the 17
  loaded plugins with a name of three characters or more, three mistyped forms were looked up (last character
  dropped, last character replaced by `x`, second character dropped): 330 lookups, 220 resolved to the
  command that was meant, 110 found nothing, and 0 resolved to another command (**verified**,
  `out-q1b_fuzzy.txt`). This is a sample, not a proof.
- **An empty command part** (`#bp.core.commands`) prints the plugin's command list. If the plugin has exactly
  one command, the empty string is a unique `startswith` match and that command runs: `#bp.audit108.badfmt`,
  a plugin left with one command by CM-4, ran it (**verified**, `out-q3d.txt`). Every plugin in a normal boot
  has at least four commands, so this is not reachable there (**verified**, `out-q1b_fuzzy.txt`).

### Q1e: Arguments

`CommandClass.parse_args` uses `shlex.split`, then `parse_known_args`. **Verified**, `out-q1_flow.txt`:

- **Unknown arguments are dropped without a message.** `list -x`, `list --nope=1` and `list a b c d` ran as if
  the extra words were not there, and `history -c extra` cleared the history (CM-11).
- **Abbreviated options are accepted** (`allow_abbrev` is argparse's default): `history --c` cleared the
  history, and `list --he` printed the help. `-h` and `--help` are an added `store_true` flag, handled in
  `CommandClass.run`, so `-h` prints the help without counting as a call.
- **Errors do not exit.** `argp.ArgumentParser.error` raises `ArgumentError`; a bad `int` (`! abc`), a missing
  value (`--num`) and an unclosed quote (`list "core.proxy`) each printed the error and the help and did not
  raise. No `SystemExit` or other exception came out of 29 odd inputs (`%s`, `{x}`, a NUL byte, a trailing
  backslash, a 10,000-character argument list, 20-digit numbers; `out-q3b.txt`). A `type=` function that raises
  something other than `ValueError` or `ArgumentTypeError` would propagate out of `parse_args`, which is
  outside the `try` in `run` (**read**; no such `type` exists in the repository, and none was tried).

### Q1f: Output

`CommandClass.run` calls `run_finish`, which calls `format_return_message` when `format` is true. The frame is
`Begin Command`, `Start:`, the lines, `Finish:` and `End Command`, with extra sections when the
`simple_output` setting is off. The output goes to `clients=[client_id]` of the client that typed the command
and to every client (`clients=None`) when the line has no client id (**verified**, `out-q3c.txt`).

When this was measured, `CommandClass.format` and `.preamble` were stored and nothing read them.
`AddCommand(format=False, preamble=False)`, used by `_command_run_history`, was not honoured:
`#bp.core.commands.! -99` was framed with `Begin Command` (**verified**, `out-q1c.txt`; grep of the package:
the only matches for `.format` and `.preamble` as attributes were the assignments in
`CommandClass.__init__`). Fixed in CM-2: `run_internal_command_from_event` now passes `command_item.format`
and `format_return_message` skips the `Begin Command`, start, finish and `End Command` lines when
`preamble` is false.

---

## Q2: Is the Command State Kept Consistent?

### Q2a: Registration

**Verified** by `out-q2.txt` and `out-q3.txt` unless marked.

- **Discovery** is by name and attribute: `get_command_functions_in_object` keeps methods whose `__name__`
  starts with `_command_` and that have `command_data`. Any of the three decorators sets `command_data`. It
  runs from `ev_plugin_loaded` for the plugin, and for every loaded plugin at startup and when the commands
  plugin itself loads.
- **Duplicates.** `_api_command_add_by_func` appends to `commands_list` every time. Calling
  `update_commands_for_plugin` for a loaded plugin doubled its entries (16 to 32); two `force=True` re-adds of
  one command left it listed four times. After the run `commands_list` held 151 entries and the command table
  133 (CM-7). `command_data` is a dictionary and was not duplicated.
- **The `else` branch is live.** The plan for this audit suspected that the `else` branch for a command with
  no `name` is dead because `AddCommand.__call__` always sets one. It is not dead: a method decorated with
  `AddParser` alone has no `name`, and the branch names it from the method. `plugins.test.cmddec`'s `raise`
  command registered as `raise`, and its `command_data.command` held only `autoadd` and `kwargs`.
  `AddCommand` is optional.
- **`autoadd=False`** skipped a command at load and `command.add.by.func(..., force=True)` added it.
- **A badly named decorated method** (`wrongname`, decorated with both) is skipped silently at load (CM-9).
- **A placeholder error** in a name stopped registration of the commands after it (`badfmt` ended with one
  command of four, `aaa`) (CM-4).

### Q2b: Unload and reload of a plugin

**Verified.** Reloading `plugins.audit108.reent` through the loader left 16 `commands_list` entries and
`command_data` with 16, and the lifetime count of a command stayed at 2 with `count_since_reload` back to 0.
Unloading removed the `command_data` entry and every list entry, kept the counts in
`saved_command_counts`, and loading again restored the count and emptied the saved entry (#96, #92).
`plugin.id.is.valid` is still true after an unload, because it tests membership of the table of *discovered*
plugins, not of loaded plugins, so the gate on `_api_command_remove_for_plugin` is open when
`ev_plugin_unloaded` fires. The same fact makes the checks in `command.data.get` and
`command.list.formatted` too weak (CM-5).

### Q2c: Plugins that are valid but have no command data

`plugin.id.is.valid` is true for the nine plugins the loader found but did not load in the probe
(`plugins.debug.*`, `plugins.test.*`). **Verified**, `out-q2a.txt`, for `plugins.debug.api`: `command.data.get`,
`command.list.formatted`, `command.help.format` and `command.run` raised `KeyError`; `command.count` returned 0.
`#bp.core.commands.list plugins.debug.api` printed `Error running command` and counted an error. The client
path `#bp.debug.api.set` cannot reach this, because `find_command` matches only loaded plugins. A *loaded*
plugin without command data can occur (CM-4); a client typing `#bp.audit108.reent.nomsg` for such a plugin
raised `KeyError` inside `find_command`, in the event, and received nothing (**verified**, `out-q2bbad.txt`; the
ERROR line is in `err-q2bbad.txt`). The event system contained it, the next line (`look`) was handled normally
and `current_input_event` was None again. So this is an ordinary, contained defect (CM-5).

### Q2d: `_api_remove_command`

It has no `@AddAPI`, so `plugins.core.commands:remove.command` does not exist (**verified**, `out-q5.txt` shows
the API list). Called directly it worked: it removed the command and called `<plugin>:data.update`
(**verified**). It does not remove the `commands_list` entry (**read**). Nothing calls it (**verified**, grep
in `out-q6-dead.txt` shows no caller in `src` or `tests`; CM-13).

### Q2e: History

**Verified**, `out-q2c.txt` and `out-q2d.txt` unless marked.

- **Size.** `add_command_to_history` appends and then pops when `len >= historysize`. With `historysize=5` the
  list stayed at 4 entries; `historysize` entries are never held (CM-8).
- **Dedupe.** Sending a line already in the history moved it to the end instead of adding a second copy.
- **What is recorded.** `_eventcb_check_for_command` adds the line when `event_record["showinhistory"]` is true
  and the line is not internal. `showinhistory` starts as the `show_in_history` of the `ProcessDataToMud`
  (True for client input; a record built with `show_in_history=False` was not recorded), and
  `run_internal_command_from_event` then overwrites it with the third value of `find_command`. That value is
  `True` for every command that is found and `False` for a help or error page. So `#bp.core.commands.list`,
  whose command says `show_in_history=False`, was recorded, and `#bp.nope.x` was not (CM-1).
- **The flag leaked to the next line (fixed in #390).** Before the fix, after an unknown `#bp` command, the lines after it in the same input
  were not recorded: `#bp.nope.x|lookD` left the history without `lookD`, while `lookC|#bp.nope.x` recorded
  `lookC` (CM-3).
- **`_command_run_history` (`!`)** indexes with `history[number]` when the list is shorter than `historysize`,
  and `history[number - 1]` when it is as long, so `! -1` shows the last entry in one case and the one before
  it in the other, `! 0` shows the first entry and `! 4` with four entries raises `IndexError` (the length
  guard uses `<` against `abs(number)`) (CM-8).
- **`!` shows, it does not re-run.** It sends `Commands: rerunning command <x>` and then `<x>` to the clients
  as text. The line did not go to the MUD and the command was not run again (**verified**, `out-q1_flow.txt`:
  the only line sent to the MUD after `! 1 2` was the original `! 1 2`, with `send` False). Both lines go to
  `clients=None`, that is every logged-in client that may see internal lines, not only the client that typed
  it (**verified**, `out-q3c.txt`) (CM-8).
- **`history` numbering** uses `list.index`, so a duplicate would be shown with the first one's number (**verified**
  with a hand-made list `x, y, x`: `0 : x`, `1 : y`, `0 : x`). `add_command_to_history` removes duplicates
  first, so this does not arise through the plugin.

### Q2f: The re-entrancy guard

`_eventcb_check_for_command` skips an event whose record equals `current_input_event`, and
`current_input_event` is in `attributes_to_save_on_reload`.

- **A nested line is processed normally.** A command that sends another client line through
  `ProcessDataToMud` from inside the event produced its own event record. A command that sends its own line
  again ran four times (to the cap the probe set), so the guard never fired for it (**verified**,
  `out-q3.txt`, "same depth 4").
- **The guard acts when the commands plugin reloads from inside its own event.** Running
  `#bp.core.pluginm.reload plugins.core.commands` logged `called out of order` and
  `was processed 3 times` warnings (the new instance's callback is registered during the event), and the
  `reload` command still ran once (count 1) (**verified**, `out-q2b.txt`, `err-q2bbad.txt`). That the guard
  is what stops the second run is **read**, not shown: it was not switched off to compare.
- **A failure leaves a stale record.** After an exception in `find_command`, `current_input_event` kept the
  failed record until the next line reset it (**verified**, `out-q3.txt`). It is also saved across a reload.

### Q2g: The commands plugin's own reload

`_phook_commands_save_on_reload` saves every command's counts when `is_reloading_f` is true, and
`BasePlugin` caches `attributes_to_save_on_reload` only in the same case. `is_reloading_f` is set by the
`reload` command of the plugin manager and not by `libs.plugins.loader:plugin.reload`. **Verified**:
reloading the commands plugin with the `reload` command kept the counts (`history` 1 and a user command 1,
`out-q2b.txt`); reloading it with the loader API alone lost them (`history` 1 to 0, `out-q2.txt`). The second
is how a plugin or test that calls the API would reload it.

With CM-4 in play the reload is incomplete: with `plugins.audit108.badfmt` loaded before `plugins.audit108.reent`,
`_add_commands_for_all_plugins` stopped at `badfmt`, `reent` was loaded and had no command data, and its saved
counts stayed in `saved_command_counts` (**verified**, `out-q2bbad.txt`).

---

## Q3: What Happens on a Failure?

### Q3a: Outcomes of a command

**Verified**, `out-q3.txt`; the client sees the lines shown.

| What the command does | What the client gets | `run()` returns | Counted |
| :--- | :--- | :--- | :--- |
| Raises `RuntimeError` | `Error running command: <cmd>`; ERROR log with traceback | `False`, reason `function returned False` | one error, `last_error` `RuntimeError: ...` |
| Returns `(False, [msg])` | `msg`, a blank line, then the help | `False`, reason `function returned False` | a call, no error |
| Returns `None` or a bare `True` | the frame, no lines | `True`, `command ran successfully` | a call |
| Returns `(True, "hi")` | one line per character: `h`, `i` | `True` | a call |
| Bad or missing argument, unclosed quote | `@RError: ...`, a blank line, the help | `False`, reason `could not parse args` | not counted |
| `-h` | the help | `True`, reason `help` | not counted |
| Unknown command | the error page and the plugin's command list; the line is dropped | not run | not counted |

The reason string for an exception says `function returned False`, the same as for a `False` return, so a
caller of `command.run` cannot tell them apart (CM-10).

### Q3b: A failure outside the `try`

`CommandClass.run` wraps only the call of the command function. `find_command` and `format_return_message`
are outside it. **Verified**, `out-q3.txt`, `err-q3.txt`: with `find_command` replaced by a function that
raised, the client received nothing, the line was dropped (`send` was already False), the event system logged
`raise_event - event ev_to_mud_data_modify with function _eventcb_check_for_command raised an exception`, and
the next line was handled normally. A failure in `format_return_message` did the same, after the command had
run and been counted. The same happened for the real `KeyError` cases in CM-5 and CM-6. CM-10.

### Q3c: View-only clients

`Client.client_read` sends the input of a view-only client to `process_data_from_view_only_client`, which
sends the fixed reply `As a view only user, you cannot enter commands`. **Verified** by reading the branch
and by grep: `ProcessDataToMud(` is called with client input at one place, the non-view branch at
`src/bastproxy/libs/net/client.py` line 510; the other call is in the test plugin `lkattr`. So no
view-only input reaches `ev_to_mud_data_modify` (**read**).

### Q3d: Output routing

A command run from the event sends its reply to `clients=[client_id]`, so only the client that typed it gets
it (**verified**). `SendDataDirectlyToClient.can_send_to_client` does not deliver an internal line to a view
client unless the client is in `clients` (**read**, `src/bastproxy/libs/records/rtypes/clientdata.py`). The
history command `!` is the exception noted in Q2e: it sends to every client.

### Q3e: Antispam

**Verified**, `out-q3b.txt`: 45 identical lines reached the MUD as 47 lines, with the `antispamcommand`
(`look`) inserted at positions 20 and 41 of the 47, that is before the 21st and the 41st identical line. The
`no_multiple_commands` branch cannot run, because nothing ever adds to that dictionary (**verified**, grep in
`out-q6-dead.txt`: two matches, its creation and its test) (CM-13).

---

## Q4: What Is Untested?

Measured by `coverage.txt` (full suite) and `coverage-narrow.txt` (the five command test files).

| File | Statements | Missed | Cover (full suite) | Cover (command tests only) |
| :--- | --: | --: | --: | --: |
| `_commands.py` (the plugin) | 549 | 374 | 28.08% | 28.08% |
| `_command.py` | 138 | 36 | 70.00% | 70.00% |
| `_utils.py` | 49 | 4 | 87.30% | 87.30% |
| `cmdargs.py` | 12 | 0 | 100.00% | 41.67% |
| `src/bastproxy/libs/argp.py` | 28 | 0 | 97.06% | 97.06% |

The rest of the suite adds nothing to `_commands.py`. Of its missed ranges, the ones that matter are the
settings registration (`82-156`), `command.add.by.func` (`328-411`), `command.remove.for.plugin`
(`468->exit`), `pass_through_command_from_event` (`703-757`), every `error_*` page (`796-890`), `find_command`
and `find_command_split_command_string` (`909-1021`), the body of `run_internal_command_from_event`
(`1038-1075`), `_api_remove_command` (`1183-1212`), `command.list.formatted` (`1253-1305`), and the bodies of
`_command_list`, `_command_run_history` and `_command_history` (`1344-1362`, `1429-1445`, `1457-1468`).
In `_command.py` the untested ranges are the `shlex` and `ArgumentError` branches of `parse_args`
(`170-182`) and all of `format_return_message` (`196-302`).

Test files that mention each symbol (`out-q4-tests.txt`; a text match, not proof of exercise):

- **No test file names:** `find_command_split_command_string`, `add_command_to_history`, `_command_run_history`,
  `_command_history`, `AddCommand`, `AddParser`, `AddArgument`, `command.add.by.func`,
  `_api_command_add_by_func`, `format_return_message`, `command.data.get`, `command.list.formatted`,
  `command.help.format`, `_eventcb_plugin_loaded`, `get_command_functions_in_object`, `proxy_help`,
  `error_command_not_found_in_plugin`, `plugin.list.formatted`, `set_command_autoadd`.
- **Named only in a stub test:** `find_command` (`test_commands_plugin_stats.py`,
  `test_commands_plugin_whitespace.py`), `pass_through_command_from_event`, `run_internal_command_from_event`
  and `_eventcb_check_for_command` (`test_commands_plugin_whitespace.py`, with a `MagicMock` plugin that
  replaces the called methods), `update_command` (`test_commands_plugin_unload.py`,
  `test_commands_plugin_stats.py`).

The bugs in Q2 and Q3 sit in this uncovered code. CM-14.

---

## Q5: Where the Docs Disagreed With the Code

[Command System](command_system.md) disagreed with the code in 23 places; each is corrected on that page. The
checks are **verified** unless marked **read**.

1. **Command ids.** The page wrote `#bp.<plugin>.<command>`, `#bp.commands.list`, `#bp.commands.history`,
   `#bp.commands.!` and `#bp.core.commands.detail`; a command needs the package: `#bp.core.commands.list`.
   `#bp.commands.list` printed the error page (`out-q1_flow.txt`). Corrected in the overview, the invocation
   section, the built-in commands and the examples.
2. **The `CommandsPlugin` snippet.** It showed `__init__`, `commands_list = {}`, and `command_prefix`.
   The plugin builds state in `_phook_init_plugin`, `commands_list` is a `list[str]`, and the prefix is the
   `cmdprefix` setting. Replaced with the real attributes (**read**).
3. **The `CommandClass` snippet.** It showed the constructor as `(name, function, plugin_id, **kwargs)`,
   `ArgumentParser()` created inside, and a `Base` group default. The constructor takes
   `(plugin_id, name, function, arg_parser, format, group, preamble, show_in_history, shelp)`, the parser is
   built by the plugin, and the group defaults to the plugin id (**read**).
4. **`format`, `preamble` and `show_in_history` are described as working.** When measured they were stored
   and never read (Q1f, Q2e; CM-1, CM-2). All three are now honoured (CM-1 fixed in #388, CM-2 in
   #389), and the page says so.
5. **Output "with a `#BP:` preamble", color conversion and line endings.** The output is the framed block in
   Q1f.
6. **Decorator order.** "Must be applied in this order: `AddCommand`, `AddParser`, `AddArgument`" and
   "`@AddCommand` marks a method as a command." Registration needs only the name `_command_*` and the
   `command_data` attribute that any of the three decorators creates; `AddCommand` is optional (Q2a). Only
   the order of several `AddArgument` lines matters.
7. **`AddCommand` options.** `autoadd` was not listed. Added.
8. **`AddParser` options.** `formatter_class` is overwritten by `argp.CustomFormatter` after the parser is
   built, and positional `AddParser(...)` arguments are stored and never used (**read**, `_commands.py` L381;
   grep in `out-q6-dead.txt`). Both are noted.
9. **Default name.** "uses method name" is true, with `_command_` removed; an unnamed command given only
   `AddParser` is named in the `else` branch.
10. **Placeholders.** Names, descriptions and argument help are formatted with the plugin's attributes
    (`{plugin_id}`); a stray `{` or `}` breaks registration (CM-4). Not mentioned before. Added.
11. **"Fuzzy matching" with no detail.** Replaced with the real rules (Q1d).
12. **Invocation steps.** The list left out the separator split, the left-strip, and that every prefix line
    is kept from the MUD. Corrected, along with the 10-step "Command Execution Flow" (Q1a).
13. **`success, message, error = ...command.run(...)`.** `command.run` returns a pair `(success, messages)`
    and `(None, [])` for a missing command; the plugin id must be the full id (`plugins.core.commands`).
14. **`plugins.core.commands:get.commands.for.plugin`** and **`plugins.core.commands:format.output.line`**
    do not exist (`out-q5.txt`). Replaced with APIs that do.
15. **`#bp.commands.list [plugin] [command]`.** It needs the full plugin id (`plugins.core.proxy`);
    `list core.proxy` printed `No plugins found`, and `list plugins.core` listed the plugins of the package.
16. **`! 5`, "reruns".** `!` shows the history entry and does not run it; numbers are 0-based as in `history`
    (Q2e). The doc described re-execution.
17. **History "Commands with `show_in_history=False` are excluded."** They are not (CM-1).
18. **"Size-limited queue."** It holds `historysize - 1` entries (CM-8).
19. **Troubleshooting, "Ensure `set_command_autoadd(True)` is called."** `autoadd` is true by default; the
    switch is `AddCommand(autoadd=False)`. `set_command_autoadd` is used once, by the base plugin.
20. **Troubleshooting, "History Not Working."** Success is not a condition for recording; a command that
    fails is recorded the same.
21. **"Custom Command Prefix: change the command prefix per plugin."** The prefix is one global setting,
    `cmdprefix` of `plugins.core.commands`, and a prefix containing a dot never matches (CM-12).
22. **"Conditional Command Registration"** defined a decorated function inside a method. Discovery scans the
    attributes of the plugin instance, so such a function is never found (**read**). Replaced with
    `autoadd=False` plus `command.add.by.func(..., force=True)`, which was tried.
23. **"Test Arguments"** caught `SystemExit`. The parser raises `ArgumentError` (Q1e).

---

## Q6: Patterns and Anti-Patterns

Greps, all scoped to `src/bastproxy/plugins/core/commands` with `--include=*.py` (`out-q6-greps.txt`):

- `grep -rnE 'except( Exception| BaseException)?:'`: 1 match (`_api_command_add_by_func`). The other broad
  handler is `except Exception as exc:` in `CommandClass.run`, which that pattern does not match.
- `grep -rnE 'Path|os\.path'`: none
- `grep -rnE '^[A-Za-z_]+ = |^global |^[A-Z_]+: '`: the `PLUGIN_*` constants, two `__all__`, `CANRELOAD` and
  `commands_at_startup`
- `grep -rnE 'print\('`: none; `grep -rnE 'sys\.exit'`: none
- `grep -rnE 'self\.api\('`: 125 matches
- `grep -rnE 'raise '`: none; `grep -rnE 'return False|return None'`: 12 matches
- `grep -rnE 'type: ignore|noqa|pylint: disable|pyright: ignore'`: 2 matches, both `pyright: ignore`

| # | Pattern | Where | Consistent? | Verdict |
| --: | :--- | :--- | :--- | :--- |
| 1 | **Decorator-built parser**: `AddCommand`, `AddParser` and `AddArgument` hang a `CommandFuncData` on the function; the plugin builds the `ArgumentParser` at registration | `_utils.py`, `_api_command_add_by_func` | Yes | **Keep.** It keeps a command's parser next to its function and the order of `AddArgument` follows argparse. What needs fixing is what it stores and nothing reads (CM-13; CM-1 and CM-2 are fixed). |
| 2 | **Discovery by name** (`_command_*` and `hasattr(command_data)`), checked twice | `get_command_functions_in_object`, `_api_command_add_by_func` | Yes | **Change (CM-9).** A decorated method with the wrong name is skipped without a log line. |
| 3 | **Detection inside a modify event** on `ev_to_mud_data_modify`, which also keeps the line from the MUD | `_eventcb_check_for_command` | Yes | **Keep.** It lets other plugins see and change a line before or after. The risks are in what the callback does when it fails (CM-10) and the flag it left on the record (CM-3, fixed in #390). |
| 4 | **Raising `ArgumentParser.error`** instead of exiting | `argp.py` | Yes | **Keep.** No input in the fuzz run exited the process or escaped (Q1e). |
| 5 | **`parse_known_args`** | `CommandClass.parse_args` | Yes | **Change (CM-11).** Unknown arguments and abbreviated options are accepted silently. |
| 6 | **`str.format(**plugin.__dict__)`** on names, descriptions and argument help, outside a `try` | `_api_command_add_by_func` | Yes | **Change (CM-4).** One bad string ends registration of the rest of the plugin and, on a commands reload, of the other plugins. |
| 7 | **Service location through `self.api("...")`** | 125 calls; `CommandClass` builds its own `API` | Yes | **Keep.** The project-wide trade covered by [Plugin System Findings](plugin_system_findings.md) and [API System Findings](api_system_findings.md). |
| 8 | **Catch-all `except Exception`** | `_api_command_add_by_func` (creating the `CommandClass`), `CommandClass.run` | Yes | **Keep.** Both log with `exc_info` and tell the user. The one in `run` is why a failing command never takes down the event. The gap is the code outside it (CM-10). |
| 9 | **Silent returns**: `return None` or `return` with a warning, or nothing at all | `_api_command_add_by_func`, `get_command_data_from_plugin`, `_api_command_data_get` | No | **Change (CM-9; CM-5 fixed in #392).** The lookups raised `KeyError` for a plugin with no data while the same functions return `None` and `{}` for a plugin that is not valid. |
| 10 | **Parallel indexes**: `commands_list` (list) beside `command_data` (dict) | `CommandsPlugin` | No | **Change (CM-7).** The list gets duplicates; it is read only by the summary count. |
| 11 | **Dead state** | `commands_at_startup`, `default_help_command`, `no_multiple_commands`, `api_get_all_commands_list`, `_api_remove_command`, `AddParser` positional arguments | n/a | **Change (CM-13).** |
| 12 | **Magic indexes into a list the plugin edits**: the history | `add_command_to_history`, `_command_run_history` | No | **Change (CM-8).** |
| 13 | **Re-entrancy guard on a saved attribute** (`current_input_event`) | `_eventcb_check_for_command` | Yes | **Keep, small.** It matters only for the commands plugin's own reload (Q2f); a failing event leaves a stale record until the next line. |
| 14 | **Strings for paths** | none | n/a | **Keep.** The package touches no path. |
| 15 | **Hidden global state** | `CANRELOAD` (read by the loader) and `commands_at_startup` (never read) at module level; the rest is on the plugin instance | Yes | **Keep** `CANRELOAD`; remove `commands_at_startup` (CM-13). |
| 16 | **`CmdArgsRecord` in the plugin's `libs/data`** | `cmdargs.py` | n/a | **Keep.** It is a record type used only by this plugin. Its header comment names a different directory (Other Observations). |
| 17 | **Typing**: the package is under a mypy `ignore_errors` override and has no annotations | whole package | Yes | **Keep here.** Tracked by #6. |

---

## New Defects

Each entry links the issue it was filed as, and gives the body it was filed with, in the fields of the
matching template in `.github/ISSUE_TEMPLATE/`. Line references are to
`src/bastproxy/plugins/core/commands/plugin/_commands.py` at the base commit.

### CM-1: `show_in_history=False` on a command has no effect

**Status:** fixed in #388 (`find_command` returns `command_item.show_in_history`)
**Issue:** #388
**Location:** `CommandsPlugin.find_command` (the `True` in the "got it all" return), `run_internal_command_from_event`
(L1042); `CommandClass.show_in_history`.
**Evidence (verified):** Q2e: `#bp.core.commands.list`, `detail`, `history` and `!` declare
`show_in_history=False` and were recorded. Only unknown commands and help pages were not.
**Fix:** return `command_item.show_in_history` as the third value of `find_command`.

> **Proposed issue (fix):** `fix: commands that set show_in_history=False are still recorded in the history`
>
> **Bug Description:** `find_command` returns `True` as its `show_in_history` value for every command it
> finds. `run_internal_command_from_event` writes that into the event record, so the `show_in_history`
> option of `AddCommand`, which is stored on `CommandClass` and read nowhere, is ignored.
> **Steps to Reproduce:** send `#bp.core.commands.list`, then `#bp.core.commands.history`.
> **Expected vs Actual Behavior:** Expected: neither is in the list, as their decorators say. Actual: both
> are.
> **Environment:** base commit `5a870c5`, Python 3.12.12.
> **Error Output:** none.
> **Additional Context:** Command System Findings, Q2e. The same applies to `format` and `preamble` (CM-2).

### CM-2: `format=False` and `preamble=False` on a command have no effect

**Status:** fixed in #389 (the options are honoured: `run_internal_command_from_event` passes the command's `format`, and
`format_return_message` drops the `Begin Command`/`End Command` lines when `preamble` is false)
**Issue:** #389
**Location:** `CommandClass.run_finish` (`if format:`, the argument, not the attribute), `CommandClass.__init__`
(`self.format`, `self.preamble`); `run_internal_command_from_event` (passes `format=True`).
**Evidence (verified):** Q1f: `#bp.core.commands.! -99`, declared `format=False, preamble=False`, was framed
with `Begin Command`. A grep for readers of the attributes finds none.
**Fix:** either honour `command.format` when the event runs the command, or remove both options and their
documentation.

> **Proposed issue (fix):** `fix: the format and preamble options of AddCommand are stored and never used`
>
> **Bug Description:** `CommandClass.format` and `.preamble` are set in `__init__`; `run_internal_command_from_event`
> always passes `format=True`. `_command_run_history` asks for neither.
> **Steps to Reproduce:** send `#bp.core.commands.! -99`.
> **Expected vs Actual Behavior:** Expected: the one-line reply without the `Begin Command` frame. Actual:
> the frame is added.
> **Environment:** as CM-1. **Error Output:** none.
> **Additional Context:** Command System Findings, Q1f. Decide whether the options stay.

### CM-3: An unknown `#bp` command stops the lines after it in the same input from being recorded

**Status:** fixed (#390)
**Issue:** #390
**Location:** `run_internal_command_from_event` (L1042-1046), `_eventcb_check_for_command` (L1169).
**Evidence (verified):** Q2e: `#bp.nope.x|lookD` recorded neither line; `lookC|#bp.nope.x` recorded `lookC`;
`#bp.nope.x|#bp.core.commands.list|lookI` recorded `lookI` again, because a found command sets the flag to True.
**Fix:** decide per line, from the line's own result, and do not write the result into state the next line
reads. Done in #390: `_eventcb_check_for_command` reads the input's flag before the line runs, uses the
line's own value for the history decision, and puts the input's value back. The `UpdateFlag.MODIFY` text
at L1045 is also not an f-string and prints `{show_in_history}`; that is not part of #390.

> **Proposed issue (fix):** `fix: a line after an unknown #bp command in the same input is not recorded in the history`
>
> **Bug Description:** A line that starts with the prefix but is not a command sets `showinhistory` to False
> for the lines that follow in the same input.
> **Steps to Reproduce:** send `#bp.nope.x|lookD` and look at the history.
> **Expected vs Actual Behavior:** Expected: `lookD` is recorded like any other line. Actual: it is not.
> **Environment:** as CM-1. **Error Output:** none.
> **Additional Context:** Command System Findings, Q2e.

### CM-4: A bad placeholder in a command's name, description or argument help stops the plugin's other commands from registering

**Status:** fixed in #391
**Issue:** #391
**Location:** `_api_command_add_by_func` (L360-378: the `.format(**func.__self__.__dict__)` calls);
`update_commands_for_plugin` (L311) and `_add_commands_for_all_plugins` (L280) have no `try` around the
per-item call.
**Evidence (verified):** Q2a, Q2g: a command named `{nope}` in a plugin whose commands sort around it
registered only `aaa` of four; the plugin loaded; the only trace is `raise_event - event ev_plugin_loaded
... raised an exception` / `KeyError: 'nope'` in the log (`err-q3.txt`). After a reload of the commands
plugin a plugin loaded after it had no command data (`out-q2bbad.txt`). Description and argument-help
strings go through the same call (**read**), so any `{` or `}` in them does the same.
**Fix:** format inside the existing `try` or a new one, log the command and the string, skip that command,
and wrap the per-command and per-plugin loops so one failure cannot end them.

> **Proposed issue (fix):** `fix: one bad placeholder in a command stops registration of the plugin's other commands`
>
> **Bug Description:** `_api_command_add_by_func` formats the name, description and argument help with the
> plugin's attributes outside any `try`. The `KeyError` ends `update_commands_for_plugin`'s loop. On a
> commands-plugin reload it also ends `_add_commands_for_all_plugins`, so later plugins have no commands.
> **Steps to Reproduce:** load a plugin with `@AddCommand(name="{nope}")` between two other commands. List
> its commands.
> **Expected vs Actual Behavior:** Expected: that command is skipped with a clear log line and the others
> register. Actual: the commands after it (including the base `set`) are missing and the only message is an
> event-callback traceback.
> **Environment:** as CM-1. **Error Output:** `KeyError: 'nope'`.
> **Additional Context:** Command System Findings, Q2a and Q2g.

### CM-5: A plugin with no command data raises `KeyError` in the lookups

**Status:** fixed in #392 (the four lookups use `self.command_data.get(plugin_id, {})`; `command.list.formatted` still raises for the `Base` group, CM-6)
**Issue:** #392
**Location:** `_api_command_data_get` (L526), `get_command_data_from_plugin` (L627), `_api_command_list_formatted`
(L1260), `_command_list` (L1353).
**Evidence (verified):** Q2c: for `plugins.debug.api` (valid, not loaded) four APIs raised `KeyError`, and
`#bp.core.commands.list plugins.debug.api` printed `Error running command`. For a loaded plugin without command
data (CM-4), `#bp.audit108.reent.nomsg` raised inside `find_command`, in the event: the client received
nothing. The event system contained it; the next line was handled normally.
**Fix:** use `self.command_data.get(plugin_id, {})`.

> **Proposed issue (fix):** `fix: command lookups raise KeyError for a valid plugin that has no command data`
>
> **Bug Description:** The four lookups index `command_data[plugin_id]` after `plugin.id.is.valid`, which is
> true for every discovered plugin, loaded or not.
> **Steps to Reproduce:** `#bp.core.commands.list plugins.debug.api`.
> **Expected vs Actual Behavior:** Expected: `There are no commands in plugin plugins.debug.api`. Actual:
> `Error running command`, and an error is counted against `list`.
> **Environment:** as CM-1. **Error Output:** `KeyError: 'plugins.debug.api'`.
> **Additional Context:** Command System Findings, Q2c.

### CM-6: `command.list.formatted` raises `KeyError` for a plugin with no command in the `Base` group

**Status:** open
**Issue:** #393
**Location:** `_api_command_list_formatted` (L1302: `groups["Base"]`).
**Evidence (verified):** Q3 and `out-q3d.txt`: typing an unknown command for a plugin whose only command is
not in the `Base` group (`#bp.audit108.badfmt.zzz`) raised `KeyError: 'Base'` from the "command not found"
page, inside the event; the client got nothing. `#bp.core.commands.list plugins.audit108.badfmt` did the same
inside the command. A normal plugin has the `Base` group from the base plugin's `set`, `help`, `reset` and
`save`, so this is reachable after CM-4 or `autoadd=False`.
**Fix:** `groups.get("Base", [])`.

> **Proposed issue (fix):** `fix: command.list.formatted raises KeyError when a plugin has no Base command`
>
> **Bug Description:** The `Base` section is built with `groups["Base"]`.
> **Steps to Reproduce:** with a plugin whose commands are all outside `Base`, send an unknown command for it.
> **Expected vs Actual Behavior:** Expected: the error page. Actual: nothing is shown.
> **Environment:** as CM-1. **Error Output:** `KeyError: 'Base'`.
> **Additional Context:** Command System Findings, Q3b.

### CM-7: `commands_list` gets a duplicate entry every time a command is added again

**Status:** open
**Issue:** #394
**Location:** `_api_command_add_by_func` (L409); `update_commands_for_plugin`.
**Evidence (verified):** Q2a: `update_commands_for_plugin` on a loaded plugin moved its entries from 16 to 32;
two `force=True` re-adds of one command listed it four times; 151 entries against 133 commands in the table.
`Total Commands for all plugins` in the summary is `len(commands_list)`.
**Fix:** add only when `f"{plugin_id}.{command_name}"` is not already there, or derive the list from `command_data`.

> **Proposed issue (fix):** `fix: commands_list collects duplicates when a command is added again`
>
> **Bug Description:** `command.add.by.func` appends without checking.
> **Steps to Reproduce:** call `command.add.by.func` twice for one method with `force=True`.
> **Expected vs Actual Behavior:** Expected: one entry. Actual: two.
> **Environment:** as CM-1. **Error Output:** none.
> **Additional Context:** Command System Findings, Q2a.

### CM-8: The history keeps `historysize - 1` entries and `!` picks the wrong one in two cases

**Status:** open
**Issue:** #395
**Location:** `add_command_to_history` (L597), `_command_run_history` (L1430-1443).
**Evidence (verified):** Q2e: with `historysize=5` the list stayed at 4. With four entries and `historysize=5`
`! -1` showed the last entry; with four entries and `historysize=4` it showed the one before. `! 4` with four
entries raised `IndexError` (`Error running command`); `! -4` raised it in the second case. `!` output goes to
every client (`clients=None`), not only the one that typed it.
**Fix:** pop when `len > historysize`; index with one rule; guard `-len <= number < len`; pass `clients` from
the event.

> **Proposed issue (fix):** `fix: the command history holds one entry too few and ! indexes inconsistently`
>
> **Bug Description:** `add_command_to_history` pops at `>=`. `_command_run_history` subtracts one from the
> index when the list is as long as `historysize`, and its bounds check lets `number == len` through.
> **Steps to Reproduce:** set `historysize` to 5, add six lines, run `#bp.core.commands.history`, then
> `#bp.core.commands.! 4`.
> **Expected vs Actual Behavior:** Expected: five entries, and `! 4` shows the fifth. Actual: four entries;
> `! 4` raises `IndexError`.
> **Environment:** as CM-1. **Error Output:** `IndexError: list index out of range`.
> **Additional Context:** Command System Findings, Q2e.

### CM-9: A decorated method not named `_command_*` is skipped without a message

**Status:** open
**Issue:** #396
**Location:** `get_command_functions_in_object` (L319); `_api_command_add_by_func` (L339-345).
**Evidence (verified):** Status table (#98) and Q2a: `wrongname`, decorated with `AddCommand` and `AddParser`,
was not registered and nothing was logged. Calling `command.add.by.func` with it logged `Function is not a
command: wrongname`.
**Fix:** at discovery, log a warning for any method that has `command_data` and a name that does not match.

> **Proposed issue (fix):** `fix: warn when a method with command decorators is not named _command_*`
>
> **Bug Description:** The prefix is the only registration test and its failure is silent.
> **Steps to Reproduce:** decorate `def wrongname(self)` with `AddCommand` and `AddParser` in a plugin and
> load it.
> **Expected vs Actual Behavior:** Expected: a warning that names the method. Actual: none.
> **Environment:** as CM-1. **Error Output:** none.
> **Additional Context:** Command System Findings, #98 row of the status table.

### CM-10: A failure outside `CommandClass.run`'s `try` shows the client nothing, and the failure reasons are wrong

**Status:** open
**Issue:** #397
**Location:** `run_internal_command_from_event` (`find_command`, the sends); `CommandClass.run` (reason strings,
the message type); `CommandClass.run_finish` (`format_return_message`).
**Evidence (verified):** Q3a, Q3b: with `find_command` or `format_return_message` raising, the client got no
reply, the line was dropped, and the only trace was the event system's ERROR line; `current_input_event` stayed
set until the next line. An exception inside a command gave the reason `function returned False`. A command
returning `(True, "hi")` printed `h` and `i` as two lines.
**Fix:** wrap the body of `run_internal_command_from_event` so the client gets `Error running command` for any
exception; give an exception its own reason string; treat a `str` message as one line.

> **Proposed issue (fix):** `fix: tell the client when the command path itself fails, and report the right reason`
>
> **Bug Description:** Only the call of the command function is inside the `try`. An exception in
> `find_command` or in formatting the output is caught by the event system, which logs it; the client sees
> nothing and the line is gone.
> **Steps to Reproduce:** make `find_command` raise, send `#bp.core.commands.list`.
> **Expected vs Actual Behavior:** Expected: an error reply. Actual: silence.
> **Environment:** as CM-1. **Error Output:** `RuntimeError: injected find_command failure`.
> **Additional Context:** Command System Findings, Q3a and Q3b.

### CM-11: Unknown arguments and abbreviated options are accepted silently

**Status:** open
**Issue:** #398
**Location:** `CommandClass.parse_args` (`parse_known_args`); `argp.ArgumentParser`.
**Evidence (verified):** Q1e: `list -x`, `list --nope=1` and `list a b c d` ran with the extras dropped;
`history -c extra` cleared the history; `history --c` cleared it as an abbreviation of `--clear`.
**Fix:** use `parse_args`, set `allow_abbrev=False`, and report the unrecognised arguments with the help.

> **Proposed issue (fix):** `fix: commands ignore unknown arguments and accept abbreviated options`
>
> **Bug Description:** `parse_known_args` discards what it does not recognise, and argparse abbreviations are
> on.
> **Steps to Reproduce:** `#bp.core.commands.history --c`, `#bp.core.commands.list -x`.
> **Expected vs Actual Behavior:** Expected: an error and the help. Actual: the history is cleared, and
> `list` runs.
> **Environment:** as CM-1. **Error Output:** none.
> **Additional Context:** Command System Findings, Q1e.

### CM-12: A `cmdprefix` containing `.` never matches, and nothing validates the setting

**Status:** open
**Issue:** #399
**Location:** `find_command_split_command_string` (L987-992); the `cmdprefix` setting in `_phook_initialize`.
**Evidence (verified):** Q1c: with `#b.p`, every `#b.p.<command>` printed the package error page. The line was
still kept from the MUD.
**Fix:** strip the prefix with `str.removeprefix` before splitting, and reject a prefix with spaces or dots
or a single character at set time.

> **Proposed issue (fix):** `fix: a command prefix containing a dot does not work`
>
> **Bug Description:** The line is split on `.` before the prefix is removed, so a dotted prefix is never an
> element.
> **Steps to Reproduce:** set `cmdprefix` to `#b.p`, send `#b.p.core.commands.list`.
> **Expected vs Actual Behavior:** Expected: the command runs. Actual: the package error page.
> **Environment:** as CM-1. **Error Output:** none.
> **Additional Context:** Command System Findings, Q1c.

### CM-13: Dead state in the commands plugin

**Status:** open
**Issue:** #400
**Location:** `commands_at_startup` (`_utils.py`), `default_help_command`, `no_multiple_commands` (and its
branch in `pass_through_command_from_event`), `api_get_all_commands_list`, `_api_remove_command`, and the
positional `AddParser` arguments.
**Evidence (verified, grep):** `out-q6-dead.txt`: each name has one match, or, for `no_multiple_commands`, a
creation and a test of an always-empty dictionary. `CANRELOAD` is **not** dead: the loader reads it.
**Fix:** delete them, or register `_api_remove_command` with `@AddAPI` and make it remove the list entry.

> **Proposed issue (refactor):** `refactor: remove unused state from the commands plugin`
>
> **Current State:** five attributes and functions, and one decorator argument, are never read or called.
> **Desired State / Success Criteria:** they are removed, or wired in with a test; `doit check` passes.
> **Additional Context:** Command System Findings, Q6 row 11.

### CM-14: Most of the commands plugin is untested

**Status:** open
**Issue:** #401
**Location:** `_commands.py` (28.08%), `_command.py` (70.00%).
**Evidence (verified):** Q4.
**Fix:** tests for `find_command` and `find_command_split_command_string`, `command.add.by.func` and the
decorators, the history code, `command.list.formatted` and the failure paths of CM-4 to CM-6 and CM-10, using
the stub pattern of `tests/plugins/test_commands_plugin_whitespace.py`. Write them with the fixes for CM-1 to
CM-12, not before: a test written against the current behaviour would pin the defects.

> **Proposed issue (chore):** `chore: add tests for command lookup, registration, history and failure paths`
>
> **Task Description:** Cover the symbols Q4 lists as unnamed in any test.
> **Acceptance Criteria:** `_commands.py` coverage above 70%; each CM defect has a regression test.
> **Additional Context:** Command System Findings, Q4.

---

## Other Observations

- **The file header comments name the wrong paths**: `_command.py` and `_utils.py` give an old module name that
  is not where they live, the package `__init__` says `_init_.py`, and `cmdargs.py` names a record-types
  directory it is not in. Cosmetic.
- **`AddCommand` names an unnamed command `" raise"` with a leading space**, from
  `func.__name__.replace("_command_", " ")`; `_api_command_add_by_func` strips it (**read**).
- **`formatter_class` passed to `AddParser` is replaced** by `argp.CustomFormatter` after the parser is
  built (**read**, L381). The `argp` module wraps text at 73 columns and adds the default to the help text.
- **`CommandStats.last_error` keeps the exception text as it is**, so a message containing a colour code
  (`@R`) is shown coloured by the `detail` command (**verified**: the stored value was
  `RuntimeError: boom@Rred`).
- **`command.current.set` is not reset when `format_return_message` fails**, so `current_command` can name a
  command that is no longer running (**read**).
- **A single `|` in an argument is a separator** (Q1b). The regex leaves a doubled `||` alone (**read**); what
  the command then receives was not tried.
- **The `ev_to_mud_data_modify` callback is registered with the default priority**, which is why the commands
  plugin reload registers its new callback during the event it is running in (Q2f).
