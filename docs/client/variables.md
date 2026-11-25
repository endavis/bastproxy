---
title: Variables
description: Store named values and use them in the lines you type with %{name} references
audience:
  - users
  - contributors
tags:
  - client
  - variables
---

# Variables

The `plugins.client.variables` plugin stores named string values and expands `%{name}` references in the lines a client sends to the MUD. The values are saved in `variables.txt` in the plugin's data directory and survive a restart.

## Syntax

- A reference is `%{name}`. A name is letters, digits and underscores, does not start with a digit, and is case-sensitive.
- `%%{name}` is an escape: it is sent as the literal `%{name}`. Only a doubled `%` directly before a valid `{name}` is touched, so `100%%` and `%%{ x` are sent as typed.
- A reference to an undefined variable stays as typed.
- Matched text an [action](actions.md) puts into a `#bp` command has its `%{` escaped for a command that expands, so it is never read as a variable (#816). A literal command gets it unchanged.
- Expansion is a single pass. A value that contains `%{other}` is sent as is, so a variable cannot loop.

Example: after `#bp.client.variables.add target orc`, the line `kill %{target}` is sent as `kill orc`.

## Lines that are not expanded

- Lines that start (after leading spaces) with the command prefix, in any case, are not expanded as a line. Their arguments are expanded as described in [Command arguments](#command-arguments).
- Lines that will not be sent to the MUD.
- Lines typed with echo off (such as a password), which can contain `%{`.
- Lines that are not I/O lines.

Input is split on the command separator before expansion, so a `|` inside a value is sent as is and does not split the line. `variable.set` refuses a value that contains CR or LF, so a variable cannot add MUD lines.

## Command arguments

The arguments of a `#bp` command are expanded before the command parses them, so `#bp.client.mapper.goto %{target}` goes to the value of `target`. The command name is not expanded.

- These commands keep their arguments literal: every command of the variables, aliases, actions and substitutes plugins, and `loop.run`. They store a template or pattern as typed and expand it when it runs. `loop.run` has to stay literal: it re-sends its template, which is expanded on each pass, and expanding it twice would undo the `%%{` escape.
- Every other command expands, including the `core` commands, `set` and the mapper. To pass a literal `%{x}` to one of them, type `%%{x}`.
- A reference to an undefined variable stays as typed.
- The history stores the line as typed, and a `!` rerun expands against the current values.
- A line typed with echo off is not expanded.
- The expanded arguments count against the argument length limit. A line that goes over it is refused with "arguments too long" and is not recorded in the history.

## Commands

| Command | Does |
|---------|------|
| `#bp.client.variables.add [-o] <name> <value...>` | Add a variable. An existing name is refused unless `-o` (`--overwrite`) is given, so changing a value needs `-o`. The value is the rest of the line. The command is not named `set` because every plugin already has a `set` command for its own settings. |
| `#bp.client.variables.remove <name>` | Remove a variable. |
| `#bp.client.variables.list [match]` | List variables, optionally only names containing `match`. |

Typing only `#bp.client.variables` runs `list` (the plugin's default command, #778).

## API

| API | Returns |
|-----|---------|
| `plugins.client.variables:variable.get(name)` | the value, or `None` |
| `plugins.client.variables:variable.set(name, value)` | `True`, or `False` for a bad name, a non-string value or a value with CR or LF |
| `plugins.client.variables:variable.remove(name)` | `True`, or `False` when not defined |
| `plugins.client.variables:variable.exists(name)` | `bool` |
| `plugins.client.variables:variable.list()` | a copy, name to value |
| `plugins.client.variables:variable.reference.to.value(text)` | text with references expanded |

## Where expansion happens

The plugin listens to `ev_to_mud_data_modify` at priority 60, after the commands plugin (priority 50, lower runs first), for lines that are not commands. For `#bp` commands it listens to `ev_plugins.core.commands_args_modify`, which the commands plugin raises before it parses the arguments of a command that is not `literal_args`. The command history therefore stores the line as typed, and a `!` rerun expands against the current values. A plugin that rewrites a line in place at a priority below 60 gets its result expanded. A plugin that re-sends lines through `plugins.core.commands:command.line.run` gets expansion on the new lines. See [ADR-0016](../decisions/0016-user-variables-expand-name-references-on-the-input-path.md) and the [data flow](../claude/data_flow.md).
