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

The `plugins.client.aliases` plugin stores named aliases. When the first word of a line a client sends is an enabled alias, the line is replaced by the alias's expansion. Aliases are saved in `aliases.txt` and group state in `groups.txt`, in the plugin's data directory, and survive a restart.

## Syntax

- An alias matches the first word of the line (after leading spaces), exactly and case-sensitively. A name is one word, has no `%` and does not start with the command prefix or contain the command separator.
- `%1` to `%9` are the words typed after the alias, split on whitespace. A missing word becomes empty. Digits are read one at a time, so `%10` is `%1` followed by `0`.
- `%*` is the whole rest of the line, stripped.
- `%%1` and `%%*` are escapes: they are sent as the literal `%1` and `%*`.
- If the expansion has no `%1`-`%9` or `%*` reference and arguments were typed, they are appended after a space. With `oa` set to `open all`, `oa door` sends `open all door`.
- Substitution is a single pass, so an argument that contains `%2` is sent as is.
- An expansion that starts with another alias is expanded again, so aliases can build on each other.

Example: after `#bp.client.aliases.add k kill %1`, the line `k orc` is sent as `kill orc`.

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
| `#bp.client.aliases.add [-g GROUP] [-d] <name> <expansion...>` | Add an alias or replace one. The expansion is the rest of the line. `-g` sets the group, `-d` adds it disabled. The command is not named `set` because every plugin already has a `set` command for its own settings. |
| `#bp.client.aliases.remove <name>` | Remove an alias. |
| `#bp.client.aliases.list [match]` | List aliases, optionally only names containing `match`. |
| `#bp.client.aliases.enable [name] [-g GROUP]` | Enable an alias, or a group. Give exactly one of the two. |
| `#bp.client.aliases.disable [name] [-g GROUP]` | Disable an alias, or a group. Give exactly one of the two. |
| `#bp.client.aliases.show <name>` | Show the expansion, group, enabled state and the hits this session. |

An alias is active only when it and its group are enabled. A group that was never disabled is enabled.

## API

| API | Returns |
|-----|---------|
| `plugins.client.aliases:alias.add(name, expansion, group="", enabled=True)` | `True`, or `False` for a bad name, expansion or group |
| `plugins.client.aliases:alias.remove(name)` | `True`, or `False` when not defined |
| `plugins.client.aliases:alias.get(name)` | a copy with `expansion`, `group` and `enabled`, or `None` |
| `plugins.client.aliases:alias.exists(name)` | `bool` |
| `plugins.client.aliases:alias.list()` | a copy, name to alias |
| `plugins.client.aliases:alias.enabled.set(name, enabled)` | `True`, or `False` when not defined |
| `plugins.client.aliases:alias.is.enabled(name)` | `True` only when the alias and its group are enabled |
| `plugins.client.aliases:alias.group.enabled.set(group, enabled)` | how many aliases are in the group |
| `plugins.client.aliases:alias.group.is.enabled(group)` | `bool` |
| `plugins.client.aliases:alias.expansion.is.resent(line)` | `bool`: whether the aliases at the start of the line, following a chain, expand to something that is re-sent (it contains the separator or starts with the command prefix). Session hits are not counted. |

## Where expansion happens

The plugin listens to `ev_to_mud_data_modify` at priority 55, after the commands plugin (priority 50) and before variables (priority 60). See [ADR-0017](../decisions/0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md), [ADR-0016](../decisions/0016-user-variables-expand-name-references-on-the-input-path.md) and the [data flow](../claude/data_flow.md).
