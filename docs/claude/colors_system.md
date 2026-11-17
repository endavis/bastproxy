---
title: Colour System
description: The colour-code syntax, the one tokenizer that defines it, and how conversion, stripping, validation, html and width are built on it
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - colors
---

# Colour System

## Overview

The colors plugin (`src/bastproxy/plugins/core/colors/`) converts between bastproxy's `@` colour codes and ANSI SGR sequences, strips both, validates codes and renders html. All of it is built on one tokenizer, `src/bastproxy/plugins/core/colors/libs/_tokenizer.py`, which is the only definition of the syntax. The audit that led to this design is in [Colour System Findings](colors_findings.md).

## The syntax

The tokenizer scans the string once, left to right, with one compiled pattern. The first alternative that matches wins.

| Order | Text | Token kind | Visible |
|---|---|---|---|
| 1 | `ESC [ digits and ; m` | `SGR` | nothing |
| 2 | `@@` | `ESCAPE` | `@` |
| 3 | `@-` | `ESCAPE` | `~` |
| 4 | `@x` or `@z` and 1 to 3 digits, 0 to 255 | `XTERM_FG` / `XTERM_BG` | nothing |
| 4 | the same with a value above 255 | `INVALID` | nothing |
| 5 | `@x` or `@z` with no digit | `INVALID` (the next character is kept) | nothing |
| 6 | `@` and one of `krgybmcwDRGYBMCW` | `COLOR` | nothing |
| 7 | `@` and any other character except `ESC`, newline included | `INVALID` (both characters dropped) | nothing |
| 8 | `@` at the end of the string or before `ESC` | `TEXT` | `@` |
| 9 | any other run of text, or a lone `ESC` | `TEXT` | the text |

Notes:

- Digits are kept as written (`@x075` stays `075`), and at most three are read, so `@x0751` is `@x075` followed by the text `1`.
- A non-SGR escape such as `ESC [2J` is plain text.
- `"".join(token.raw for token in tokenize(s)) == s` always holds.
- `@x` alone is not a code. `ansicode.to.colorcode` does not use `CONVERTCOLORS['x']`; its reset is `@w`.

## Building on the tokenizer

| API | Rule |
|---|---|
| `colorcode.to.tokens` | `(raw, visible)` pairs, one per token. The only way another plugin reaches the tokenizer. |
| `colorcode.strip` | Joins the visible text of `TEXT` and `ESCAPE` tokens. SGR sequences go too. |
| `ansicode.strip` | Removes every `SGR` sequence with the tokenizer module's SGR pattern alone, so an `@` before an escape cannot hide it. Everything else is kept as written. |
| `colorcode.to.ansicode` | Each code emits its own sequence in place. A code with no visible text after it is dropped. One `ESC [0m` closes the string if any sequence was emitted. A lowercase colour other than `@w` appends the active xterm background (`;48;5;N`), because `0;3x` clears it. `@w` is the general reset: it clears the background, and later codes do not bring it back. |
| `colorcode.is.valid` | The string is exactly one `COLOR`, `XTERM_FG` or `XTERM_BG` token. |
| `colorcode.to.html` | Foreground and background share one span; `@w`, `@D` and no colour give no foreground; `@w` also clears the background; colours reset on each line. |
| `color.length.difference.get` | `len(text)` minus the display width of the visible text: the offset to add to a display width to get a `str.ljust` or format width. |
| `ansicode.to.colorcode` | Follows SGR state across one line and writes `@` codes only before visible text (see below). Only SGR sequences are read (the tokenizer's `split_sgr`); the parameter rules are in `src/bastproxy/plugins/core/colors/libs/_sgr.py`. A literal `@` in the text is written as `@@` (the tokenizer's `escape_at`, also used by `colorcode.escape`), so `colorcode.strip` of the result gives back `ansicode.strip` of the input. A colour-matching trigger that matches `@` in MUD text writes `@@` in its regex. Parsing and diffing are cached, because every MUD line can go through it. |

### `ansicode.to.colorcode` rules

The state is foreground (default, basic, bright or xterm), bold and background. Each parameter is applied in order, and an empty parameter is `0`.

| Parameter | Effect |
|---|---|
| `0`, empty | Reset all |
| `1` / `22` | Bold on / off |
| `30-37`, `90-97` | Basic / bright foreground |
| `39` / `49` | Default foreground / background |
| `40-47`, `100-107` | Background 0-7 / 8-15 |
| `38;5;n`, `48;5;n` | Xterm foreground / background (`n` up to 255) |
| `38;2;r;g;b`, `48;2;r;g;b` | The nearest xterm colour in 16-255 (the 6x6x6 cube or the 24 greys, by squared RGB distance) |
| Anything else | Ignored; there is no `@` code for it |

A malformed `38` or `48` stops the parse of that sequence and keeps what came before.

- The foreground code is a lowercase letter, or the uppercase one when bold; bright colours are always uppercase; bold with the default colour is `@W`; xterm is `@x{n}`; the background is `@z{n}`.
- Codes are written only before visible text, from the last state written. A reset (or any change to default) is written as `@w`, which also clears the background, then the foreground, then the background. So `\x1b[1m\x1b[31mx` is `@Rx`, a trailing reset writes nothing, and `\x1b[31mred\x1b[0m plain` is `@rred@w plain`.
- A line-start `\x1b[0;37m` is `@w`, because explicit white differs from the default.
- State starts at the default on every line and is not carried to the next one.

`colorcode.escape` is a plain string replacement and defines no syntax.

## Other plugins

A plugin never imports another plugin. The utils plugin gets the tokenizer through `plugins.core.colors:colorcode.to.tokens`: `table.format` looks it up once per call and passes it to `wrap_cell`, which takes its widths from the `visible` field. The commands plugin passes the same API to `argp.CustomFormatter` for help wrapping. See [ADR-0008](../decisions/0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md).

## Display width

Width is measured in terminal columns, not code points, by `src/bastproxy/libs/textwidth.py`, which is built on `wcwidth` ([ADR-0009](../decisions/0009-display-width-is-measured-with-wcwidth-in-one-framework-helper.md)). It is a framework lib, so plugins and `src/bastproxy/libs/argp.py` share it without importing each other.

- The helper measures visible text. Each caller strips the colour codes first, through `colorcode.strip` or the tokenizer, and passes the result to `display_width`; every colour code counts as zero. A plugin author writes `display_width(strip(text))`.
- The result is never negative. Control characters and terminal escape sequences count as zero columns, so `a\tb` is 2.
- Wide characters (CJK, emoji) take two columns, combining marks and joiners zero, and a ZWJ sequence or flag is one grapheme.
- `text_units` splits text into graphemes with their widths; the widths sum to `display_width`. `wrap_cell` wraps on these units, so a combining mark stays with its base character, a grapheme is never cut, and a line always holds at least one grapheme (a grapheme wider than the column gets its own line). A grapheme split across tokens, such as `e@R` followed by a combining mark, makes the mark a zero-width unit of its own.
- `table.format` gives each column at least the width of its widest grapheme, so the table grows instead of cutting a wide character.
- `src/bastproxy/libs/argp.py` wraps help text with `wcwidth.wrap`. `argp.CustomFormatter` takes an injected `colorcode.to.tokens` callable and wraps the visible text, so `@` codes are zero-width, and the colour in force at a break carries to the continuation line (#542).

## Left for later

- Colour state is per line; a colour that runs over a line break is not carried to the next line.
