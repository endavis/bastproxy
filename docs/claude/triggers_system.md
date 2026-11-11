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
- When several triggers with **different** regexes match one line, **only the first one added fires**. `priority` is stored but not used (TR-1).
- `trigger.update` and `group.toggle.enable` do not work, and `trigger.toggle.enable` cannot enable a trigger that was added disabled (TR-2, TR-3, TR-4).

## Key Components

### TriggerItem Class
**Location**: `src/bastproxy/plugins/core/triggers/plugin/_triggers.py`

Represents a single trigger:

```python
class TriggerItem:
    def __init__(self, owner_id, trigger_name, regex, regex_id, original_regex,
                 enabled=True, group=None, omit=False, priority=100,
                 stopevaluating=False, argtypes=None, matchcolor=False,
                 trigger_id=None, event_name=None, original_regex_compiled=None):
        self.api = API(owner_id=f"{owner_id}:{trigger_name}")
        self.enabled = enabled                      # Set once, at creation (TR-2)
        self.owner_id = owner_id
        self.trigger_name = trigger_name
        self.regex = regex                          # The regex as a string, named groups made unnamed
        self.regex_id = regex_id                    # Shared regex id ("reg_<n>"), None without a regex
        self.original_regex = original_regex        # The regex as given, with named groups
        self.original_regex_compiled = original_regex_compiled
        self.group = group                          # Trigger group
        self.omit = omit                            # Gag matched lines
        self.priority = priority                    # Stored and displayed, not used (TR-1)
        self.stopevaluating = stopevaluating
        self.argtypes = argtypes                    # Type conversions
        self.matchcolor = matchcolor                # Second-stage match on colour-coded text
        self.hits = 0
        self.trigger_id = trigger_id                # "t_<owner_id>_<trigger_name>"
        self.event_name = f"event_{self.trigger_id}"  # The event_name argument is ignored
```

`raisetrigger(args)` counts a hit, sets `args["line"].sendtoclients = False` when `omit` is set, writes `trigger_name` and `trigger_id` into `args` and raises `event_name` with `args` as the event data.

### TriggersPlugin Class
**Location**: `src/bastproxy/plugins/core/triggers/plugin/_triggers.py`

Manages all triggers:

```python
class TriggersPlugin(BasePlugin):
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        self.can_reload_f = False       # The triggers plugin cannot be reloaded
        self.latest_regex_id = 0        # Counter behind "reg_<n>"
        self.beall_id = ...             # Ids of the three built-in triggers
        self.all_id = ...
        self.emptyline_id = ...
        self.triggers = {}              # trigger_id -> TriggerItem
        self.trigger_groups = {}        # group name -> list of trigger ids
        self.regexes = {}               # regex_id -> {"regex", "regex_id", "triggers", "hits"}
        self.regex_lookup_to_id = {}    # regex string -> regex_id (deduplication)
        self.created_regex = {"created_regex": "", "created_regex_compiled": ""}
```

`regexes[regex_id]["triggers"]` lists the **enabled** triggers on that regex; it, not `TriggerItem.enabled`, decides whether a regex is part of the combined pattern. Entries in `regexes`, `regex_lookup_to_id` and `trigger_groups` are never removed (TR-4, TR-10).

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
    priority=10,                                 # Stored, but not used for ordering (TR-1)
    group="secrets"                              # Trigger group
)
```

`trigger.add` returns `(True, trigger_item)` on success and a bare `False` on failure (a name the owner already uses, a regex that does not compile, no owner found), so `success, trigger = ...` raises `TypeError` on a failure (TR-9). The regex is matched with `match`, so it must match from the first character of the line: `You hit .* for (?P<damage>\d+) damage` above does not match `[combat] You hit orc for 5 damage`. Start a pattern with `.*` to match anywhere in the line.

### 2. Responding to Triggers

Register callbacks for trigger events:

```python
# Create trigger
success, trigger = self.api("plugins.core.triggers:trigger.add")(
    "hp_low",
    r"HP: (?P<current>\d+)/(?P<max>\d+)",
    owner_id=self.plugin_id,
    argtypes={"current": int, "max": int}
)

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
2. The `beall` trigger's event is raised.
3. The text is `line.noansi`: colour codes and, when the line has an MXP mode, MXP markup are removed.
4. If the text is `""`, the `emptyline` trigger's event is raised and no regex is tried. A line of colour codes only counts as empty; a line of spaces does not.
5. Otherwise the combined regex is matched from the start of the text. It is one alternation with a named group per distinct regex, `(?P<reg_1>...)|(?P<reg_2>...)`, in the order the regexes were first added. At most one alternative can match, so **one regex is chosen per line: the first added that matches**.
6. `process_match` goes through the triggers on that regex, in the order they were added. Each one's own compiled regex (`original_regex_compiled`, with its named groups) is matched again, against `line.colorcoded` for a `matchcolor` trigger and `line.noansi` otherwise.
7. On a match the named groups are converted with `argtypes`, stored as `matches`, and `raisetrigger` raises the trigger's event. `omit` sets `line.sendtoclients = False` before the callbacks run.
8. A trigger with `stopevaluating` ends the loop over the triggers on that regex.
9. The `all` trigger's event is raised.

