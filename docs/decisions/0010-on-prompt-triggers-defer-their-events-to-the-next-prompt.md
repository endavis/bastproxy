---
title: "ADR-0010: On-prompt triggers defer their events to the next prompt"
description: A trigger added with on_prompt=True matches its line at once but holds its event until the next GA/EOR prompt line, falling back to immediate firing for a MUD that sends no prompts and to a timeout when the prompt is late.
date: 2026-11-18
audience:
  - contributors
tags:
  - adr
---

# ADR-0010: On-prompt triggers defer their events to the next prompt

## Status

Accepted

## Context

A MUD that marks prompts with GA or EOR sends output in bursts that end in a prompt. A trigger that sends a command mid-burst sends it before the MUD has finished, and the reply can interleave with the rest of the output (#544). The MUD reader already marks prompt lines (`NetworkDataLine.is_prompt`), including a prompt with no trailing newline, which is delivered as soon as the GA/EOR arrives; the triggers plugin did not read the flag.

Helpers that react to prompts (#548) need one place in the plugin where a prompt arrives.

## Decision

1. **Option.** `trigger.add` and `trigger.update` accept `on_prompt` (default `False`). Triggers without it behave as before.
2. **Match now, fire later.** An `on_prompt` trigger matches its line when the line arrives; its regex, `when`, `argtypes`, `stopevaluating` and `omit` apply then. Only its event is held, and it is raised in arrival order when the next prompt line passes through `_eventcb_check_trigger`, after that line's own triggers. A trigger whose regex matches the prompt therefore fires on that line.
3. **Callback data.** A held event carries `args["prompt"]`, the prompt line, or `None` when it fired at once or timed out. Hits count when the event fires. A trigger removed or disabled while its event is held does not fire.
4. **A MUD with no prompts.** Until a prompt line has been seen, `on_prompt` triggers fire at once. A disconnect (`ev_libs.net.mud_muddisconnect`) forgets that and drops held events.
5. **Time limit.** A held event older than `PROMPT_MAX_WAIT` (2.0 s) is raised, with `prompt=None`, when the next MUD line is checked. Expiry is lazy, like `EchoRecord`: with no further line, the event waits.
6. **One prompt point.** All prompt handling goes through `TriggersPlugin._prompt_arrived`, which flushes the held events and then raises a new built-in `prompt` trigger (no regex, only for prompt lines, only with a listener).

## Rationale

- **Match now (2):** the line, its groups and `omit` belong to the moment the line passes; deferring only the event keeps `omit` and `stopevaluating` meaning what they do for every other trigger.
- **Fallback (4):** a MUD without GA/EOR never ends a burst, so waiting would mean never firing.
- **Lazy expiry (5):** no timer to start, stop or leak; the cost is an event that waits until another line arrives.
- **Built-in `prompt` (6):** #548 registers on it through the API instead of reading `is_prompt` itself.

## Consequences

- A line with `omit` is hidden at match time even though the event fires later.
- With no further line after the burst and no prompt, a held event stays held.
- The queue and its state live in `src/bastproxy/plugins/core/triggers/plugin/_prompt.py` and `_triggers.py`.

## Related

- [Triggers system, Prompt Triggers](../claude/triggers_system.md#prompt-triggers)
- Issues #544 and #548
- [ADR-0007](0007-triggers-match-each-triggers-own-regex-in-priority-order.md)
