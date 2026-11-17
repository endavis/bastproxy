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
- `@x` alone is not a code. The reset in `CONVERTCOLORS` is still used by `ansicode.to.colorcode` (see below).

## Building on the tokenizer

| API | Rule |
|---|---|
| `colorcode.to.tokens` | `(raw, visible)` pairs, one per token. The only way another plugin reaches the tokenizer. |
| `colorcode.strip` | Joins the visible text of `TEXT` and `ESCAPE` tokens. SGR sequences go too. |
| `ansicode.strip` | Removes every `SGR` sequence with the tokenizer module's SGR pattern alone, so an `@` before an escape cannot hide it. Everything else is kept as written. |
| `colorcode.to.ansicode` | Each code emits its own sequence in place. A code with no visible text after it is dropped. One `ESC [0m` closes the string if any sequence was emitted. A lowercase colour other than `@w` appends the active xterm background (`;48;5;N`), because `0;3x` clears it. `@w` is the general reset: it clears the background, and later codes do not bring it back. |
| `colorcode.is.valid` | The string is exactly one `COLOR`, `XTERM_FG` or `XTERM_BG` token. |
| `colorcode.to.html` | Foreground and background share one span; `@w`, `@D` and no colour give no foreground; `@w` also clears the background; colours reset on each line. |
| `color.length.difference.get` | `len(text)` minus the length of the visible text. |
| `ansicode.to.colorcode` | An `SGR` with 1 to 3 numeric parameters is looked up in `CONVERTANSI`; any other `SGR` is dropped with a debug log. It matches only SGR sequences (the same pattern as `ansicode.strip`), and the lookup is cached per parameter string, because every MUD line goes through it. |

`colorcode.escape` is a plain string replacement and defines no syntax.

## Other plugins

A plugin never imports another plugin. The utils plugin gets the tokenizer through `plugins.core.colors:colorcode.to.tokens`: `table.format` looks it up once per call and passes it to `wrap_cell`, which takes its widths from the `visible` field. See [ADR-0008](../decisions/0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md).

## Left for later

- `ansicode.to.colorcode` keeps today's lookup. A reset code written in `@` syntax and per-parameter SGR handling (CA-1 and CA-2) are #533.
- Display width of wide characters is #528.
