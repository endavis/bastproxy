---
title: Aliases
description: Define short names that expand to longer input, with %1 to %9 and %* arguments
audience:
  - users
  - contributors
tags:
  - client
  - aliases
---

# Aliases

The `plugins.client.aliases` plugin stores named aliases. When the first word of a line a client sends is an enabled alias, the line is replaced by the alias's expansion. Aliases are saved in `aliases.txt`, group state in `groups.txt` and the id counter in `state.txt`, in the plugin's data directory, and survive a restart. A file written before ids and hit counts existed still loads: each alias gets an id (in name order) and a hit count of 0.

## Syntax

- An alias matches the first word of the line (after leading spaces), exactly and case-sensitively. A name is one word, has no `%`, is not only digits (a number is an id, see below) and does not start with the command prefix or contain the command separator.
- `%1` to `%9` are the words typed after the alias, split on whitespace. A missing word becomes empty. Digits are read one at a time, so `%10` is `%1` followed by `0`.
- `%*` is the whole rest of the line, stripped.
- `%%1` and `%%*` are escapes: they are sent as the literal `%1` and `%*`.
- If the expansion has no `%1`-`%9` or `%*` reference and arguments were typed, they are appended after a space. With `oa` set to `open all`, `oa door` sends `open all door`.
- Substitution is a single pass, so an argument that contains `%2` is sent as is.
- An expansion that starts with another alias is expanded again, so aliases can build on each other.

Example: after `#bp.client.aliases.add k kill %1`, the line `k orc` is sent as `kill orc`.

## Shortening proxy commands: the prefix match

An enabled alias whose expansion starts with the command prefix also matches a first word of the form `name.tail`. With `map` set to `#bp.client.mapper`, `map.find orc` runs `#bp.client.mapper.find orc`.

- The exact first-word match is tried first, so an alias named `map.find` wins over the prefix match.
- Otherwise each `.` in the word is tried, longest prefix first. The part before the dot must be an enabled alias that starts with the command prefix, and at least one character must follow the dot. `map.`, `mapper` and `maps` do not match `map`, and an alias like `k` = `kill %1` never prefix-matches `k.x`.
- The tail (`.find`, dot included) is attached to the first word of the expansion, before the arguments are substituted. With `m` set to `#bp.client.mapper %1`, `m.find orc` runs `#bp.client.mapper.find orc`. Gluing the tail to the end of the expansion would give `#bp.client.mapper orc.find`. A tail that contains `%` does not match, so typed text is never read as an argument reference.
- The result starts with the command prefix, so it is re-sent like any `#bp` expansion.

## Lines that start with the command prefix (#777)

Lines that start with the command prefix, in any case, are never expanded, and a name cannot start with it. The prefix match above already shortens proxy commands, so a typed `#bp.client.mapper.find` needs no alias. Expanding `#bp` lines would mean running before the commands plugin (priority 50), which breaks [ADR-0017](../decisions/0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md)'s rule that the history holds the typed line.

## Variables in expansions

The aliases plugin does not expand variables itself. `%{name}` references in an expansion are expanded by the [variables](variables.md) plugin right after, when it is loaded. `%%{name}` stays an escape. Without the variables plugin the references are sent as typed.

## Multi-command and `#bp` expansions

An expansion that contains the command separator (`stand|kill %1`) or starts with the command prefix is sent back through the input path. The typed line is not sent, each part runs as typed input, so `#bp` commands run and aliases in each part expand. The command history keeps the typed line, not the parts, and a `!` rerun runs the alias again.

Type the separator doubled when you add such an alias: `#bp.client.aliases.add port stand||look||say %*`. A typed line is split on a single separator before the command runs, so a single `|` would end the `add` command there. The `add` command stores `stand|look|say %*`. The `alias.add` API stores the expansion exactly as it is passed, so a plugin passes the single separator.

The separator is the `cmdseperator` setting of `plugins.core.proxy`, `|` by default. If the expansion has no separator but has `;` (or `|` when the separator is something else), `add` still adds the alias and warns that it will be sent as one line, showing the expansion with the separator doubled, for example `od||oe||on` for `od;oe;on`. A literal `;` is fine, for example in text sent to a channel.

