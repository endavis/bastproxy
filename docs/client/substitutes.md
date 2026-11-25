---
title: Substitutes
description: Rewrite text in MUD output before it reaches the client, keeping colour, with plain or regex matching
audience:
  - users
  - contributors
tags:
  - client
  - substitutes
---

# Substitutes

The `plugins.client.substitutes` plugin stores named substitutions. Each has a pattern and a replacement. Every line of MUD output is searched for the pattern, and each match is replaced before the line reaches the client. Substitutions are saved in `substitutes.txt` in the plugin's data directory and survive a restart. See [ADR-0019](../decisions/0019-user-substitutions-rewrite-mud-lines-after-triggers-and-keep-colour-codes.md).

## Commands

| Command | What it does |
| :--- | :--- |
| `#bp.client.substitutes.add [-r] [-o] NAME PATTERN REPLACEMENT...` | Add a substitution. An existing name is refused unless `-o` (`--overwrite`) is given. |
| `#bp.client.substitutes.remove NAME` | Remove one. |
| `#bp.client.substitutes.list [MATCH]` | List them, optionally only names containing `MATCH`. Regex ones are tagged `(regex)`. |
| `#bp.client.substitutes.clear` | Remove every substitution and report how many. |

Examples:

```text
#bp.client.substitutes.add orc 'orc' goblin
#bp.client.substitutes.add -r arrive '^(\w+) arrives' '@G%1@w is here'
#bp.client.substitutes.add quiet 'You are hungry.' ''
```

Quote a pattern or replacement that holds spaces or regex characters with single quotes. A replacement of `''` deletes the matched text. The command separator splits a typed line, so type `||` for a literal `|`.

## Plain and regex matching

- A plain pattern is a case-sensitive substring. Every occurrence in the line is replaced. `%1` is literal text in a plain replacement.
- With `-r` the pattern is a regex, searched anywhere in the line, every non-overlapping match. The replacement may use `%1` to `%9` (groups by position) and `%<name>` (the named group `(?P<name>...)`). `%%1` is a literal `%1`. A group that did not take part is empty. `%*` is not supported. `add` refuses a reference to a group the regex lacks.
- Matching runs on the text the user sees, without colour codes and without the line ending.
- A match of zero width, such as `x*` on a line without `x`, is skipped.
- A regex that takes longer than 0.05 seconds on a line is skipped for that line, with a warning logged once per substitution.
- Substitutions apply in name order, each one on the output of the one before.

## Colour

- The replacement is your own text: colour codes in it work and `@@` is a literal `@`.
- Text matched by a group and inserted with `%1` is literal, never a colour code, and takes the colour of the replacement, not its original colour.
- When the replacement has no colour codes, the colour after the replaced text is what it was before. A colour change inside the matched text moves to just after the replacement.
- When the replacement has colour codes, the colour that was active at the end of the matched text is restored after it.

## Triggers and actions

Substitutions run after [triggers](../claude/triggers_system.md) (priority 60, triggers are 50). A substitution never makes an [action](actions.md) fire or stops one, and `%*` in an action is the original line.

## Limits

- A line with MXP markup is not substituted, because rewriting it would drop its links.
- Internal lines and lines a trigger gagged are not substituted.
- There are no groups and no enable or disable; remove a substitution to stop it.
