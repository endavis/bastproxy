---
title: "ADR-0019: User substitutions rewrite MUD lines after triggers and keep colour codes"
description: Substitutions rewrite MUD lines at priority 60, after triggers, rebuilding colour codes token by token.
date: 2026-11-21
audience:
  - contributors
tags:
  - adr
---

# ADR-0019: User substitutions rewrite MUD lines after triggers and keep colour codes

## Status

Accepted

## Context

Issue #710 asks for user substitutions: rewrite text in MUD output before it reaches the client, the way the legacy `ssub` did. The output must keep its colour, and MUD text must never be read as a colour code. `plugins.core.triggers` is the existing matching mechanism, but a trigger matches only from the start of the line, fires at most once per line and its callback has no spans into the colour-coded text. ADR-0018 fixed the `%1`-`%9` and `%<name>` reference syntax and the timeout handling of #697 is already in the triggers plugin.

## Decision

- The plugin `plugins.client.substitutes` stores named substitutions (`pattern`, `replacement`, `regex`) in `substitutes.txt`. It does not use triggers. It registers a callback on `ev_to_client_data_modify` at priority 60, so it runs after triggers (50) and line waiters (40). Triggers and actions therefore see the original MUD text, and a substitution only changes what is displayed.
- A line is skipped when it is internal, not an I/O line, not a `str`, gagged (`send` is False) or has an `mxp_mode`. `colorcoded` strips MXP markup, so rewriting an MXP line would drop its links. This is a documented limitation.
- Matching is a plain, case-sensitive substring by default and replaces every occurrence. With `-r` the pattern is a `regex` module regex, searched with `finditer(..., timeout=0.05)` (#697). A timeout skips that substitution for the line and logs a warning once. Zero-width matches are skipped. Matching runs on the visible text, without colour codes and without the trailing line ending.
- Substitutions apply in sorted name order, each on the output of the one before.
- Colour is kept at token level. The line's colour-coded form is split by `plugins.core.colors:colorcode.to.tokens`. Text outside a match keeps its raw form. Colour codes inside a match move after a replacement that has none. A replacement with colour codes drops the inner codes and is followed by a restore (`@w` plus the foreground and background active at the match end). The result goes back through `colorcode.to.ansicode`, so `line.line` stays ANSI like every other MUD line.
- The replacement is the user's own text: colour codes are interpreted and `@@` is a literal `@`. In regex mode `%1`-`%9` and `%<name>` insert matched text, `%%` before a reference makes it literal, a group that did not take part is empty and `%*` is not supported. Matched text has `@` doubled, so MUD text is never read as a colour code. `substitute.add` refuses a reference to a group the regex lacks, a bad regex, an empty pattern and a line break in the pattern or replacement. Nothing is ever run.
- The commands are `add`, `remove`, `list` and `clear`. There are no groups and no enable or disable.

## Rationale

A trigger cannot find every occurrence anywhere in a line or give spans, which colour preservation needs, so a direct event callback fits. Running after triggers keeps actions reliable: a substitution can neither fire an action nor stop one. Token-level rebuilding is the only way to keep colour across a replaced span without re-interpreting MUD text. Skipping MXP lines is preferred to silently losing their markup.

## Related Issues

- Issue #710: add substitutions of MUD output text
- Issue #592: user variables, aliases, actions and loop

## Related Documentation

- [Substitutes](../client/substitutes.md)
- [Data flow](../claude/data_flow.md)
- [ADR-0007](0007-triggers-match-each-triggers-own-regex-in-priority-order.md)
- [ADR-0018](0018-user-actions-substitute-trigger-groups-into-commands-and-escape-matched-text.md)