What follows from this (each is **verified** in the findings page, Q1 and Q3):

- Two triggers with different regexes that both match a line do not both fire, and `priority` does not decide which one does (TR-1). Two triggers with the **same** regex (after named groups are made unnamed) both fire, in the order they were added.
- A `matchcolor` trigger must first match the text without colour codes in step 5 and then the colour-coded text in step 6, so a regex that contains a colour code never fires (TR-6).
- An `argtypes` conversion that raises, for example `int` on a group that did not take part in the match, ends the processing of that line: later triggers and `all` are skipped (TR-7).
- A callback that raises is logged by the event system and the other callbacks and triggers still run.
- Prompts and partial lines are matched like any other line.

### 4. The Combined Regex

- Each distinct regex is stored once in `regexes`, with the triggers that use it; named groups are made unnamed first with `re.sub(r"\?P\<.*?\>", "", regex)`, so two regexes that differ only in group names share an entry.
- `rebuild_regexes` joins every regex that has an enabled trigger into the combined pattern and compiles it. It runs on every add of an enabled trigger and on every remove or toggle that changes a regex's trigger list, so loading N triggers compiles N growing patterns (TR-10).
- The combination changes what some regexes mean: numeric backreferences such as `\1` point at another regex's group, a named backreference `(?P=name)` makes the combined pattern fail to compile, and a literal `\?P<x>` is cut out of the pattern (TR-5).
- When the combined pattern fails to compile, the error is logged and the previous compiled pattern stays in use: triggers added from then on never fire until the offending trigger is removed (TR-5).

## Common APIs

- `plugins.core.triggers:trigger.add` - Add a trigger; returns `(True, trigger_item)` or `False`
- `plugins.core.triggers:trigger.remove` - Remove a trigger. Refused (returns `False`) while a callback is registered on its event, unless `force=True`. Raises `KeyError` for a trigger without a regex (TR-8)
- `plugins.core.triggers:trigger.update` - Meant to update a trigger in place; every call for an existing trigger raises `TypeError` (TR-3)
- `plugins.core.triggers:trigger.get` - Get the `TriggerItem`, or `None`
- `plugins.core.triggers:trigger.register` - Register a callback on the trigger's event; takes a trigger name or id. Raises `KeyError` for an unknown trigger (TR-9)
- `plugins.core.triggers:trigger.unregister` - Unregister a callback; the same `KeyError`
- `plugins.core.triggers:trigger.toggle.enable` - Add the trigger to, or take it out of, its regex's list. It does not change `TriggerItem.enabled`, so it cannot enable a trigger added with `enabled=False`, and the `list` command and the stats keep showing the value from creation (TR-2)
- `plugins.core.triggers:trigger.toggle.omit` - Set the omit flag
- `plugins.core.triggers:group.toggle.enable` - Meant to toggle every trigger of a group; it changes nothing and logs "does not exist" for each member (TR-4)
- `plugins.core.triggers:trigger.remove.for.owner` - Remove all triggers of an owner (no `force`)

The name-taking APIs build the trigger id from the name and the owner; without `owner_id` the owner is the calling plugin.

## Built-in Triggers

The plugin adds three triggers without a regex:
- **beall**: its event is raised for every MUD line, before the regexes are tried
- **all**: its event is raised for every MUD line, after the regexes
- **emptyline**: its event is raised for a line whose text without colour codes is `""`

They are added with `enabled=False` and are raised anyway: the flag is not checked for them, and `trigger.toggle.enable` raises `KeyError` on them (TR-8). Both `beall` and `all` are raised for every line whether or not anything is registered on them (cost in the findings page, Q4). They are passed the `ev_to_client_data_modify` event's own record, so `trigger_name` and `trigger_id` are written into it ([Data Flow](data_flow.md), #230). A regex trigger `^$` never fires, because an empty line is not matched against the regexes.

## The `enabled` Setting

The plugin has an `enabled` setting, but changing it does not stop or start matching (**verified**, TR-11). `_eventcb_enabled_modify` registers and unregisters `_eventcb_check_trigger` on `ev_libs.net.mud_from_mud_event`, an event nothing raises, while the registration that does the work, on `ev_to_client_data_modify`, stays.

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
@RegisterPluginHook("initialize")
def _phook_initialize(self):
    # Trigger on tells
    success, trigger = self.api("plugins.core.triggers:trigger.add")(
        "tell_received",
        r"^(?P<sender>\w+) tells you '(?P<message>.*)'",
        owner_id=self.plugin_id
    )

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
@RegisterPluginHook("initialize")
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
@RegisterPluginHook("initialize")
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
@RegisterPluginHook("initialize")
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

