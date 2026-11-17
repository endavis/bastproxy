---
title: "ADR-0009: Display width is measured with wcwidth in one framework helper"
description: Display width is the wcwidth of visible text, measured in one framework helper that plugins and argp share; control characters count zero and wrapping works on graphemes.
date: 2026-11-17
audience:
  - contributors
tags:
  - adr
---

# ADR-0009: Display width is measured with wcwidth in one framework helper

## Status

Accepted

## Context

Tables, centred titles, line caps, the line-length calculation and help text sized their output with `len()`. `len()` counts code points, so CJK and emoji (two columns each) overran their column and combining marks and joiners (zero columns) left gaps. Issue #528 asks for display width. Width is needed by the colors plugin, the utils plugin, the proxy plugin and `src/bastproxy/libs/argp.py`. Plugins must not import each other, and framework code cannot reach a plugin.

## Decision

1. `wcwidth>=0.9.4` is a runtime dependency.
2. Display width is measured in one framework module, `src/bastproxy/libs/textwidth.py`, which every caller can import. It has two functions: `display_width(text)` and `text_units(text)`.
3. The helper measures visible text only. Each caller strips colour codes as it did before (through the colors API or the tokenizer) and passes the result in. The tokenizer still decides what is visible ([ADR-0008](0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md)); no colors API for width is added.
4. The width is never negative. Control characters and terminal escape sequences count as zero columns (`wcwidth.width(..., control_codes="ignore")`), never `wcswidth`, which returns -1 for a control character. Printable ASCII skips wcwidth.
5. `text_units` splits text into graphemes (one terminal escape sequence is one zero-width unit). `wrap_cell` wraps on these units with a prefix sum of their widths, so a combining mark stays with its base character and a joined emoji is never cut. A line always takes at least one unit, so a grapheme wider than the column gets a line of its own.
6. `fit_column_widths` takes an optional per-column floor (`unit_mins`, the widest grapheme of the column), so a table column is never narrower than one wide character and the table grows instead.
7. `src/bastproxy/libs/argp.py` wraps help text with `wcwidth.wrap` instead of `textwrap`. Help text still holds `@` codes at that point, as before, so they count as visible there.

The helper and its rules are described in [Colour System](../claude/colors_system.md#display-width). Implemented by #528.

## Rationale

- **One helper:** every width path then agrees, and a change to the rules is made once.
- **In `libs/`:** a lib is importable by plugins and argp alike, with no cross-plugin import. Width of plain text has nothing to do with the `@` syntax, so it does not belong in the colors tokenizer.
- **Control characters count zero:** a width must never be negative or subtract from the width of its neighbours, and a tab or bell takes no column of its own in the layout.
- **Graphemes, not code points:** cutting inside a cluster would show a broken character.
- **`wcwidth.wrap` in argp:** it measures display columns and keeps the textwrap behaviour for ASCII; the only difference found on a random corpus is that it drops a trailing space at a line end.

## Consequences

- A new runtime dependency, `wcwidth`.
- Printable ASCII output is unchanged. An ASCII control character in a measured string now counts 0 columns instead of 1, and argp help lines may lose a trailing space.
- A grapheme split across colour-code tokens (a base character, a colour code, then a combining mark) is measured as two units; the mark has zero width.
- argp does not know `@` codes, so help lines that hold them can come out short but never overrun. Making the wrap `@`-aware is separate work.
- New code that measures visible text calls `display_width`, and never `len()` of text that may hold wide characters.

## Related Issues

- Issue #528: measure display width with wcwidth for wide and combining characters

## Related Documentation

- [Colour System](../claude/colors_system.md)
- [Command System](../claude/command_system.md)
- [ADR-0008](0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md)
