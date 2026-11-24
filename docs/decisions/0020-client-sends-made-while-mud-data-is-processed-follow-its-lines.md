---
title: "ADR-0020: Client sends made while MUD data is processed follow its lines"
description: Client sends made while MUD data is processed are held and sent after the data's last line, in the order made.
date: 2026-11-24
audience:
  - contributors
tags:
  - adr
---

# ADR-0020: Client sends made while MUD data is processed follow its lines

## Status

Accepted

## Context

Issue #746: a plugin that sends output from a trigger callback reached the client before the MUD lines that came before the matching line. `MudConnection.mud_read` hands a batch of lines to one `ProcessDataToClient`, which raises `ev_to_client_data_modify` for the whole batch before it sends any line. A `SendDataDirectlyToClient` made inside that event ran at once. #714 solved the same problem for the MUD direction with `PendingMudSends`.

## Decision

- `src/bastproxy/libs/context.py` gets the context variable `client_capture` and the context manager `holding_client_sends`. `fresh_context()` resets it, so other tasks never inherit it.
- `ProcessDataToClient._exec_` sets a `PendingClientSends` around its modify event. While it is open, `SendDataDirectlyToClient.__call__` appends the send to it, adds an INFO update and returns.
- The batch's own `SendDataDirectlyToClient` sends its lines, then runs the held sends in the order made, then raises `ev_to_client_data_read`. Plugin output goes out after the batch's last line, usually the prompt. There is no per-line anchoring, unlike #714.
- A held send keeps its own `clients`, `exclude_clients` and formatting. A held send is released through `BaseRecord.__call__`, so it cannot be held twice.
- A nested `ProcessDataToClient` hands its send, with its own held sends, to the outer capture. When `send_to_clients` is False or the modify event raises, the held sends are still released, so output is never lost.
- Sends outside MUD processing (client commands, timers, events not caused by MUD data) send at once.
- Side effect: client log lines and `#bp` command output from actions fired by MUD lines are also held until after the batch, including errors logged from trigger callbacks.

## Rationale

Processing is synchronous inside the `mud_read` task and the capture is a context variable, so it cannot leak across tasks or reorder output across batches. Holding until after the prompt matches the maintainer's decision that output follows the packet's lines in the order made, and reuses the #714 shape. On-prompt triggers (ADR-0010) already defer their events to the next prompt; this change affects only when the output is sent.

## Related Issues

- Issue #746: send plugin output after the MUD packet that triggered it
- Issue #714: lines re-sent while an input is separated

## Related Documentation

- [Data flow](../claude/data_flow.md)
- [Record system](../claude/record_system.md)
- [ADR-0010](0010-on-prompt-triggers-defer-their-events-to-the-next-prompt.md)
