---
title: Triggers System
description: Regex matching on MUD output that raises events for plugins to handle
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - triggers
---

# Triggers System

## Overview

The triggers system in bastproxy provides pattern matching on MUD output using regular expressions. When a line from the MUD matches a trigger's pattern, an event is raised that plugins can respond to. Triggers support named capture groups, type conversion of the captured values and line omission.

This page describes what the code does today, including where that is not what the API suggests. The audit behind it is [Triggers System Findings](triggers_system_findings.md); defects are referred to by their number there (TR-1, TR-2 and so on). The points most likely to surprise:

- A regex is matched from the **start of the line** (`match`, not `search`). `orc` does not match `You hit orc.`; `.*orc` does.
- **Every** enabled trigger whose own regex matches the line fires, in `priority` order (lower first), then in the order added. `stopevaluating` stops every later trigger for the line. Each trigger has its own compiled regex ([ADR-0007](../decisions/0007-triggers-match-each-triggers-own-regex-in-priority-order.md)).
- `group.toggle.enable` was fixed in #349 (TR-4). `trigger.update` was fixed in #348 (TR-3), and `trigger.toggle.enable` sets `TriggerItem.enabled`, so it can enable a trigger added disabled (TR-2, fixed by #347).

## Key Components

### TriggerItem Class
**Location**: `src/bastproxy/plugins/core/triggers/plugin/_triggers.py`

Represents a single trigger:

```python
class TriggerItem:
    def __init__(self, owner_id, trigger_name, regex, regex_id, original_regex,
                 enabled=True, group=None, omit=False, priority=100,
                 stopevaluating=False, argtypes=None, matchcolor=False,
                 trigger_id=None, original_regex_compiled=None, order=0,
                 when=None, conditions=()):
        self.api = API(owner_id=f"{owner_id}:{trigger_name}")
        self.enabled = enabled                      # Set at creation; trigger.toggle.enable updates it (TR-2)
        self.owner_id = owner_id
        self.trigger_name = trigger_name
        self.regex = regex                          # Equal to original_regex
        self.regex_id = regex_id                    # Always None, kept for one release
        self.original_regex = original_regex        # The regex as given, with named groups
        self.original_regex_compiled = original_regex_compiled
        self.group = group                          # Trigger group
        self.omit = omit                            # Gag matched lines
        self.priority = priority                    # Orders matching: lower runs first
        self.stopevaluating = stopevaluating
        self.argtypes = argtypes                    # Type conversions
        self.matchcolor = matchcolor                # Match the colour-coded text instead of the plain text
        self.when = when                            # GMCP conditions as given: {"Char.Vitals.hp": ">50"}
        self.conditions = conditions                # The parsed form of `when`, checked after the regex matches
        self.order = order                          # Counter set when the trigger is added; breaks priority ties
        self.hits = 0
        self.trigger_id = trigger_id                # "t_<owner_id>_<trigger_name>"
        self.event_name = f"event_{self.trigger_id}"  # Not a parameter (removed by #354)
```

`raisetrigger(args)` counts a hit, sets `args["line"].send = False` when `omit` is set, writes `trigger_name` and `trigger_id` into `args` and raises `event_name` with `args` as the event data.

### EchoRecord Class
**Location**: `src/bastproxy/plugins/core/triggers/plugin/_echo.py`

