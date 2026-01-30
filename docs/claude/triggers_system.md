# Triggers System

## Overview

The triggers system in bastproxy provides pattern matching on MUD output using regular expressions. When text from the MUD matches a trigger's pattern, an event is raised that plugins can respond to. Triggers support named capture groups, priority ordering, line omission, and efficient regex compilation.

## Key Components

### TriggerItem Class
**Location**: `plugins/core/triggers/plugin/_triggers.py`

Represents a single trigger:

```python
class TriggerItem:
    def __init__(self, owner_id, trigger_name, regex, regex_id, original_regex, **kwargs):
        self.owner_id = owner_id
        self.trigger_name = trigger_name
        self.regex = regex                          # Compiled regex
        self.regex_id = regex_id                    # Shared regex ID
        self.original_regex = original_regex        # With named groups
        self.enabled = True
        self.omit = False                           # Gag matched lines
        self.group = ""                             # Trigger group
        self.argtypes = {}                          # Type conversions
        self.matchcolor = False                     # Match on colored text
        self.stopevaluating = False                 # Stop after match
        self.event_name = ""                        # Event to raise
```

### TriggersPlugin Class
**Location**: `plugins/core/triggers/plugin/_triggers.py`

Manages all triggers:

```python
class TriggersPlugin(BasePlugin):
    def __init__(self):
        self.triggers = {}              # All triggers
        self.regexes = {}               # Compiled regexes
        self.trigger_groups = {}        # Grouped triggers
        self.regex_lookup_to_id = {}    # Regex deduplication
```

## How It Works

### 1. Creating Triggers

Create triggers via API:

```python
# Simple trigger
self.api("plugins.core.triggers:trigger.add")(
    "hp_warning",                                # Trigger name
    r"HP: (\d+)/(\d+)",                         # Regex pattern
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
    priority=10,                                 # High priority
    group="secrets"                              # Trigger group
)
```

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
    event_record = self.api("plugins.core.events:get.current.event.record")()
    matches = event_record["matches"]

    current = matches["current"]
    max_hp = matches["max"]

    if current < (max_hp * 0.2):  # Below 20%
        LogRecord(
            f"WARNING: Low HP! {current}/{max_hp}",
            level="warning",
            sources=[self.plugin_id]
        )()
        # Take action (heal, flee, etc.)
        self.emergency_heal()
```

### 3. Trigger Matching

When data comes from MUD:
1. System checks all enabled triggers
2. Compiles multiple regexes efficiently
3. Matches against line (with or without color)
4. Extracts named groups
5. Raises trigger event with matches
6. Optionally omits line from client

### 4. Regex Optimization

The system optimizes regex matching:
- Combines multiple patterns into one compiled regex
- Deduplicates identical patterns
- Uses named groups to identify which trigger matched
- Rebuilds compiled regex when triggers change

## Common APIs

- `plugins.core.triggers:trigger.add` - Add a trigger
- `plugins.core.triggers:trigger.remove` - Remove a trigger
- `plugins.core.triggers:trigger.update` - Update trigger without recreating
- `plugins.core.triggers:trigger.get` - Get trigger object
- `plugins.core.triggers:trigger.register` - Register callback to trigger
- `plugins.core.triggers:trigger.unregister` - Unregister callback
- `plugins.core.triggers:trigger.toggle.enable` - Enable/disable trigger
- `plugins.core.triggers:trigger.toggle.omit` - Toggle line omission
- `plugins.core.triggers:group.toggle.enable` - Enable/disable trigger group
- `plugins.core.triggers:remove.data.for.owner` - Remove all triggers for plugin

## Built-in Triggers

The system provides automatic triggers:
- **beall**: Fires before any line is processed
- **all**: Fires after all triggers on every line
- **emptyline**: Fires on empty lines

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
Shows detailed information about triggers

### List Groups
```
#bp.triggers.listgroups
```
Lists all trigger groups

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
    event_record = self.api("plugins.core.events:get.current.event.record")()
    matches = event_record["matches"]

    sender = matches["sender"]
    message = matches["message"]

    LogRecord(
        f"Tell from {sender}: {message}",
        level="info",
        sources=[self.plugin_id]
    )()

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
    event_record = self.api("plugins.core.events:get.current.event.record")()
    matches = event_record["matches"]

    self.combat_stats["damage_dealt"] += matches["damage"]
    self.combat_stats["attacks"] += 1

def track_damage_taken(self):
    """Track damage received."""
    event_record = self.api("plugins.core.events:get.current.event.record")()
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
    event_record = self.api("plugins.core.events:get.current.event.record")()
    matches = event_record["matches"]

    self.stats.update({
        "hp": matches["current"],
        "max_hp": matches["max"],
        "sp": matches["sp"],
        "max_sp": matches["maxsp"]
    })

    # Raise event for other plugins
    self.api("plugins.core.events:raise.event")(
        "ev_myplugin_stats_updated",
        event_args={"stats": self.stats}
    )
```

## Best Practices

1. **Efficient Patterns**: Use specific patterns, avoid `.* catchalls
2. **Named Groups**: Use named groups for clarity
3. **Type Conversion**: Specify `argtypes` for numeric values
4. **Error Handling**: Handle missing groups gracefully
5. **Cleanup**: Remove triggers in uninitialize hook
6. **Testing**: Test regex patterns thoroughly
7. **Groups**: Use trigger groups for related triggers
8. **Priority**: Use priority to control matching order

## Advanced Features

### Stop Evaluating

```python
# Stop checking other triggers after this matches
self.api("plugins.core.triggers:trigger.add")(
    "critical_error",
    r"FATAL ERROR:",
    owner_id=self.plugin_id,
    stopevaluating=True,
    priority=1  # Check first
)
```

### Match with Color

```python
# Match on colored text
self.api("plugins.core.triggers:trigger.add")(
    "red_warning",
    r".*WARNING.*",
    owner_id=self.plugin_id,
    matchcolor=True  # Match including color codes
)
```

### Dynamic Trigger Updates

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

- **Event System**: Triggers raise events for matches
- **Plugin System**: Triggers removed when plugin unloads
- **Data Flow**: Integrates with `ev_to_client_data_modify` event
- **Record System**: Lines and matches tracked in records

## Trigger Properties

- `trigger_name`: Trigger identifier
- `owner_id`: Plugin that owns trigger
- `regex`: Pattern to match
- `enabled`: Whether trigger is active
- `omit`: Hide matched lines from client
- `group`: Group name for batch operations
- `argtypes`: Type conversions for captured groups
- `priority`: Match priority (lower = earlier)
- `matchcolor`: Match with or without color codes
- `stopevaluating`: Stop checking triggers after match
- `event_name`: Event raised on match

## Regex Tips

1. **Escape Special Characters**: `\.`, `\*`, `\?`, etc.
2. **Use Raw Strings**: `r"pattern"` to avoid escaping backslashes
3. **Named Groups**: `(?P<name>pattern)` for clarity
4. **Non-Capturing**: `(?:pattern)` when you don't need the group
5. **Start/End Anchors**: `^` and `$` for line boundaries
6. **Character Classes**: `\d` (digit), `\w` (word), `\s` (whitespace)
7. **Quantifiers**: `*` (0+), `+` (1+), `?` (0-1), `{n,m}` (range)

## Performance Notes

- Triggers are compiled once and reused
- Multiple triggers with same pattern share compiled regex
- Disabled triggers don't impact performance
- Complex patterns may slow matching
- Use specific patterns over generic ones
