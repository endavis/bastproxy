---
title: "ADR-0008: The colors tokenizer is the single definition of the colour-code syntax"
description: The colors plugin has one tokenizer that defines the colour-code syntax, and other plugins reach it only through the colorcode.to.tokens API, never by import.
date: 2026-11-17
audience:
  - contributors
tags:
  - adr
---

# ADR-0008: The colors tokenizer is the single definition of the colour-code syntax

## Status

Accepted

## Context

The `@` colour-code syntax was defined five times, in regexes of the colors plugin and in `_CELL_TOKEN` in the utils plugin, and the five disagreed ([findings](../claude/colors_findings.md)). Issue #534 asks for one definition. A second question is how other plugins reach it: plugins must not import each other.

## Decision

1. The colors plugin has one tokenizer, `src/bastproxy/plugins/core/colors/libs/_tokenizer.py`. It is the only definition of the `@` and SGR syntax; every colors API is built on it.
2. Only the colors plugin's own modules import it. Other plugins reach it through the `plugins.core.colors:colorcode.to.tokens` API, which returns `(raw, visible)` pairs of plain tuples, so no colors type crosses the plugin boundary.
3. `table.format` looks the API up once per call and passes it to `wrap_cell`. The commands plugin is a second consumer: it passes the same API to `argp.CustomFormatter` for help wrapping.
4. A test asserts that no other module compiles a pattern for `@` codes or SGR sequences.

The syntax and the rules are in [Colour System](../claude/colors_system.md). Implemented by #534.

## Rationale

- **One definition:** the five definitions gave different answers for the same string; one scan cannot.
- **API only:** a plugin importing another plugin couples their load order and layering; the API is the plugin boundary.
- **Plain tuples:** `utils` needs only widths, so it needs no `Token` type.

## Consequences

- Strings with a malformed `@` change their width and output (the audit's CO-1 to CO-4, and CA-3 for SGR stripping). The pull request lists each change.
- Any new code that needs the syntax calls `colorcode.to.tokens`, or the colors API that fits, and never writes its own pattern.
- #533 (the ANSI to colour-code direction) and #528 (display width) build on this.