A bounded record of lines the proxy sent, used to skip their echoes (see [Echoed Commands](#echoed-commands)).

### TriggersPlugin Class
**Location**: `src/bastproxy/plugins/core/triggers/plugin/_triggers.py`

Manages all triggers:

```python
class TriggersPlugin(BasePlugin):
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        self.can_reload_f = False       # The triggers plugin cannot be reloaded
        self.beall_id = ...             # Ids of the built-in triggers
        self.all_id = ...
        self.emptyline_id = ...
        self.prompt_id = ...            # The built-in prompt trigger (#544)
        self._prompts_seen = False      # True once a prompt line has arrived
        self._pending = PromptQueue()   # on_prompt events held for the next prompt
        self.triggers = {}              # trigger_id -> TriggerItem
        self.trigger_groups = {}        # group name -> list of trigger ids
        self._ordered = []              # Enabled regex triggers, sorted by (priority, order)
        self._next_order = 0            # Next value for TriggerItem.order
```

`_ordered` is what matching walks. Add, update (regex, `enabled` or `priority`), toggle and remove keep it in step; a trigger without a regex is never in it. `trigger.remove` removes the id from its group, and a group left empty is deleted (TR-4, fixed by #349).

## How It Works

### 1. Creating Triggers

Create triggers via API:

```python
# Simple trigger
self.api("plugins.core.triggers:trigger.add")(
    "hp_warning",                                # Trigger name
    r"HP: (\d+)/(\d+)",                         # Regex pattern, matched from the start of the line
    owner_id=self.plugin_id
)

# With named groups
self.api("plugins.core.triggers:trigger.add")(
    "combat_damage",
    r"You hit .* for (?P<damage>\d+) damage",   # Named group
    owner_id=self.plugin_id,
    argtypes={"damage": int}                     # Convert to int
)

# With options
self.api("plugins.core.triggers:trigger.add")(
    "secret_message",
    r"Secret: .*",
    owner_id=self.plugin_id,
    omit=True,                                   # Hide from client
    priority=10,                                 # Lower runs first; ties go in the order added
    group="secrets"                              # Trigger group
)

# Only when the GMCP data agrees
self.api("plugins.core.triggers:trigger.add")(
    "low_hp_warning",
    r"^You are bleeding",
    owner_id=self.plugin_id,
    when={"Char.Vitals.hp": "<50", "Char.Status.state": "=fight"}
)
```

`when` maps dotted GMCP paths to a comparison string: an operator (`=`, `!=`, `>`, `>=`, `<`, `<=`) and an operand. The trigger raises its event only when its regex matches and every condition holds (see [Trigger Matching](#3-trigger-matching) and [GMCP Conditions](#gmcp-conditions)).

`trigger.add` returns a `TriggerAddResult(success, trigger)`: `success=True` with `trigger` set to the new item, or `success=False` with `trigger=None` on every failure (a name the owner already uses, a regex that does not compile, no owner found, an unknown keyword), logging an error with the reason. Check `result.success` before using `result.trigger`; the result is always truthy, so test `result.success`, not the result (TR-9, #354). Before #426 it returned a `(success, trigger)` tuple; unpacking the result now raises `TypeError`. The regex is matched with `match`, so it must match from the first character of the line: `You hit .* for (?P<damage>\d+) damage` above does not match `[combat] You hit orc for 5 damage`. Start a pattern with `.*` to match anywhere in the line.

### 2. Responding to Triggers

Register callbacks for trigger events:

```python
# Create trigger
result = self.api("plugins.core.triggers:trigger.add")(
    "hp_low",
    r"HP: (?P<current>\d+)/(?P<max>\d+)",
    owner_id=self.plugin_id,
    argtypes={"current": int, "max": int}
)
if not result.success:
    return

# Register callback
self.api("plugins.core.triggers:trigger.register")(
    "hp_low",
    self.handle_hp_warning
)

def handle_hp_warning(self):
    """Handle low HP warning."""
    event_record = self.api("plugins.core.events:event.current.record.get")()
    matches = event_record["matches"]

    current = matches["current"]
    max_hp = matches["max"]

    if current < (max_hp * 0.2):  # Below 20%
        get_logger(self.plugin_id).warning("WARNING: Low HP! %s/%s", current, max_hp)
        # Take action (heal, flee, etc.)
        self.emergency_heal()
```

### 3. Trigger Matching

`_eventcb_check_trigger` is registered on `ev_to_client_data_modify`, which `ProcessDataToClient` raises once per record with every MUD I/O line in it. For each line:

1. A line that is `internal` is skipped.
2. If the line is a prompt, `_prompts_seen` is set. Held `on_prompt` events older than `PROMPT_MAX_WAIT` are raised with `prompt=None`. The `beall` trigger's event is raised, if something is registered on it.
3. The text is `line.noansi`: every terminal escape sequence (colour codes, cursor movement, clearing, OSC 8 links) and, when the line has an MXP mode, MXP markup are removed. C0 controls and 8-bit C1 sequences are kept.
4. If the text is `""`, the `emptyline` trigger's event is raised (if something is registered on it) and no regex is tried. A line of colour codes only counts as empty; a line of spaces does not.
5. Otherwise, unless the text is the echo of a line the proxy sent ([Echoed Commands](#echoed-commands)), `_match_line` walks a copy of `_ordered`, lowest `priority` first and, within a priority, in the order added. It skips a trigger that was disabled or removed since the walk began. Each trigger's own compiled regex is matched from the start of the text: `line.colorcoded` for a `matchcolor` trigger, `line.noansi` for any other. `colorcoded` is read only when the first `matchcolor` trigger is reached, and then reused. Triggers whose compiled regex has the same pattern text and flags, and that read the same text, share one match per line (a per-line cache in `_match_line`, #383, used only for triggers flagged `shared_pattern`; `_sync_order` and `_sync_order_remove` keep that flag current, so a trigger with a unique pattern is matched directly); each still gets its own `groupdict()`, so `argtypes` never leak between them.
6. On a match, a trigger with `when` checks its GMCP conditions (`_conditions_hold`). If one fails, the trigger is skipped for this line: no event, no hit, `stopevaluating` not applied, and a DEBUG line is logged. A trigger without `when` pays only an empty-tuple check. Then the named groups are converted with `argtypes`, a fresh `matches` dictionary is built, and `raisetrigger` raises the trigger's event. `omit` sets `line.send = False` before the callbacks run. An `on_prompt` trigger hides the line at this point too, but holds its event ([Prompt Triggers](#prompt-triggers)).
7. A trigger with `stopevaluating` that matched ends the walk.
8. If the line is a prompt (also an empty or echo-skipped one), `_prompt_arrived` raises the held `on_prompt` events, then the built-in `prompt` trigger's event, if something is registered on it ([Prompt Triggers](#prompt-triggers)).
9. The `all` trigger's event is raised, if something is registered on it.

Every trigger sees the line as it was when matching began. Why each trigger has its own regex, and what it costs, is in [ADR-0007](../decisions/0007-triggers-match-each-triggers-own-regex-in-priority-order.md).

What follows from this:

- Two triggers with different regexes that both match a line both fire, in priority order. Set `stopevaluating` on the earlier one to keep the later one from firing.
- Backreferences (`\1`, `(?P=name)`) mean what they say, and a regex that does not compile is refused at `trigger.add` without affecting any other trigger.
- A `matchcolor` trigger matches only the colour-coded text, so its regex can carry colour codes (`^@rWARNING`); it does not match the plain text.
- Each trigger's match, conversion and raise run in their own `try`. An error is logged with the trigger id and the line, the next trigger runs, and a failed trigger does not apply `stopevaluating`. A group that did not take part in the match stays `None` in `matches` and is not converted by `argtypes` (TR-7, #352).
- A callback that raises is logged by the event system and the other callbacks and triggers still run. A callback may remove or disable a later trigger; it then does not fire for this line.
- A prompt is matched like any other line, in the same call that delivers it. The MUD reader delivers a GA/EOR-marked prompt without a newline at once with `is_prompt` set, and an unmarked partial line after its line timeout, so no change to the reader was needed (#544).

### Prompt Triggers

A trigger added with `on_prompt=True` (also accepted by `trigger.update`) matches its line when the line arrives, but its event is held until the next line marked `is_prompt` (GA or EOR) passes through `_eventcb_check_trigger`. A trigger that sends a command then sends it after the burst it matched in, not in the middle of it. See [ADR-0010](../decisions/0010-on-prompt-triggers-defer-their-events-to-the-next-prompt.md).

- **At match time:** the regex, `when`, `argtypes`, `stopevaluating` and `omit` apply when the line arrives. A failed `when` holds nothing.
- **At the prompt:** held events are raised in arrival order, after the prompt line's own triggers. An `on_prompt` trigger whose regex matches the prompt fires on that line.
- **Callback data:** `args["prompt"]` is the prompt line, or `None` when the event fired at once or timed out. `args["line"]` is the line that matched. `omit` is not applied again at fire time.
- **Hits** count when the event fires. A trigger removed or disabled while its event is held does not fire.
- **No GA/EOR:** until a prompt line has been seen, `on_prompt` triggers fire at once. A disconnect resets that and drops held events.
- **Time limit:** a held event older than `PROMPT_MAX_WAIT` (2.0 seconds, `_prompt.py`) is raised with `prompt=None` when the next MUD line is checked. Expiry is lazy: if no line arrives, the event waits.
- **`prompt` built-in:** `_prompt_arrived` raises it for every prompt line, so `trigger.register("prompt", ...)` runs a function on each prompt.

### Echoed Commands

Many MUDs echo a command back as output. So that a trigger does not fire on the echo of a command the proxy itself sent (#545), `_eventcb_record_sent` listens on `ev_to_mud_data_read` and records each sent line that is `internal` (sent by a plugin or trigger, not a client) and normal I/O. The record is an `EchoRecord` (`src/bastproxy/plugins/core/triggers/plugin/_echo.py`) kept in `_echoes`.

- The text recorded is `line.noansi` with the trailing `\r\n` removed. An empty line is not recorded.
- When `_eventcb_check_trigger` gets a MUD line whose `line.noansi` equals a recorded entry exactly, it removes that one entry and skips `_match_line`. The line is still sent to clients, and `beall`, `emptyline` and `all` are unaffected; only the regex triggers are skipped.
- One-shot: an entry skips at most one line. `look at sword` against a recorded `look` still matches and leaves the entry.
- Bounded: at most `ECHO_MAX_ENTRIES` (20) entries, the oldest dropped first, and an entry older than `ECHO_MAX_AGE` (15.0 seconds) is dropped before each lookup, so a command the MUD never echoes does not linger. Both are module constants, not settings.
- Limits: a client that types the same text while a plugin's entry is pending uses that entry up, and a MUD that echoes the command on the same line as its prompt does not give an exact match, so the triggers still run.

### Waiting for Output

A plugin that sends a command and needs the answer uses a waiter (#548), in `src/bastproxy/plugins/core/triggers/plugin/_waiters.py`. `_eventcb_feed_waiters` (priority 40, before `_eventcb_check_trigger`) offers each non-internal MUD line (`line.noansi` and `line.is_prompt`) to every open waiter.

- Each `LineWaiter` has its own queue (at most 1000 lines, oldest dropped). A wait first reads the queued lines, then waits for new ones, and consumes every line up to and including its match; later lines stay queued. Every waiter sees every line, so two plugins never take each other's matches.
- A waiter has at most one wait at a time. `wait_for(pattern, timeout)` uses `.match()`; `wait_for_prompt(timeout)` resolves on the next line with `is_prompt` (the MUD must send GA or EOR). `send_and_wait(command, pattern, timeout)` sends after the waiter is registered.
- The result is a `WaitResult` with `text`, `is_prompt`, `match` and `matches` (the named groups).
- Waiters are not gated by the `enabled` setting, and they see the MUD's echo of a sent command, so a pattern should not match the bare command text.
- A waiter is closed by `close()`, by leaving its `with` block, or when its owner plugin unloads (`ev_plugin_unloaded`); a pending wait then resolves to `None`.
- Event callbacks are sync: start the coroutine with `libs.asynch:task.add`. The `sendwait` command of the test triggers plugin is a live demo.

## Common APIs

- `plugins.core.triggers:trigger.add` - Add a trigger; returns a `TriggerAddResult(success, trigger)` (`trigger` is `None` when `success` is false), with an error logged on failure (duplicate, no owner, regex that does not compile, unknown keyword)
- `plugins.core.triggers:trigger.remove` - Remove a trigger. Refused (returns `False`) while a callback is registered on its event, unless `force=True`. A trigger without a regex (a built-in) is removed without error
- `plugins.core.triggers:trigger.update` - Update a trigger in place (`regex`, `enabled`, `group`, `omit`, `priority`, `stopevaluating`, `argtypes`, `matchcolor`, `when`, `on_prompt`; `when` of `None` or `{}` clears the conditions); returns `True`, or `False` with an error logged for an unknown trigger, key, invalid `when` or uncompilable regex, changing nothing (TR-3, fixed by #348)
- `plugins.core.triggers:trigger.get` - Get the `TriggerItem`, or `None` (a query: nothing is logged)
- `plugins.core.triggers:trigger.register` - Register a callback on the trigger's event; takes a trigger name or id. Returns `True`, or `False` with an error logged for an unknown trigger (TR-9, #354)
- `plugins.core.triggers:trigger.unregister` - Unregister a callback; returns `True`, or `False` with an error logged for an unknown trigger
- `plugins.core.triggers:trigger.toggle.enable` - Set `TriggerItem.enabled` and put the trigger into, or take it out of, the matching order (it keeps its place). Before #347 it left `enabled` alone, so it could not enable a trigger added with `enabled=False` (TR-2)
- `plugins.core.triggers:trigger.toggle.omit` - Set the omit flag; returns `True`, or `False` with an error logged for an unknown trigger
- `plugins.core.triggers:group.toggle.enable` - Enable or disable every trigger of a group (TR-4, fixed by #349); returns `True`, or `False` with an error logged for an unknown group (#354)
- `plugins.core.triggers:trigger.remove.for.owner` - Remove all triggers of an owner (`force=True`; a failing removal is logged and the rest still go, TR-8, #353; returns `False` if any removal failed, #354)
- `plugins.core.triggers:waiter.add` - Open a `LineWaiter` that queues MUD lines from now on (`owner_id`, `max_lines`); returns `None` with an error logged if there is no owner
- `plugins.core.triggers:waiter.remove.for.owner` - Close every waiter of an owner; returns how many
- `plugins.core.triggers:waiter.count` - The number of open waiters
- `plugins.core.triggers:line.get.next` - `(pattern, timeout=10.0)`: an awaitable that resolves to a `WaitResult` for the next matching line, or `None`
- `plugins.core.triggers:prompt.get.next` - `(timeout=10.0)`: an awaitable for the next prompt line
- `plugins.core.triggers:line.get.after.send` - `(command, pattern, timeout=10.0)`: send a command, then wait for a matching line

**Error contract (#354):** an API that is given something it cannot act on logs an error at ERROR through `log_to` and returns `False`; it does not raise. Success is `True`, except `trigger.get`, which returns the item, and `trigger.add`, which always returns a `TriggerAddResult(success, trigger)` (since #426; before it was a `(success, trigger)` tuple). Check `result.success` before using `result.trigger`. The waiter APIs (#548) log at ERROR and resolve to `None` for an invalid regex, a timeout of 0 or less, a wait on a closed waiter or a second wait on one waiter; they do not raise.

The name-taking APIs build the trigger id from the name and the owner; without `owner_id` the owner is the calling plugin.

## Built-in Triggers

The plugin adds four triggers without a regex:
- **beall**: its event is raised for every MUD line, before the regexes are tried
- **all**: its event is raised for every MUD line, after the regexes
- **emptyline**: its event is raised for a line whose text without colour codes is `""`
- **prompt**: its event is raised for a line marked `is_prompt`, after the held `on_prompt` events (#544)

They are added enabled, and the flag is not checked for them (TR-8, #353): each is raised when something is registered on its event, and not otherwise. `trigger.toggle.enable` on them raises no error. They are passed the `ev_to_client_data_modify` event's own record, so `trigger_name` and `trigger_id` are written into it ([Data Flow](data_flow.md), #230). A regex trigger `^$` never fires, because an empty line is not matched against the regexes.

## The `enabled` Setting

The plugin has an `enabled` setting. While it is False, `_eventcb_check_trigger` returns before matching, so no trigger fires and the built-in `beall`, `all`, `emptyline` and `prompt` events are not raised either. The plugin keeps the value in `_matching_enabled`, updated by `_eventcb_enabled_modify` on `ev_plugins.core.triggers_var_enabled_modified`, so no setting lookup runs per line. The settings plugin raises that event for every setting when a plugin loads, so a value saved as False applies at startup. (Before #356 the setting had no effect, TR-11.)

## Commands

### List Triggers
```
#bp.triggers.list [match]
```
Lists all triggers, optionally filtered

### Trigger Details
```
#bp.triggers.detail <trigger> [trigger...]
```
Shows detailed information about triggers. The argument is the trigger id (the `Id` column of `list`), not the name.

There is no command that lists trigger groups.

## Common Patterns

### Simple Trigger

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Trigger on tells
    result = self.api("plugins.core.triggers:trigger.add")(
        "tell_received",
        r"^(?P<sender>\w+) tells you '(?P<message>.*)'",
        owner_id=self.plugin_id
    )
    if not result.success:
        return

    # Register callback
    self.api("plugins.core.triggers:trigger.register")(
        "tell_received",
        self.handle_tell
    )

def handle_tell(self):
    """Handle received tell."""
    event_record = self.api("plugins.core.events:event.current.record.get")()
    matches = event_record["matches"]

    sender = matches["sender"]
    message = matches["message"]

    get_logger(self.plugin_id).info("Tell from %s: %s", sender, message)

    # Auto-respond
    if "help" in message.lower():
        self.send_help_to(sender)
```

### Combat Tracker

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Track damage dealt
    self.api("plugins.core.triggers:trigger.add")(
        "damage_dealt",
        r"You (?P<attack_type>hit|slash|pierce) (?P<target>\w+) for (?P<damage>\d+)",
        owner_id=self.plugin_id,
        argtypes={"damage": int}
    )

    self.api("plugins.core.triggers:trigger.register")(
        "damage_dealt",
        self.track_damage
    )

    # Track damage received
    self.api("plugins.core.triggers:trigger.add")(
        "damage_received",
        r"(?P<attacker>\w+) (?:hits|slashes|pierces) you for (?P<damage>\d+)",
        owner_id=self.plugin_id,
        argtypes={"damage": int}
    )

    self.api("plugins.core.triggers:trigger.register")(
        "damage_received",
        self.track_damage_taken
    )

def track_damage(self):
    """Track damage dealt."""
    event_record = self.api("plugins.core.events:event.current.record.get")()
    matches = event_record["matches"]

    self.combat_stats["damage_dealt"] += matches["damage"]
    self.combat_stats["attacks"] += 1

def track_damage_taken(self):
    """Track damage received."""
    event_record = self.api("plugins.core.events:event.current.record.get")()
    matches = event_record["matches"]

    self.combat_stats["damage_taken"] += matches["damage"]
```

### Gagging Lines

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Gag spam messages
    self.api("plugins.core.triggers:trigger.add")(
        "gag_spam",
        r"^\[SPAM\].*",
        owner_id=self.plugin_id,
        omit=True  # Don't send to client
    )
```

### Trigger Groups

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Create multiple related triggers
    triggers = [
        ("quest_start", r"Quest: You have been assigned"),
        ("quest_update", r"Quest: You have completed"),
        ("quest_complete", r"Quest: Congratulations"),
    ]

    for name, pattern in triggers:
        self.api("plugins.core.triggers:trigger.add")(
            name,
            pattern,
            owner_id=self.plugin_id,
            group="quests"
        )

# Toggle entire group
def enable_quest_tracking(self, enabled):
    """Enable/disable all quest triggers."""
    self.api("plugins.core.triggers:group.toggle.enable")(
        "quests",
        enabled
    )
```

`group.toggle.enable` enables or disables every trigger in the group (TR-4, fixed by #349).

### Stat Tracking

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Track stat changes
    self.api("plugins.core.triggers:trigger.add")(
        "hp_change",
        r"HP: (?P<current>\d+)/(?P<max>\d+) SP: (?P<sp>\d+)/(?P<maxsp>\d+)",
        owner_id=self.plugin_id,
        argtypes={
            "current": int,
            "max": int,
            "sp": int,
            "maxsp": int
        }
    )

    self.api("plugins.core.triggers:trigger.register")(
        "hp_change",
        self.update_stats
    )

def update_stats(self):
    """Update stat tracking."""
    event_record = self.api("plugins.core.events:event.current.record.get")()
    matches = event_record["matches"]

    self.stats.update({
        "hp": matches["current"],
        "max_hp": matches["max"],
        "sp": matches["sp"],
        "max_sp": matches["maxsp"]
    })

    # Raise event for other plugins
    self.api("plugins.core.events:event.raise")(
        "ev_myplugin_stats_updated",
        event_args={"stats": self.stats}
    )
```

## Best Practices

1. **Efficient Patterns**: Use specific patterns that start with literal text; avoid `.*` catchalls
2. **Named Groups**: Use named groups for clarity. Backreferences (`\1`, `(?P=name)`) work, as each trigger has its own regex
3. **Type Conversion**: Specify `argtypes` for numeric values, groups that may not take part in the match are left `None`; every other group must hold a value the type accepts, or the trigger fails and is logged (TR-7)
4. **Error Handling**: Handle missing groups gracefully, and check `success` from `trigger.add` before using the trigger
5. **Cleanup**: A plugin's triggers are removed when it is unloaded; no `uninitialize` code is needed for that. A callback may remove a trigger, including its own; matching walks a copy
6. **Testing**: Test regex patterns thoroughly, against the start of the line
7. **Groups**: `group.toggle.enable` toggles every trigger in a group
8. **Order**: Overlapping triggers all fire. Use `priority` (lower first) to order them and `stopevaluating` to keep later ones from firing

## Advanced Features

### Stop Evaluating

```python
# Stop every later trigger for this line
self.api("plugins.core.triggers:trigger.add")(
    "critical_error",
    r"FATAL ERROR:",
    owner_id=self.plugin_id,
    stopevaluating=True,
    priority=1  # Runs before the triggers with a higher number
)
```

`stopevaluating` ends the walk over the triggers when the trigger matched, so no later trigger runs for this line, whatever its regex. The `all` built-in is still raised. A trigger that does not match, or that fails, stops nothing.

### Match with Color

```python
# Match on colored text
self.api("plugins.core.triggers:trigger.add")(
    "red_warning",
    r".*WARNING.*",
    owner_id=self.plugin_id,
    matchcolor=True  # Match the colour-coded text
)
```

The regex is matched against the colour-coded text only, for example `@rWARNING@x: fire`, so `.*WARNING.*` matches and `^@rWARNING` matches a red `WARNING` at the start of a line. A `matchcolor` trigger does not match the plain text.

### GMCP Conditions

```python
self.api("plugins.core.triggers:trigger.add")(
    "hp_low",
    r"^You feel weak",
    owner_id=self.plugin_id,
    when={"Char.Vitals.hp": "<=50"}
)
```

The conditions are parsed and checked by `src/bastproxy/plugins/core/triggers/plugin/_conditions.py`, which resolves paths with `resolve_gmcp_path` in `src/bastproxy/libs/net/oob.py` (shared with `gmcp.value.get`) and reads the decoded GMCP cache through the `libs.net.protocols:gmcp.cache.get` API (never by import).

- **Paths**: the cache is keyed by package name (`Char.Vitals`). The path is split on `.`, package prefixes are tried longest to shortest, and the first one with a value is walked with the remaining segments as dict keys. Lookups are case-sensitive and lists are not indexed.
- **Missing values**: a missing package or key, a non-dict in the middle of the path, or a JSON null fails every condition, including `!=`.
- **Ordering operators** (`>`, `>=`, `<`, `<=`) compare numerically. The value must be a number or a numeric string, otherwise the condition fails. The operand must be a finite number.
- **`=` and `!=`** compare numerically when both sides are numeric (`=50` matches `50`, `50.0` and `"50"`), otherwise as text; booleans compare as `true` and `false`.
- **Validation**: a `when` that is not a dict, has a non-string path or condition, an empty path segment, no operator, no operand, or a non-numeric operand for an ordering operator is refused. `trigger.add` logs an error and returns `TriggerAddResult(False, None)`; `trigger.update` returns `False` and changes nothing.
- **Percentages**: not supported; `>50%` is refused. The key names for maximum values differ between MUDs (`maxhp`, `max_hp`), so compute the ratio in a callback.

### Dynamic Trigger Updates

`trigger.update` works since #348 (TR-3). It rejects an unknown key or a regex that does not compile and changes nothing. Example:

```python
# Update trigger without removing it
trigger_data = {
    "regex": r"new pattern (?P<value>\d+)",
    "enabled": True,
    "priority": 20
}

self.api("plugins.core.triggers:trigger.update")(
    "my_trigger",
    trigger_data
)
```

## Integration Points

- **Event System**: Each trigger has its own event, `event_<trigger_id>`, raised once per match. The event data holds `line`, `matches`, `trigger_name` and `trigger_id`. The `Event` object stays after the trigger is removed.
- **Plugin System**: On `ev_plugin_unloaded` the triggers plugin calls `trigger.remove.for.owner`. The events plugin has removed the owner's callbacks by then, so the removals are not refused (**verified**). The owner's entries in `trigger_groups` are removed with its triggers (TR-4, fixed by #349), and the removal passes `force=True` and continues past a failing one, so it does not depend on the events plugin running first (TR-8, fixed by #353). The triggers plugin itself cannot be reloaded (`can_reload_f = False`).
- **Data Flow**: `_eventcb_check_trigger` is a callback of the `ev_to_client_data_modify` event; see [Data Flow](data_flow.md)
- **Record System**: Each raise is a record; the built-in triggers share the outer event's record (#230)

## Trigger Properties

- `trigger_name`: The name given by the owner
- `trigger_id`: `t_<owner_id>_<trigger_name>`, the key in `triggers`
- `owner_id`: Plugin that owns trigger
- `original_regex`: The pattern as given; `regex`: equal to `original_regex`; `regex_id`: always `None`, kept for one release
- `enabled`: The value given at creation, updated by `trigger.toggle.enable` (TR-2, fixed by #347)
- `omit`: Hide matched lines from client
- `group`: Group name
- `argtypes`: Type conversions for captured groups
- `priority`: Orders matching, lower first; ties go in the order added (`order`)
- `matchcolor`: Match the trigger's own regex against the colour-coded text
- `when`: The GMCP conditions as given, or `None`; `conditions` holds the parsed form
- `stopevaluating`: Stop every later trigger for the line when this one matches
- `on_prompt`: Hold the trigger's events until the next prompt line (see [Prompt Triggers](#prompt-triggers))
- `event_name`: Event raised on match, always `event_<trigger_id>`
- `hits`: How many times the trigger's event was raised

## Regex Tips

1. **Escape Special Characters**: `\.`, `\*`, `\?`, etc.
2. **Use Raw Strings**: `r"pattern"` to avoid escaping backslashes
3. **Named Groups**: `(?P<name>pattern)` for clarity
4. **Non-Capturing**: `(?:pattern)` when you don't need the group
5. **Start/End Anchors**: `^` and `$` for line boundaries
6. **Character Classes**: `\d` (digit), `\w` (word), `\s` (whitespace)
7. **Quantifiers**: `*` (0+), `+` (1+), `?` (0-1), `{n,m}` (range)

## Performance Notes

The audit's figures for the old matcher are in [Triggers System Findings](triggers_system_findings.md#q4-what-does-a-line-cost). The measured cost of the current matcher, old against new, is in [ADR-0007](../decisions/0007-triggers-match-each-triggers-own-regex-in-priority-order.md).

- Each trigger's regex is compiled once, when it is added, and never again: there is no rebuild on add, remove, toggle or update. Adding 1,000 triggers one by one took 0.141 s (29.60 s with the combined regex).
- Each line costs one `match` per enabled trigger, until a `stopevaluating` trigger matches. At 100 triggers the matcher alone took 17.7 to 25.4 us per line (stubbed harness); the whole `ev_to_client_data_modify` raise for a line was lower than with the combined regex at 10, 100 and 1,000 triggers.
- A disabled trigger, and a trigger without a regex, cost nothing per line.
- The `beall`, `all` and `emptyline` events are raised only when something is registered on them. Raising `beall` and `all` for every line cost about 270 us per line in the old code.
- Matching runs on the event loop. Complex patterns may slow matching; use specific patterns over generic ones
