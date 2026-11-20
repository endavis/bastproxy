---
title: Timers System
description: Scheduling recurring and one-shot timers from plugins
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - timers
---

# Timers System

## Overview

The timers system in bastproxy provides scheduled execution of functions at specified intervals. Timers can fire at regular intervals, at specific times of day, or as one-time events. The system handles all timing logic asynchronously and integrates with the plugin lifecycle.

## Key Components

### Timer Class
**Location**: `src/bastproxy/plugins/core/timers/plugin/_timers.py`

Represents a single timer:

```python
class Timer(Callback):
    def __init__(self, name, func, seconds, plugin_id, enabled=True, **kwargs):
        self.name = name                    # Timer name
        self.func = func                    # Function to execute
        self.seconds = seconds              # Interval in seconds
        self.owner_id = plugin_id           # Owning plugin
        self.enabled = enabled              # Whether timer is active
        self.onetime = False                # Fire only once
        self.time = ""                      # Time of day, "HHMM" in UTC (e.g., "1430")
        self.raised_count = 0               # Times fired
        self.last_fired_datetime = None     # When it last fired
        self.next_fire_datetime = ...       # Next fire time
```

### TimersPlugin Class
**Location**: `src/bastproxy/plugins/core/timers/plugin/_timers.py`

Manages all timers:

```python
class TimersPlugin(BasePlugin):
    def __init__(self):
        self.timer_events = {}              # Timers by fire time
        self.timer_lookup = {}              # Name -> Timer mapping
        self.overall_fire_count = 0         # Total fires
```

## How It Works

### 1. Creating Timers

Create timers with `timer.add(name, func, seconds, **kwargs)`. It returns the `Timer`, or `None` when the timer is refused (an error is logged). The owner is the calling plugin; pass `plugin_id=` to set it explicitly.

```python
# Simple interval timer
self.api("plugins.core.timers:timer.add")(
    "my_timer",                 # Timer name
    self.my_function,           # Function to call
    60,                         # Fire every 60 seconds
)

# Specific time of day
self.api("plugins.core.timers:timer.add")(
    "daily_backup",
    self.do_backup,
    86400,                      # Required, but a time= timer fires daily
    time="0300",                # Fire at 03:00 UTC
)

# One-time timer
self.api("plugins.core.timers:timer.add")(
    "delayed_action",
    self.delayed_func,
    30,                         # 30 seconds from now
    onetime=True,
)
```

- **`seconds`** must be a number (not a bool), finite, and at least 1. Timers fire on whole-second slots, so sub-second intervals are not supported.
- **Keyword arguments:** `onetime` (fire once, then remove), `time` ("HHMM", UTC), `enabled` (default `True`), `log` (log each fire, default `True`), `unique`, `plugin_id`.
- **Names are global.** Adding a timer under a name already in use replaces that timer (it is unscheduled first). With `unique=True` the add is refused instead and the existing timer is kept.

### 2. Timer Function

Timer functions receive no arguments:

```python
def my_timer_function(self):
    """Called when timer fires."""
    get_logger(self.plugin_id).info("Timer fired")

    # Perform timed action
    self.check_for_updates()
```

### 3. Timer Management

Control timers programmatically:

```python
# Enable/disable
self.api("plugins.core.timers:timer.toggle")(timer_name, True)

# Remove a timer
self.api("plugins.core.timers:timer.remove")(timer_name)

# Check a timer
if self.api("plugins.core.timers:timer.exists")(timer_name):
    next_fire = self.api("plugins.core.timers:timer.next.fire.get")(timer_name)
```

### 4. Execution

The timers plugin:
1. Runs an async task that checks for due timers about five times a second
2. Fires each due, enabled timer and records `last_fired_datetime`; an error in a timer is logged and the other timers still fire
3. Calculates the next fire time: an interval timer fires at its previous due time plus `seconds` (fires missed while the proxy was busy are skipped, not replayed), and a `time=` timer fires at the same time of day the next day
4. Removes one-time timers after firing, and leaves a timer removed if its function removed or replaced it
5. Tracks statistics

## Common APIs

