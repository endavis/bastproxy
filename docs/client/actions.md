---
title: Actions
description: Run commands when a line of MUD output matches a regex, with %1 to %9, %* and %<name> references
audience:
  - users
  - contributors
tags:
  - client
  - actions
---

# Actions

The `plugins.client.actions` plugin stores named actions. Each action has a regex and a command. When a line of MUD output matches the regex, the command runs. Actions are saved in `actions.txt` and group state in `groups.txt`, in the plugin's data directory, and survive a restart. Each action owns one trigger in [triggers](../claude/triggers_system.md), named after the action.

## Syntax

- The regex matches from the start of the line, as every trigger does. Use `.*` to match anywhere. It is matched against the line without colour codes, unless the action was added with `-c`.
- `%1` to `%9` are the regex groups by position, named groups included. A group that did not take part is empty. Digits are read one at a time, so `%10` is `%1` followed by `0`.
- `%*` is the whole line, without colour codes.
- `%<name>` is the named group `(?P<name>...)`. `%{name}` is not used because it is the [variables](variables.md) syntax.
- `%%1`, `%%*` and `%%<name>` are escapes: they run as the literal `%1`, `%*` and `%<name>`.
- Substitution is a single pass, so matched text that contains `%2` is not substituted again. Nothing is appended when a command has no reference.
- `action.add` refuses a command that references a group the regex does not have.

Example: after `#bp.client.actions.add dead '^(\w+) is dead' kill %1`, the line `orc is dead` runs `kill orc`.

## Quoting the regex

The regex is one argument and is split like a shell word. Use single quotes, which keep backslashes: `'^(\w+) is dead'`. Inside double quotes `\w` survives but `\\` becomes `\`.

## Typing `|`

A typed line is split on a single command separator before the command runs, so type each `|` doubled, in the regex and in the command. The `add` command stores it single: `'^(a||b) (\w+)'` stores `^(a|b) (\w+)`, and `\||` stores `\|`, a literal pipe. The `action.add` API stores both exactly as passed.

Example: `#bp.client.actions.add dead '^(\w+) is dead' stand||kill %1`.

## Variables in commands

Each part of the command goes through the input path, so `%{name}` in a command is expanded by the [variables](variables.md) plugin, and `%%{name}` reaches the MUD as `%{name}`.

## How matched text is escaped

MUD output is untrusted, so a template is trusted and a matched value is data.

- The stored command is split on the separator into parts. Each part runs on its own, in order.
- Every value loses CR and LF and has the separator doubled, so it never splits a line. A doubled separator reaches the MUD as one `|`.
- In a part that goes to the MUD, `@` in a value becomes `@@`, and any `%{` with a character from a value becomes `%%{`, including one formed where a value meets the command's text (a value ending in `%` before `{`). So a value is not a variable and not a colour code. A `%{name}` you write in the command is still expanded.
- In a part that starts with the command prefix, each value is quoted as one argument, so it cannot add arguments. Do not put quotes around a reference in such a part. A separator inside a value reaches the command doubled. If a value starts with `-`, the command would read it as an option, so nothing runs and a warning names the action.
- If a part that goes to the MUD would start with the command prefix after substitution, nothing runs and a warning names the action. A template part that starts with the prefix is allowed.
- Aliases expand the first word of a MUD-bound part. If that word comes from a value and is an enabled alias, nothing runs and a warning names the action. An alias you write as the first word of the command runs as usual.
- An alias you write as the first word runs as usual, unless the part holds matched text and the alias's expansion is re-sent: it contains the separator or starts with the command prefix, directly or through a chain of aliases. A re-sent expansion splits the matched text and passes it to proxy commands without the quoting above, so nothing runs and a warning names the action. `k %1`, with `k` = `kill %1`, runs; `n %1`, with `n` = `#bp.client.variables.add note %*`, does not. Write the `#bp` command in the action itself instead, where the matched text is quoted.

## Multi-command order

Parts run through `command.line.run`. A part that is itself re-sent can reach the MUD before the others, as described in [Aliases](aliases.md#multi-command-and-bp-expansions). This is tracked in #714.

## Echo loops

An action's command is not an internal line, so the trigger echo skip does not cover it. If the MUD echoes the command in a form that matches the action's own regex, the action fires again through the MUD. Write a regex that does not match what the command sends.

## Regex time limit

A match that takes longer than the triggers time limit counts as no match and is logged once per trigger (#697).

## Commands

| Command | Does |
|---------|------|
| `#bp.client.actions.add [-g GROUP] [-d] [-c] <name> <regex> <command...>` | Add an action or replace one. `-g` sets the group, `-d` adds it disabled, `-c` matches the line with colour codes. A name is letters, digits and underscores. |
| `#bp.client.actions.remove <name>` | Remove an action and its trigger. |
| `#bp.client.actions.list [match]` | List actions, optionally only names containing `match`. |
| `#bp.client.actions.enable [name] [-g GROUP]` | Enable an action, or a group. Give exactly one of the two. |
| `#bp.client.actions.disable [name] [-g GROUP]` | Disable an action, or a group. Give exactly one of the two. |
| `#bp.client.actions.show <name>` | Show the regex, command, group, states and the hits this session and in the trigger. |

An action is active only when it and its group are enabled. A group that was never disabled is enabled. Groups are kept by this plugin, not passed to triggers, whose group names are shared by every plugin.

## API

| API | Returns |
|-----|---------|
| `plugins.client.actions:action.add(name, regex_text, command, group="", enabled=True, matchcolor=False)` | `True`, or `False` for a bad name, regex, command or group |
| `plugins.client.actions:action.remove(name)` | `True`, or `False` when not defined |
| `plugins.client.actions:action.get(name)` | a copy with `regex`, `command`, `group`, `enabled` and `matchcolor`, or `None` |
| `plugins.client.actions:action.exists(name)` | `bool` |
| `plugins.client.actions:action.list()` | a copy, name to action |
| `plugins.client.actions:action.enabled.set(name, enabled)` | `True`, or `False` when not defined |
| `plugins.client.actions:action.is.enabled(name)` | `True` only when the action and its group are enabled |
| `plugins.client.actions:action.group.enabled.set(group, enabled)` | how many actions are in the group |
| `plugins.client.actions:action.group.is.enabled(group)` | `bool` |

## Design

See [ADR-0018](../decisions/0018-user-actions-substitute-trigger-groups-into-commands-and-escape-matched-text.md), [ADR-0017](../decisions/0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md) and [ADR-0016](../decisions/0016-user-variables-expand-name-references-on-the-input-path.md).
