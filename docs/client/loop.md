---
title: Loop
description: Run a line a number of times, with the counter in the line, through aliases and variables
audience:
  - users
  - contributors
tags:
  - client
  - loop
---

# Loop

The `plugins.client.loop` plugin runs a line a number of times. Each pass goes through the normal input path, so the command separator, `#bp` commands, [aliases](aliases.md) and [variables](variables.md) all apply to every line the loop runs. The counter syntax is the one of [ADR-0017](../decisions/0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md).

## Command

| Command | What it does |
| :--- | :--- |
| `#bp.client.loop.run COUNT LINE...` | Run LINE COUNT times. |

Typing only `#bp.client.loop` runs `run`, the plugin's default command (#778). Without a count it shows the help of `run`.

```text
#bp.client.loop.run 10 get all %1.corpse
#bp.client.loop.run 3 stand||look %1
```

The first example sends `get all 1.corpse` up to `get all 10.corpse`. Type a doubled separator (`||`) to put several commands in one pass, as for an alias. Passes are not added to the command history.

Other plugins can call the API `plugins.client.loop:loop.run(template, count)`. It returns True when every pass ran, and False, logging a warning, when it refused or stopped early.

## The counter

- `%1` is the pass number, starting at 1.
- `%%1` is a literal `%1`. The counter is never substituted again.
- Digits are read one at a time, so `%10` is the counter followed by `0`.
- `%2` to `%9` and `%*` are left as typed.
- A line with no `%1` is sent as typed: `#bp.client.loop.run 5 north` sends `north` five times. Unlike an alias, the counter is not added at the end.
- `%{name}` is a variable reference, and is expanded on each pass by [variables](variables.md).

## Limits

- COUNT is a whole number from 1 to 50. Anything else is refused with `Count must be a whole number from 1 to 50`, and nothing runs.
- A line to run is required: an empty one is refused with `Please provide a line to run`.
- Loops can be nested, with 200 passes in total across the outermost loop and every loop inside it, outer passes included. A nested loop that would go past the limit is refused before it runs, and the outer loop stops before its next pass and reports `ran k of n times: nested loops reached the limit of 200 runs`.

## Nesting

Escape the counter for the inner loop with `%%1`. This line runs the inner loop twice for each of three outer passes:

```text
#bp.client.loop.run 3 #bp.client.loop.run 2 get %%1.item %1.bag
```

The inner loop receives `get %1.item 1.bag` on the first outer pass, so it sends `get 1.item 1.bag` and `get 2.item 1.bag`. An alias can hold `%%1` in the same way to pass `%1` on to a loop.

## Ordering

The passes take the loop command's place. `stand|#bp.client.loop.run 2 kill` sends `stand`, then both `kill` lines, as for alias re-sends (#714).

## Notes

- A line that starts with `-` is read as an option, as for aliases.
- Related: [Aliases](aliases.md), [Variables](variables.md).
