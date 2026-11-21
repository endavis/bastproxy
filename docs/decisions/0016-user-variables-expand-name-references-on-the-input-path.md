---
title: "ADR-0016: User variables expand %{name} references on the input path"
description: User variables are %{name} references expanded in one pass on ev_to_mud_data_modify at priority 60, with an API for aliases, actions and loop.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0016: User variables expand %{name} references on the input path

## Status

Accepted

## Context

Issue #592 asks for user variables that aliases (#708), actions (#709) and loop (#711) can use. They need one reference syntax, one place where it is expanded and one API to call, so the three plugins do not each pick their own. TinTin++, the client used for live checks, expands `$var` and `&var` in typed input itself, and `@` is the colour-code prefix (ADR-0008).

## Decision

- A reference is `%{name}`, with a name matching `[A-Za-z_][A-Za-z0-9_]*`, case-sensitive. `%%{name}` is the escape and becomes the literal `%{name}`. An undefined reference stays as typed.
- Expansion is a single `re.sub` pass, so a value containing `%{other}` is not expanded again.
- The new plugin `plugins.client.variables` expands on `ev_to_mud_data_modify` at priority 60, after the commands plugin (50). The command history and antispam store the line as typed, and a `!` rerun expands against current values. A plugin that re-sends lines through `command.line.run` gets expansion on the new lines.
- Lines that start with the command prefix, lines with `send` false, lines with `mask_log` and lines that are not I/O are not expanded. Commands that define aliases, actions and loops therefore store references literally and expand them when they run.
- The expansion API is `plugins.client.variables:variable.reference.to.value(text)`, named with ADR-0004's conversion form, so ADR-0004 is not amended. The other APIs are `variable.get`, `variable.set`, `variable.remove`, `variable.exists` and `variable.list`.
- `variable.set` refuses a value with CR or LF, so a variable cannot add MUD lines. Values persist in a `PersistentDict`.

## Rationale

Braces make an accidental match in ordinary text such as "50% off" almost impossible and let a reference sit next to text. Hooking the event, not `execute_line`, covers typed input and `command.line.run` with one callback and avoids expanding twice, which would undo the escape. Priority 60 keeps the history free of expanded values.

## Related Issues

- Issue #707: add user variables expanded on the input path
- Issue #592: user variables

## Related Documentation

- [Variables](../client/variables.md)
- [Data flow](../claude/data_flow.md)
