---
title: Colour System Analysis and Findings
description: Audit of the colors plugin - its APIs and callers, the colour-code conversion bugs reproduced on main, why they happen, and the recommended single-tokenizer design
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - colors
  - review
---

# Colour System Analysis and Findings

**Date:** 2026-11-17
**Analyzer:** Claude Opus 5.5
**Scope:** The colors plugin in `src/bastproxy/plugins/core/colors/` (`src/bastproxy/plugins/core/colors/plugin/_colors.py`: `ColorsPlugin`,
`fixstring`, `createspan`; `src/bastproxy/plugins/core/colors/libs/_colors.py`: `CONVERTCOLORS`, `CONVERTANSI`, `COLORTABLE`), and the code outside it
that parses colour codes itself (`_CELL_TOKEN` in `src/bastproxy/plugins/core/utils/plugin/_utils.py`). Base commit `c26b915`.

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [How the Plugin Is Built](#how-the-plugin-is-built)
4. [Reproduced Defects](#reproduced-defects)
5. [Root Cause: Five Definitions of the Syntax](#root-cause-five-definitions-of-the-syntax)
6. [Other Observations](#other-observations)
7. [Recommended Design](#recommended-design)
8. [Tracking](#tracking)

---

## Executive Summary

The plugin converts between bastproxy's `@` colour codes and ANSI SGR sequences, strips both, checks codes for
validity and renders HTML. Every conversion is a chain of regex substitutions, with no record of which colour is
active. The `@` code syntax is defined separately in five places, and they disagree.

The defects reproduced on `main` fall into two groups:

- **`@` code output** (#532):
  - a literal `@w` is left in converted and stripped text;
  - `@k` is deleted;
  - a lowercase colour clears the background;
  - colour 256 is accepted as valid.
- **ANSI input** (#533):
  - a mid-line reset is lost;
  - multi-part, bold and bright SGR sequences are dropped;
  - true colour and the bare reset are not stripped.

  Colour-matching triggers read the converted text, so they see the wrong colours.

The recommended fix is one tokenizer that every function uses, with colour state tracked during conversion (#534).
Display width with wcwidth (#528) builds on that tokenizer.

## How This Was Verified

Each defect below was reproduced by calling the plugin's functions directly, with no proxy running. The methods
are unbound methods of `ColorsPlugin`, given a stub `self` whose `api` returns the plugin's own functions:

```python
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin as P


class Stub:
    plugin_id = "p"


s = Stub()
fns = {
    "ansicode.to.string": lambda c, d: P._api_ansicode_to_string(s, c, d),
    "ansicode.strip": lambda t: P._api_ansicode_strip(s, t),
    "colorcode.to.ansicode": lambda t: P._api_colorcode_to_ansicode(s, t),
    "colorcode.strip": lambda t: P._api_colorcode_strip(s, t),
}
s.api = lambda name: fns[name.split(":", 1)[1]]

fns["colorcode.strip"]("mail@@host")  # 'mail@host@w'
```

Every output quoted on this page came from that setup on commit `c26b915`. Run it with `BASTPROXY_HOME` pointing
at an existing directory.

## How the Plugin Is Built

| API | Callers outside the plugin |
|---|---|
| `colorcode.to.ansicode` | `utils` (`string.center.colored`), `NetworkDataLine.color_line` |
| `colorcode.strip` | `utils` (`table.format`, `line.cap`), `proxy` (`line.length.get`) |
| `ansicode.strip` | `utils` (`string.center.colored`), `NetworkDataLine.noansi` |
| `ansicode.to.colorcode` | `NetworkDataLine.colorcoded`, which the triggers plugin reads |
| `colorcode.escape` | `NetworkDataLine.escapecolor` |
| `colorcode.is.valid` | `utils` (`verify_color`) |
| `colorcode.to.html` | none |
| `color.length.difference.get` | none |
| `ansicode.to.string` | none; only the plugin calls it |

The logging plugin's formatter imports `ALLCONVERTCOLORS` from the plugin package directly instead of going
through an API.

`colorcode.strip` works by converting to ANSI with `colorcode.to.ansicode` and then calling `ansicode.strip`.

## Reproduced Defects

### `@` codes to ANSI, and stripping (#532)

| ID | Call | Output | Problem |
|---|---|---|---|
| CO-1 | `colorcode.strip("mail@@host")` | `mail@host@w` | `colorcode.to.ansicode` always appends `@w`. When nothing else in the string is a valid code, its `@(\w)([^@]+)` scan finds no match, and the `@w` is left as text. |
| CO-1 | `colorcode.strip("a@ab")` | `ab@w` | Same cause. |
| CO-2 | `colorcode.to.ansicode("@kblack@w")` | `black@w` | `CONVERTCOLORS` maps `k`, but `fixstring` deletes `@k` as an invalid code. That leaves no other code, so CO-1 applies too. |
| CO-3 | `colorcode.to.ansicode("@z165@rtext")` | `\x1b[48;5;165m\x1b[0;31mtext\x1b[0m` | Lowercase colours are emitted as `0;3x`. The `0` resets every attribute, so the background is lost. |
| CO-4 | `colorcode.is.valid("@x256")` | `True` | The check is `num < 257`, but the xterm palette ends at 255. |

CO-1 shows up in client output whenever a string has no valid code apart from the appended `@w`, for example
text with an escaped `@@`. It also adds two columns to every width that `table.format` and the centring helpers
compute with `colorcode.strip`.

### ANSI to `@` codes, and stripping (#533)

| ID | Call | Output | Problem |
|---|---|---|---|
| CA-1 | `ansicode.to.colorcode("\x1b[31mred\x1b[0m plain")` | `@rred@x plain` | Reset `0` maps to `@x`, which `fixstring` deletes. Converting back gives `\x1b[0;31mred plain\x1b[0m`, so the red runs past the reset. |
| CA-2 | `ansicode.to.colorcode("\x1b[1;37;44mhi")` | `hi` | `CONVERTANSI` has no entry for this combination, so the whole sequence is dropped. |
| CA-2 | `ansicode.to.colorcode("\x1b[1mbold")` | `bold` | Bold on its own has no entry. |
| CA-2 | `ansicode.to.colorcode("\x1b[91mbright")` | `bright` | The bright colours (90–97, 100–107) have no entries. |
| CA-3 | `ansicode.strip("\x1b[38;2;1;2;3mtc\x1b[0m")` | `\x1b[38;2;1;2;3mtc` | `ANSI_COLOR_REGEX` matches one to three numeric parts, so a true-colour sequence is left in. |
| CA-3 | `ansicode.strip("\x1b[mx")` | `\x1b[mx` | The bare reset has no numeric part, so the regex does not match it. |

The triggers plugin matches colour triggers against `NetworkDataLine.colorcoded`
(`src/bastproxy/plugins/core/triggers/plugin/_triggers.py`), which comes from `ansicode.to.colorcode`. A MUD that sends any of
the CA-2 sequences produces `colorcoded` text with the wrong colours or none at all. The `noansi` text keeps
the CA-3 sequences.

## Root Cause: Five Definitions of the Syntax

| Where | What it treats as an `@` code |
|---|---|
| `fixstring` | `@` followed by one of `xzcmyrgbwCMYRGBWD`; anything else after `@` is deleted, which includes `k` |
| `colorcode.to.html` split regex | `@[cmyrgbwCMYRGBWD]` or `@[xz]` with 1–3 digits |
| `colorcode.is.valid` | the same letters, or `@[xz]` with 1–3 digits and a value below 257 |
| `colorcode.to.ansicode` scan | `@` followed by any word character, then text up to the next `@` |
| `utils._CELL_TOKEN` | `@@`, `@[xz]` with 1–3 digits, or `@` followed by any letter; also any `\x1b[…m` |

Each defect above is a place where two of these disagree:

- **CO-1:** the scan and the appended `@w` disagree about whether the string has any code to convert.
- **CO-2:** `fixstring` disagrees with `CONVERTCOLORS` about `k`.
- **CA-3:** `ansicode.strip` and `_CELL_TOKEN` disagree about what counts as an SGR sequence.

## Other Observations

- **The xterm colour table is off by one.**
  - The 6×6×6 cube loop runs 217 times, so it fills 16–232 and gives 232 the cube's last value. It should be greyscale.
  - The greyscale loop fills 234–254, so 233 and 255 are missing.
  - Only `colorcode.to.html` reads the table, and nothing calls it.
- **`COLORCODE_REGEX` is malformed and unused.** It is the character class `[cmyrgbwCMYRGBWD|xz[\d{0:3}]` followed by `]`.
- **`@x` means two things.** It is both the xterm prefix and, through `CONVERTCOLORS['x'] = '0'`, a reset. That is why a reset converted from ANSI (CA-1) becomes an invalid code.
- **Bold is inconsistent.** Uppercase colours are emitted as `1;3x` without a reset, so bold carries into a following xterm colour. A following lowercase colour resets it.
- **`show` has the wrong help text.** Its usage text describes "The original string to be replaced".

## Recommended Design

Tracked in #534.

1. **One tokenizer module** in the colors plugin, the only definition of the syntax. It splits text in one pass into:
   - literal text;
   - an escaped `@@`;
   - a basic `@` colour;
   - an xterm foreground or background code;
   - an ANSI SGR sequence with its parameters.
2. **Every function uses it.** That covers stripping, conversion in both directions, validation and HTML. The width and wrapping code in `utils` calls it through an API instead of keeping its own regex.
3. **Conversion tracks colour state.**
   - Foreground, background and bold are set separately.
   - A single reset is emitted at the end, and only if a colour was set.
   - From ANSI, SGR parameters are handled one at a time, in any number: reset (`0` and empty), bold, the standard and bright colours, 256-colour, and true colour mapped to the nearest xterm colour.
4. **Stripping works on the tokens directly**, with no round trip through ANSI.
5. **Display width** (#528) becomes the wcwidth of the text tokens, with every code counting as zero.

This changes the colour output that triggers and every coloured message depend on. Build it test-first from the
cases on this page, and get the repo admin's approval for any change to an existing test's expected output.

## Tracking

| Finding | Issue |
|---|---|
| CO-1 to CO-4 | #532 |
| CA-1 to CA-3 | #533 |
| Root cause, other observations, design | #534 |
| Display width | #528 (after #534) |

**Status:** #534 fixes CO-1 to CO-4 (the `@` code output defects tracked in #532) and CA-3, and rebuilds every colour API on one tokenizer, described in [Colour System](colors_system.md). #533 fixes CA-1 and CA-2. CO-3 applies to every lowercase colour except `@w`, which stays the general reset and clears the background; callers such as `colors.show` rely on that.
