---
title: "ADR-0011: Plugins wait for MUD output through per-waiter queues on the triggers plugin"
description: Plugins wait for MUD output through per-waiter line queues in the triggers plugin, reached through awaitable plugins.core.triggers APIs that always clean up and log instead of raising.
date: 2026-11-18
audience:
  - contributors
tags:
  - adr
---

# ADR-0011: Plugins wait for MUD output through per-waiter queues on the triggers plugin

## Status

Accepted

## Context

A plugin that sends a command and then acts on the reply had to register a temporary trigger, keep state across callbacks and remove the trigger afterwards. Issue #548 asks for a "send, then wait" helper. Concurrent users must not take each other's matches, and a timeout or cancellation must leave nothing behind.

## Decision

1. **Home.** The facility lives in the triggers plugin (`src/bastproxy/plugins/core/triggers/plugin/_waiters.py`).
2. **Per-waiter queues.** Each waiter has its own bounded queue of lines. Every waiter sees every line. A wait consumes the lines up to and including its match; later lines stay queued.
3. **Hook.** A separate callback on `ev_to_client_data_modify` at priority 40 feeds the waiters. The trigger matching path is not changed. Waiters are not gated by the triggers `enabled` setting and they see the MUD's echo of a sent command.
4. **Awaitable APIs.** `line.get.next`, `prompt.get.next` and `line.get.after.send` are the first awaitable plugin APIs. They are sync functions that return a coroutine, so nothing is registered until it is awaited. Event callbacks stay synchronous; callers start the coroutine with `libs.asynch:task.add`.
5. **Cleanup.** Timeout, cancellation, `close()` and plugin unload each remove the waiter. A wait always has a positive timeout.
6. **No raise.** Bad input (invalid regex, non-positive timeout, closed waiter, second concurrent wait) is logged and the awaitable resolves to `None`.

## Rationale

- **Triggers plugin:** it already sees every MUD line and owns the matching rules and the per-owner cleanup; a new plugin would duplicate them.
- **Per-waiter queues:** a shared one-shot trigger would let one plugin take another's match, and a batch of lines delivered together would lose the prompt after the match.
- **Separate callback:** it keeps the trigger matching path unchanged.
- **Coroutine-returning APIs:** they resolve the caller's owner at call time and register nothing until awaited, so an un-awaited call leaks nothing.

## Consequences

- Plugins reach the helper through `plugins.core.triggers:*` APIs with no cross-plugin import.
- A prompt wait needs the MUD to send GA/EOR; otherwise it times out (prompt-aware matching is #544).
- With no open waiter the feed callback returns at once.

## Related Documentation

- [Triggers System: Waiting for Output](../claude/triggers_system.md#waiting-for-output)
- [Plugin Developer Guide: Waiting for output](../plugin-developer-guide.md#waiting-for-output)
- Issue #548; related ADR-0004 (API naming) and [ADR-0007](0007-triggers-match-each-triggers-own-regex-in-priority-order.md).