- `plugins.core.timers:timer.add` - Add a timer
- `plugins.core.timers:timer.remove` - Remove a timer
- `plugins.core.timers:timer.toggle` - Enable/disable a timer
- `plugins.core.timers:timer.exists` - Check whether a timer exists
- `plugins.core.timers:timer.next.fire.get` - Get the next fire time for a timer
- `plugins.core.timers:timer.remove.for.plugin` - Remove all timers for a plugin

## Commands

### List Timers
```
#bp.core.timers.list [match]
```
Lists all timers, optionally filtered by name

### Timer Details
```
#bp.core.timers.detail <timer> [timer...]
```
Shows detailed information about specific timers

### Toggle Logging
```
#bp.core.timers.log <timername>
```
Toggle whether timer fires are logged

## Common Patterns

### Regular Interval Timer

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Check for updates every 5 minutes
    self.api("plugins.core.timers:timer.add")(
        "update_check",
        self.check_updates,
        300,  # 5 minutes
    )

def check_updates(self):
    """Check for available updates."""
    updates = self.api("plugins.update.service:check")()
    if updates:
        get_logger(self.plugin_id).info("Updates available: %s", updates)
```

### Daily Timer

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Backup database daily at 03:00 UTC
    self.api("plugins.core.timers:timer.add")(
        "daily_backup",
        self.backup_database,
        86400,                  # required; a time= timer fires daily
        time="0300",            # 03:00 UTC
    )

def backup_database(self):
    """Perform daily backup."""
    backup_file = self.create_backup()
    get_logger(self.plugin_id).info("Database backed up to %s", backup_file)
```

### One-Time Delayed Action

```python
def process_with_delay(self, data):
    """Process data after a delay."""
    # Store data for later processing
    self.pending_data = data

    # Create one-time timer
    self.api("plugins.core.timers:timer.add")(
        f"process_{data.id}",
        self.process_pending,
        30,                     # 30 seconds delay
        onetime=True,
    )

def process_pending(self):
    """Process the pending data."""
    self.process(self.pending_data)
    self.pending_data = None
```

### Conditional Timer

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self):
    # Add timer
    self.api("plugins.core.timers:timer.add")(
        "conditional_check",
        self.conditional_action,
        60,
        enabled=False,  # Start disabled
    )

@RegisterToEvent(event_name="ev_plugins_myplugin_var_feature_enabled_modified")
def _eventcb_feature_changed(self):
    """Enable/disable timer based on setting."""
    event_record = self.api("plugins.core.events:event.current.record.get")()
    enabled = event_record["newvalue"]

    self.api("plugins.core.timers:timer.toggle")("conditional_check", enabled)
```

## Best Practices

1. **Unique Names**: Timer names are global; prefix them with something plugin-specific, and pass `unique=True` when another add must not replace the timer
2. **Cleanup**: Timers are removed when their plugin unloads; remove a timer earlier with `timer.remove` when it is no longer needed
3. **Error Handling**: Catch exceptions in timer functions (an uncaught one is logged, and the timer stays scheduled)
4. **Performance**: Keep timer functions fast
5. **Logging**: Use `log=False` for high-frequency timers to reduce log spam

## Integration Points

- **Plugin System**: Timers automatically removed when plugin unloads
- **Event System**: Timers can raise events
- **Async**: Runs as async task, non-blocking
- **Settings**: Can be controlled by settings

## Timer Properties

- `name`: Timer identifier
- `owner_id`: Plugin that owns the timer
- `seconds`: Interval between fires
- `enabled`: Whether timer is active
- `onetime`: Fire only once
- `time`: Specific time of day (optional)
- `raised_count`: Number of times fired
- `last_fired_datetime`: When the timer last fired (UTC, set when an enabled timer fires)
- `next_fire_datetime`: When it will fire next (a disabled timer is still rescheduled)
- `log`: Whether to log fires

## Notes

- All times are in UTC, including `time="HHMM"`
- Timers do not survive a plugin reload: they are removed when the plugin unloads, so add them again when the plugin loads
- One-time timers are automatically removed after firing
- Disabled timers don't fire but remain registered
- Timer functions should be fast and non-blocking
