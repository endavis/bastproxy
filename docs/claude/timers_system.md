# Timers System

## Overview

The timers system in bastproxy provides scheduled execution of functions at specified intervals. Timers can fire at regular intervals, at specific times of day, or as one-time events. The system handles all timing logic asynchronously and integrates with the plugin lifecycle.

## Key Components

### Timer Class
**Location**: `plugins/core/timers/plugin/_timers.py`

Represents a single timer:

```python
class Timer(Callback):
    def __init__(self, name, func, seconds, plugin_id, enabled=True, **kwargs):
        self.name = name                    # Timer name
        self.func = func                    # Function to execute
        self.seconds = seconds              # Interval in seconds
        self.plugin_id = plugin_id          # Owning plugin
        self.enabled = enabled              # Whether timer is active
        self.onetime = False                # Fire only once
        self.time = ""                      # Specific time (e.g., "1430")
        self.raised_count = 0               # Times fired
        self.next_fire_datetime = None      # Next fire time
```

### TimersPlugin Class
**Location**: `plugins/core/timers/plugin/_timers.py`

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

Create timers via API:

```python
# Simple interval timer
self.api("plugins.core.timers:add")(
    "my_timer",                 # Timer name
    self.my_function,           # Function to call
    60,                         # Fire every 60 seconds
    owner_id=self.plugin_id
)

# Specific time of day
self.api("plugins.core.timers:add")(
    "daily_backup",
    self.do_backup,
    86400,                      # 24 hours
    owner_id=self.plugin_id,
    time="0300"                 # Fire at 3:00 AM
)

# One-time timer
self.api("plugins.core.timers:add")(
    "delayed_action",
    self.delayed_func,
    30,                         # 30 seconds from now
    owner_id=self.plugin_id,
    onetime=True
)
```

### 2. Timer Function

Timer functions receive no arguments:

```python
def my_timer_function(self):
    """Called when timer fires."""
    LogRecord(
        "Timer fired",
        level="info",
        sources=[self.plugin_id]
    )()

    # Perform timed action
    self.check_for_updates()
```

### 3. Timer Management

Control timers programmatically:

```python
# Enable/disable
self.api("plugins.core.timers:toggle")(timer_name, enabled=True)

# Remove timer
self.api("plugins.core.timers:remove")(timer_name, owner_id=self.plugin_id)

# Get timer info
timer = self.api("plugins.core.timers:get")(timer_name)
```

### 4. Execution

The timers plugin:
1. Runs an async task checking for timers
2. Fires timers when their time comes
3. Calculates next fire time
4. Removes one-time timers after firing
5. Tracks statistics

## Common APIs

- `plugins.core.timers:add` - Add a timer
- `plugins.core.timers:remove` - Remove a timer
- `plugins.core.timers:toggle` - Enable/disable a timer
- `plugins.core.timers:get` - Get timer object
- `plugins.core.timers:remove.data.for.plugin` - Remove all timers for a plugin

## Commands

### List Timers
```
#bp.timers.list [match]
```
Lists all timers, optionally filtered by name

### Timer Details
```
#bp.timers.detail <timer> [timer...]
```
Shows detailed information about specific timers

### Toggle Logging
```
#bp.timers.log <timername>
```
Toggle whether timer fires are logged

## Common Patterns

### Regular Interval Timer

```python
@RegisterPluginHook("initialize")
def _phook_initialize(self):
    # Check for updates every 5 minutes
    self.api("plugins.core.timers:add")(
        "update_check",
        self.check_updates,
        300,  # 5 minutes
        owner_id=self.plugin_id
    )

def check_updates(self):
    """Check for available updates."""
    updates = self.api("plugins.update.service:check")()
    if updates:
        LogRecord(
            f"Updates available: {updates}",
            level="info",
            sources=[self.plugin_id]
        )()
```

### Daily Timer

```python
@RegisterPluginHook("initialize")
def _phook_initialize(self):
    # Backup database daily at 3 AM
    self.api("plugins.core.timers:add")(
        "daily_backup",
        self.backup_database,
        86400,                  # 24 hours
        owner_id=self.plugin_id,
        time="0300"            # 3:00 AM
    )

def backup_database(self):
    """Perform daily backup."""
    backup_file = self.create_backup()
    LogRecord(
        f"Database backed up to {backup_file}",
        level="info",
        sources=[self.plugin_id]
    )()
```

### One-Time Delayed Action

```python
def process_with_delay(self, data):
    """Process data after a delay."""
    # Store data for later processing
    self.pending_data = data

    # Create one-time timer
    self.api("plugins.core.timers:add")(
        f"process_{data.id}",
        self.process_pending,
        30,                     # 30 seconds delay
        owner_id=self.plugin_id,
        onetime=True
    )

def process_pending(self):
    """Process the pending data."""
    self.process(self.pending_data)
    self.pending_data = None
```

### Conditional Timer

```python
@RegisterPluginHook("initialize")
def _phook_initialize(self):
    # Add timer
    self.api("plugins.core.timers:add")(
        "conditional_check",
        self.conditional_action,
        60,
        owner_id=self.plugin_id,
        enabled=False  # Start disabled
    )

@RegisterToEvent(event_name="ev_plugins_myplugin_var_feature_enabled_modified")
def _eventcb_feature_changed(self):
    """Enable/disable timer based on setting."""
    event_record = self.api("plugins.core.events:get.current.event.record")()
    enabled = event_record["newvalue"]

    self.api("plugins.core.timers:toggle")(
        "conditional_check",
        enabled=enabled
    )
```

## Best Practices

1. **Unique Names**: Use descriptive, unique timer names
2. **Cleanup**: Remove timers in uninitialize hook
3. **Error Handling**: Catch exceptions in timer functions
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
- `last_fired_datetime`: When last fired
- `next_fire_datetime`: When will fire next
- `log`: Whether to log fires

## Notes

- All times are in UTC
- Timers persist across plugin reloads if properly managed
- One-time timers are automatically removed after firing
- Disabled timers don't fire but remain registered
- Timer functions should be fast and non-blocking
