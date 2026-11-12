---
title: "ADR-0007: Triggers match each trigger's own regex in priority order"
description: Each trigger matches its own compiled regex, ordered by priority then order added, instead of one combined alternation; stopevaluating stops later triggers, built-ins are raised only with a listener, and the measured per-line and add costs are recorded.
date: 2026-11-12
audience:
  - contributors
tags:
  - adr
---

# ADR-0007: Triggers match each trigger's own regex in priority order

## Status

Accepted

## Context

The triggers plugin joined every enabled regex into one alternation and ran it once per line. The triggers audit ([findings](../claude/triggers_system_findings.md), Q8) found four defects that come from that design:

- **TR-1 (#346):** the alternation reports one regex per line, the first one added, so `priority` is ignored and a second trigger with an overlapping regex never fires.
- **TR-5 (#350):** the alternation changes the meaning of backreferences, and one regex that fails to compile freezes the matcher for every later trigger.
- **TR-6 (#351):** a `matchcolor` trigger needs a second match on the colour-coded text, and the first pass could hide it.
- **TR-10 (#355):** the alternation is recompiled on every add, remove, toggle and update. Adding 1,000 triggers one by one took 46.57 s in the audit.

`priority` and `stopevaluating` across regexes cannot be implemented on a single alternation without a second pass. Issue #359 (TR-14) asks for the redesign.

## Decision

Each trigger matches its own compiled regex. The repo owner confirmed this scope: #346 is fixed by the #359 matcher.

1. **One compiled regex per trigger.** The plugin keeps `_ordered`, a list of enabled regex triggers sorted by `(priority, order added)`. Lower priority runs first, and ties go in the order added. `order` is a counter set at add and kept by update and toggle.
2. **Anchored, on purpose.** Matching stays `.match`, anchored at the start of the line, as before. A regex that should match anywhere starts with `.*`.
3. **Text is read once.** `noansi` is read once per line. `colorcoded` is read only when the first `matchcolor` trigger is reached, then reused. A trigger with `matchcolor` matches only the colour-coded text; any other trigger matches `noansi`. Every trigger sees the line as it was when matching began.
4. **`stopevaluating`.** A matching trigger with `stopevaluating` stops every later trigger for the line, whatever its regex. The `all` built-in still runs. A trigger that does not match, or that fails, stops nothing.
5. **Isolation.** The loop runs over a copy of the list and re-checks each item before use (still enabled and still in `triggers`). Each trigger's match, argument conversion and raise run in their own `try`; an error is logged with the trigger id and the line, and the next trigger runs.
6. **Built-ins only with a listener.** `beall`, `all` and `emptyline` are raised only when their event has a registered function. An empty line raises only `emptyline` and tries no regex.
7. **Removed:** the regex table (`regexes`, `regex_lookup_to_id`), the combined regex (`created_regex`, `rebuild_regexes`), `process_match`, and the named-group strip. The ten trigger APIs and their signatures are unchanged. `TriggerItem.regex_id` stays as `None` for one release and `TriggerItem.regex` equals `original_regex`.
8. **No new dependency.** `google-re2` was rejected in Q8. A first-word prefilter is the later option once the benchmark (#358) gives a budget.

## Rationale

- **Own regex (1):** it is the only layout where priority, `stopevaluating`, backreferences and `matchcolor` each mean what the docs say, with no second pass.
- **Add time (1):** a compile per add replaces a compile of everything per change, so adding triggers is linear.
- **Copy and re-check (5):** a callback may remove or disable a later trigger, or its own. The loop must neither raise nor fire the removed trigger.
- **Listener check (6):** the check is the one `trigger.remove` already uses. It also removes the per-line cost of raising three events nobody listens to.

## Consequences

Breaking, listed in the commit's `BREAKING CHANGE:` footer:

- Overlapping triggers with different regexes all fire. Set `stopevaluating` on the earlier one to keep the old hiding.
- Triggers run in `priority` order (lower first), then order added. Current triggers all use 100, so their order stays.
- `stopevaluating` stops every later trigger for the line.
- `matchcolor` matches only the colour-coded text.
- `#bp.triggers.detail` loses "Regex (w/o Groups)" and "Regex ID"; the stats lose the three regex rows; `TriggerItem.regex_id` is always `None`.
- Built-in triggers are raised only when they have a listener.

Status of the other audit items: TR-1, TR-5, TR-6 and the rebuild half of TR-10 are fixed. TR-7 (#352) and TR-8 (#353) are partly fixed and stay open. TR-4, TR-9, TR-11, TR-12 and TR-13 are not part of this change.

### Measured cost

Python 3.12.12, `regex` 2026.9.29, 12th Gen Intel Core i7-12650H, Linux 6.17.13-2-pve. 250 to 2,000 triggers added one by one, the old code from `git show HEAD:...` and the new code in the same harness.

**Stubbed harness** (the matcher alone: a stand-in plugin object, the event raise replaced by a no-op, built-ins without listeners; median of 7 runs of 2,000 lines). Microseconds per line:

```
triggers     line       old       new
      10  nomatch       1.6       4.6
      10    first       6.3       5.7
      10     last       6.7       5.7
     100  nomatch       1.9      25.2
     100    first      28.3      17.7
     100     last      31.7      25.4
    1000  nomatch       4.2     243.0
    1000    first     238.6     152.7
    1000     last     298.4     251.0
```

The matcher alone is slower for a line that matches nothing: the old alternation rejects such a line in one pass, and the new matcher tries each regex. This table leaves out what the running proxy pays around the matcher, so it is not the figure that decides cost.

**End to end** (the real plugin system booted in-process, built-ins without listeners, triggers added from a throwaway owner, the whole `ProcessDataToClient` raise of `ev_to_client_data_modify` for one line; median of 7 runs of 300 lines; three process runs per matcher gave the same ordering; one run of each is shown). Microseconds per line:

```
old  triggers   nomatch     first      last
           0    1108.7
          10    1140.0    1314.3    1320.3
         100    1146.8    1361.6    1390.1
        1000    1271.8    1701.2    1797.9
new
           0     843.9
          10     825.6     991.5    1019.7
         100     867.5    1014.3    1008.4
        1000    1123.8    1219.3    1294.3
```

The new total is lower than the old one at 10, 100 and 1,000 triggers for all three line types, in every run. The gap at zero triggers (about 270 us) is the old code raising `beall` and `all` for every line even with no listener; measured alone on the old code, those two raises cost 272.7 us per line.

**Adding triggers** (seconds for N distinct regexes added one by one):

```
     N     old s     new s  new us/trigger
   250      1.58     0.022            89.1
   500      6.75     0.055           109.1
  1000     29.60     0.141           140.8
  2000    136.82     0.318           158.8
```

## Related Issues

- #346 (only the first-added trigger regex fires; priority is ignored)
- #359 (TR-14: replace the combined regex with one regex per trigger)
- #350 (TR-5), #351 (TR-6), #355 (TR-10)
- #358 (TR-13: benchmark and budget)

## Related Documentation

- [Triggers System](../claude/triggers_system.md)
- [Triggers System Findings](../claude/triggers_system_findings.md)