The group is recorded, but `group.toggle.enable` does not toggle its triggers today (TR-4). Until that is fixed, call `trigger.toggle.enable` for each trigger name.

### Stat Tracking

```python
@RegisterPluginHook("initialize")
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
2. **Named Groups**: Use named groups for clarity. Do not use backreferences (`\1`, `(?P=name)`); they break in the combined regex (TR-5)
3. **Type Conversion**: Specify `argtypes` for numeric values, only on groups that always take part in the match and always hold a value the type accepts (TR-7)
4. **Error Handling**: Handle missing groups gracefully, and check the result of `trigger.add` before unpacking it
5. **Cleanup**: A plugin's triggers are removed when it is unloaded; no `uninitialize` code is needed for that. Do not remove a trigger from one of its own callbacks (TR-7)
6. **Testing**: Test regex patterns thoroughly, against the start of the line
7. **Groups**: Groups are recorded, but the group toggle does not work yet (TR-4)
8. **Order**: Do not rely on `priority`. Give triggers regexes that do not overlap, because only the first-added matching regex fires (TR-1)

## Advanced Features

### Stop Evaluating

```python
# Stop the triggers added later on the same regex
self.api("plugins.core.triggers:trigger.add")(
    "critical_error",
    r"FATAL ERROR:",
    owner_id=self.plugin_id,
    stopevaluating=True,
    priority=1  # Stored, not used (TR-1)
)
```

`stopevaluating` only ends the loop over the triggers that share this trigger's regex, so it affects triggers added after it with the same regex. Triggers with other regexes are not reached for this line in any case.

### Match with Color

```python
# Match on colored text
self.api("plugins.core.triggers:trigger.add")(
    "red_warning",
    r".*WARNING.*",
    owner_id=self.plugin_id,
    matchcolor=True  # Second-stage match on the colour-coded text
)
```

The regex has to match twice: the text without colour codes first (the combined regex), then the colour-coded text, for example `@RWARNING@x: fire`. `.*WARNING.*` matches both. A regex with a colour code in it, such as `^@RWARNING`, never fires, and neither does `^WARNING` on a line that starts with a colour code (TR-6).

### Dynamic Trigger Updates

`trigger.update` does not work today: for an existing trigger every call raises `TypeError: 'TriggerItem' object is not subscriptable` (TR-3). Remove the trigger and add it again instead. The intended use is:

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
- **Plugin System**: On `ev_plugin_unloaded` the triggers plugin calls `trigger.remove.for.owner`. The events plugin has removed the owner's callbacks by then, so the removals are not refused (**verified**). The owner's entries in `trigger_groups` stay, and one trigger without a regex stops the removal of the triggers after it (TR-4, TR-8). The triggers plugin itself cannot be reloaded (`can_reload_f = False`).
- **Data Flow**: `_eventcb_check_trigger` is a callback of the `ev_to_client_data_modify` event; see [Data Flow](data_flow.md)
- **Record System**: Each raise is a record; the built-in triggers share the outer event's record (#230)

## Trigger Properties

- `trigger_name`: The name given by the owner
- `trigger_id`: `t_<owner_id>_<trigger_name>`, the key in `triggers`
- `owner_id`: Plugin that owns trigger
- `original_regex`: The pattern as given; `regex`: the same with named groups made unnamed; `regex_id`: the shared regex entry
- `enabled`: The value given at creation; not updated by `trigger.toggle.enable` (TR-2)
- `omit`: Hide matched lines from client
- `group`: Group name
- `argtypes`: Type conversions for captured groups
- `priority`: Stored and shown by `detail`; not used (TR-1)
- `matchcolor`: Match the trigger's own regex against the colour-coded text
- `stopevaluating`: Stop the later triggers on the same regex
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

Measured figures are in [Triggers System Findings](triggers_system_findings.md#q4-what-does-a-line-cost).

- Each trigger's own regex is compiled once, when it is added; the combined pattern is compiled again on every change (TR-10)
- Triggers with the same pattern share one alternative of the combined pattern
- A trigger disabled with `trigger.toggle.enable` is out of the combined pattern once no enabled trigger uses its regex. A trigger added with `enabled=False` is never in it
- The `beall` and `all` events are raised for every line; that costs more than the matching itself at realistic trigger counts (TR-8)
- Matching runs on the event loop. Complex patterns may slow matching; use specific patterns over generic ones