A re-sent expansion takes the alias line's place. In `stand|port x`, where `port` expands to several commands, `stand` is sent first, then the `port` lines (#714).

## Lines that are not expanded

- Lines that start (after leading spaces) with the command prefix.
- Lines that will not be sent to the MUD.
- Lines typed with echo off (such as a password).
- Lines that are not I/O lines.

## Recursion limit

One typed line goes through at most 10 expansions, counted across chains and re-sends. An alias that expands to itself stops there: the line is not sent, a warning is logged with the alias name and the client gets `alias <name>: expansion stopped after 10 levels`.

## Commands

| Command | Does |
|---------|------|
| `#bp.client.aliases.add [-g GROUP] [-d] [-o] <name> <expansion...>` | Add an alias. The expansion is the rest of the line. `-g` sets the group, `-d` adds it disabled. An existing name is refused unless `-o` (`--overwrite`) is given; a replaced alias keeps its id and hit count. The command is not named `set` because every plugin already has a `set` command for its own settings. |
| `#bp.client.aliases.remove <name or id>` | Remove an alias. |
| `#bp.client.aliases.list [match]` | List aliases as `[id] name : expansion`, optionally only names containing `match`. |

| `#bp.client.aliases.enable [name or id] [-g GROUP]` | Enable an alias, or a group. Give exactly one of the two. |
| `#bp.client.aliases.disable [name or id] [-g GROUP]` | Disable an alias, or a group. Give exactly one of the two. |
| `#bp.client.aliases.toggle [name or id] [-g GROUP]` | Flip an alias, or a group, between enabled and disabled. Give exactly one of the two. |
| `#bp.client.aliases.show <name or id>` | Show the id, expansion, group, enabled state, total hits and the hits this session. |

**Ids.** Each alias has an integer id, starting at 1. An id is never reused: the next free id is kept in `state.txt` and removing an alias does not lower it. A command takes a name or an id, and a name is tried first. Names made only of digits are refused when added, so a typed number is never ambiguous. The APIs take names only.

**Hits.** `show` has `total hits`, counted across restarts, and `session hits`, counted since the plugin loaded. Both count real expansions only, not the checks `alias.expansion.is.resent` makes. The total is held in memory and written when the plugin saves (unload, shutdown, the periodic save) and on every add or remove, so a crash loses the hits since the last save.

**Debug logging.** At the DEBUG level of `plugins.client.aliases`, each real expansion is logged with the alias name, whether it matched by name or by prefix, the typed text and the result.

An alias is active only when it and its group are enabled. A group that was never disabled is enabled.

## API

| API | Returns |
|-----|---------|
| `plugins.client.aliases:alias.add(name, expansion, group="", enabled=True)` | `True`, or `False` for a bad name, expansion or group. An existing alias is still replaced, keeping its id and hits; only the `add` command needs `-o`. |
| `plugins.client.aliases:alias.remove(name)` | `True`, or `False` when not defined |
| `plugins.client.aliases:alias.get(name)` | a copy with `expansion`, `group`, `enabled`, `id` and `hits`, or `None` |
| `plugins.client.aliases:alias.exists(name)` | `bool` |
| `plugins.client.aliases:alias.list()` | a copy, name to alias |
| `plugins.client.aliases:alias.enabled.set(name, enabled)` | `True`, or `False` when not defined |
| `plugins.client.aliases:alias.is.enabled(name)` | `True` only when the alias and its group are enabled |
| `plugins.client.aliases:alias.group.enabled.set(group, enabled)` | how many aliases are in the group |
| `plugins.client.aliases:alias.group.is.enabled(group)` | `bool` |
| `plugins.client.aliases:alias.expansion.is.resent(line)` | `bool`: whether the aliases at the start of the line, following a chain, expand to something that is re-sent (it contains the separator or starts with the command prefix). Session hits are not counted. |

## Where expansion happens

The plugin listens to `ev_to_mud_data_modify` at priority 55, after the commands plugin (priority 50) and before variables (priority 60). See [ADR-0017](../decisions/0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md), [ADR-0016](../decisions/0016-user-variables-expand-name-references-on-the-input-path.md) and the [data flow](../claude/data_flow.md).
