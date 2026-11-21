---
title: "ADR-0017: User aliases expand the first word on the input path at priority 55"
description: Aliases expand the first word of client input at priority 55, in place or by re-sending, with %1-%9 and %* arguments and a depth bound of 10.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0017: User aliases expand the first word on the input path at priority 55

## Status

Accepted

## Context

Issue #708 asks for user aliases. Actions (#709) and loop (#711) need the same argument syntax, and ADR-0016 already fixed where variables expand (priority 60, after commands). An alias must run after the commands plugin (50), so the history holds the typed line, and before variables (60), so its expansion gets variables expanded. `ProcessDataToMud` splits a line on the command separator before it raises `ev_to_mud_data_modify`, and sends every line only after the event, so an in-place rewrite cannot add lines or run `#bp` commands.

## Decision

- The plugin `plugins.client.aliases` matches the first word of a client line (left-stripped, exact, case-sensitive) on `ev_to_mud_data_modify` at priority 55.
- An expansion with no separator and not starting with the command prefix rewrites the line in place. An alias at the start of the result is resolved in the same callback.
- An expansion that contains the command separator or starts with the command prefix is re-sent: the typed line gets `send = False` and the expansion goes through `plugins.core.commands:command.line.run(text, show_in_history=False)`. The separator split, `#bp` commands and alias matching then apply to each part, and variables expands the new lines at 60. The history keeps the typed line only.
- The `add` command stores a doubled separator (`||`) as a single one, because a typed line is split on a single separator before the command runs. The `alias.add` API stores the expansion as passed.
- Arguments are `%1` to `%9` (whitespace-separated words, a missing one is empty) and `%*` (the rest of the line, stripped). `%%1` and `%%*` give the literal text. Substitution is one `re.sub` pass, so an argument is not substituted again. With no reference in the expansion, typed arguments are appended after a space. Digits are read one at a time, so `%10` is `%1` followed by `0`. Actions and loop reuse this syntax.
- Expansion is bounded by `MAX_DEPTH = 10`, counted across in-place chains and nested re-sends. Past it the line is not sent, a WARNING names the alias, and the client is told.
- The plugin does not expand variables itself, so variables is an optional plugin and there is one expansion pass.
- Lines starting with the command prefix, lines with `send` false, masked lines and non-I/O lines are not expanded.

## Rationale

Priority 55 keeps ADR-0016's contract as written: the history holds the typed line and a rewrite below 60 is expanded. Rewriting in place keeps the order of lines for the common single-line alias. Only re-sending can split on the separator and run `#bp` commands, because the commands plugin has already run. Re-sent lines are sent in the alias line's place by `ProcessDataToMud` (#714), so in `stand|port x` the `port` lines follow `stand`. See [Data Flow](../claude/data_flow.md).

## Related Issues

- Issue #708: add user aliases
- Issue #711: add a loop command (reads %1 as its counter)
- Issue #592: user variables, aliases, actions and loop

## Related Documentation

- [Aliases](../client/aliases.md)
- [Loop](../client/loop.md)
- [Data flow](../claude/data_flow.md)
