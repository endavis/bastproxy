---
title: "ADR-0018: User actions substitute trigger groups into commands and escape matched text"
description: Actions put trigger groups into commands as %1-%9, %* and %<name>, and escape matched MUD text per part.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0018: User actions substitute trigger groups into commands and escape matched text

## Status

Accepted

## Context

Issue #709 asks for user actions: commands that run when a line of MUD output matches a regex. ADR-0017 fixed the `%1`-`%9` and `%*` syntax for aliases and said actions reuse it. `plugins.core.triggers` already matches lines and raises an event per match, but the event has `matches` (named groups only) and no numbered groups. MUD output is untrusted: a matched value is put into a command, and a value must not be able to run a proxy command, split a line, expand a variable or add a colour code.

## Decision

- The plugin `plugins.client.actions` stores actions and gives each one a trigger in `plugins.core.triggers`, named after the action and owned by the plugin. Persistence, groups, enable and disable, `show` and `list` follow `plugins.client.aliases`.
- The trigger event gains `groups`, the raw `match.groups()` tuple, with `None` for a group that did not take part. `matches` is unchanged.
- References are `%1`-`%9` (numbered groups, so named groups count by position), `%*` (the whole line without colour codes) and `%<name>` (a named group). `%{name}` is not used because it is the variables syntax. `%%` before a reference makes it literal. Substitution is one pass and a group that did not take part is empty. `action.add` refuses a command that references a group the regex lacks.
- The stored command is split on the command separator into trusted template parts. Each part runs in order through `plugins.core.commands:command.line.run(part, show_in_history=False)`.
- Matched text is escaped per part. Every value loses CR and LF and has the separator doubled. In a part that goes to the MUD a value has `@` turned into `@@`, and every `%{` with a character from a value, including one formed at a value's edge, becomes `%%{`. In a part that starts with the command prefix a value is `shlex.quote`d, so it is one argument. A firing runs nothing, and a WARNING names the action, when matched text would choose what runs: a MUD part would start with the command prefix after substitution, the first word of a MUD part comes from a value and is an enabled alias (checked through `plugins.client.aliases:alias.is.enabled` when that API exists), or a value in a command part starts with `-`.
- The `add` command stores a doubled separator in the regex and in the command as a single one, as aliases do. The `action.add` API stores both as passed.
- The action group is kept by the plugin and not passed to triggers, whose group names are one global namespace. The trigger gets the effective state (action and group enabled).

## Rationale

Re-matching in the plugin would duplicate the trigger plugin's timeout and colour handling, so the event carries the groups instead. Escaping by the kind of part keeps each template part trusted and each value data. An alias can still expand a value at the start of a MUD part, because aliases are user-authored; this is documented, not blocked. Ordering of several parts follows `command.line.run` (issue #714).

## Related Issues

- Issue #709: add user actions
- Issue #592: user variables, aliases, actions and loop

## Related Documentation

- [Actions](../client/actions.md)
- [Triggers system](../claude/triggers_system.md)
- [ADR-0017](0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md)
