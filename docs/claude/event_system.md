# Event System

## Overview

The event system in bastproxy is a priority-based event dispatch system that allows plugins to register callbacks for specific events and process them in a defined order. Events can be raised by any component, and registered callbacks are executed based on their priority level (lower numbers execute first).

## Key Components

### Event Class
**Location**: `plugins/core/events/libs/_event.py` and `plugins/core/events/plugin/_event.py`

The `Event` class is the core of the event system. Each event has:
- **name**: Unique event identifier
- **created_by**: The plugin or module that created the event
- **description**: List of strings describing the event
- **arg_descriptions**: Dictionary of argument names and their descriptions
- **priority_dictionary**: Maps priorities to registered callbacks
- **raised_count**: Number of times the event has been raised
- **current_callback**: The currently executing callback
- **active_event**: The currently active ProcessRaisedEvent instance

```python
class Event:
    def __init__(self, name: str, created_by: str = "",
                 description: list | None = None,
                 arg_descriptions: dict[str, str] | None = None):
        self.name = name
        self.created_by = created_by
        self.description = description or []
        self.arg_descriptions = arg_descriptions or {}
        self.priority_dictionary = {}
        self.raised_count = 0
```

### EventDataRecord
**Location**: `plugins/core/events/libs/data/_event.py`

A data container for event arguments that extends `BaseDictRecord`:

```python
class EventDataRecord(BaseDictRecord):
    def __init__(self, owner_id: str = '', event_name: str = 'unknown',
                 data: dict | None = None):
        BaseDictRecord.__init__(self, owner_id, data)
        self.event_name = event_name
```

### ProcessRaisedEvent
**Location**: `plugins/core/events/libs/process/_raisedevent.py`

A record type that tracks the execution of a raised event:

```python
class ProcessRaisedEvent(BaseRecord):
    def __init__(self, event: "Event", event_data: "EventDataRecord",
                 called_from=""):
        self.event = event
        self.called_from = called_from
        self.event_name = event.name
        self.event_data = event_data
        self.times_invoked = 0
```

### RegisterToEvent Decorator
**Location**: `plugins/core/events/libs/_utils.py`

Decorator class for registering functions to events:

```python
class RegisterToEvent:
    def __init__(self, **kwargs):
        # kwargs include:
        #   - event_name: the event to register to
        #   - priority: callback execution priority (default: 50)
        self.registration_args = {"event_name": "", "priority": 50} | kwargs
```

### EventsPlugin
**Location**: `plugins/core/events/plugin/_events.py`

The core plugin that manages the event system, tracking all events and registrations.

## How It Works

### 1. Event Registration

Plugins register callbacks to events using the `RegisterToEvent` decorator:

```python
@RegisterToEvent(event_name="ev_to_mud_data_modify", priority=50)
def _eventcb_handle_data(self):
    event_record = self.api("plugins.core.events:get.current.event.record")()
    # Process the event data
```

The decorator marks the function with event registration metadata, which is processed during plugin initialization.

### 2. Event Creation

Events are created using the API:

```python
self.api("plugins.core.events:add.event")(
    "ev_my_custom_event",
    "plugins.my.plugin",
    description=["Event when something happens"],
    arg_descriptions={
        "data": "The data associated with the event",
        "client_id": "The client that triggered the event"
    }
)
```

### 3. Event Raising

Events are raised by calling the `raise.event` API:

```python
self.api("plugins.core.events:raise.event")(
    "ev_my_custom_event",
    event_args={"data": some_data, "client_id": client_id}
)
```

When an event is raised:
1. A `ProcessRaisedEvent` instance is created
2. The event data is wrapped in an `EventDataRecord` if it's not already
3. Callbacks are executed in priority order (sorted by priority number)
4. Each callback at a priority level is executed once
5. If new callbacks are registered during execution, they are processed in subsequent iterations
6. The event is reset after all callbacks complete

### 4. Priority-Based Execution

Callbacks are organized by priority (default: 50):
- Lower numbers execute first (e.g., priority 1 before priority 50)
- All callbacks at a given priority are executed before moving to the next priority
- The system uses a while loop to handle callbacks registered during event execution

```python
def raise_priority(self, priority, already_done: bool) -> bool:
    found = False
    for call_back in list(self.priority_dictionary[priority].keys()):
        if (call_back in self.priority_dictionary[priority] and
            not self.priority_dictionary[priority][call_back] and
            self.current_callback != call_back):
            self.current_callback = call_back
            self.priority_dictionary[priority][call_back] = True
            call_back.execute()
            found = True
    return found
```

### 5. Event Stack

The event system maintains a stack of currently active events:
- Accessible via `api("plugins.core.events:get.event.stack")()`
- Used to track the chain of events that led to the current execution
- Helpful for debugging and understanding event flow

### 6. Current Event Record

Callbacks can access the current event's data record:

```python
event_record = self.api("plugins.core.events:get.current.event.record")()
if event_record:
    # Access event data
    data = event_record["some_key"]
    # Modify event data
    event_record["some_key"] = new_value
```

## Important Files

### Core Event System
- `plugins/core/events/libs/_event.py` - Event class implementation
- `plugins/core/events/libs/process/_raisedevent.py` - ProcessRaisedEvent class
- `plugins/core/events/libs/data/_event.py` - EventDataRecord class
- `plugins/core/events/libs/_utils.py` - RegisterToEvent decorator

### Event Plugin
- `plugins/core/events/plugin/_events.py` - EventsPlugin that manages events
- `plugins/core/events/__init__.py` - Plugin metadata and exports

## Code Examples

### Creating and Raising an Event

```python
# Create the event
self.api("plugins.core.events:add.event")(
    "ev_data_processed",
    self.plugin_id,
    description=["Raised when data has been processed"],
    arg_descriptions={
        "processed_data": "The data after processing",
        "status": "Processing status"
    }
)

# Raise the event later
self.api("plugins.core.events:raise.event")(
    "ev_data_processed",
    event_args={
        "processed_data": result,
        "status": "success"
    }
)
```

### Registering to an Event

```python
@RegisterToEvent(event_name="ev_to_client_data_modify", priority=1)
def _eventcb_process_client_data(self):
    """Process data before it's sent to the client."""
    event_record = self.api("plugins.core.events:get.current.event.record")()
    if event_record:
        # Access the line being sent to the client
        line = event_record["line"]
        # Modify it if needed
        line.line = "Modified: " + line.line
```

### Checking Event Registration

```python
# Check if a function is registered to an event
is_registered = self.api("plugins.core.events:is.registered.to.event")(
    "ev_my_event",
    my_callback_function
)

# Get event details
event_details = self.api("plugins.core.events:get.event.detail")("ev_my_event")
```

### Unregistering from an Event

```python
self.api("plugins.core.events:unregister.from.event")(
    "ev_my_event",
    my_callback_function
)
```

## Integration Points

### Plugin System
- Plugins automatically register their `@RegisterToEvent` decorated methods during initialization
- The `EventsPlugin` listens to `ev_plugin_loaded` and `ev_plugin_unloaded` to manage registrations
- When a plugin unloads, all its event registrations are removed

### Data Flow
- Events are the primary mechanism for data flow through the system
- Key data flow events:
  - `ev_to_mud_data_modify` - Data from client to mud
  - `ev_to_client_data_modify` - Data from mud to client
  - `ev_from_mud_event` - Raw data received from mud
  - `ev_from_client_event` - Raw data received from client

### Command System
- The command system uses events to track command execution
- The `plugins.core.commands` plugin listens to `ev_plugin_loaded` to discover new commands

### Logging
- The event system integrates with logging to track event raises and callback execution
- Debug logs show event execution flow and timing

## Unique Patterns

### Dynamic Event Registration During Execution

The event system handles callbacks registered while an event is being raised:

```python
priorities_done = []
found_callbacks = True
count = 0
while found_callbacks:
    count = count + 1
    found_callbacks = False
    if keys := list(self.event.priority_dictionary.keys()):
        keys = sorted(keys)
        for priority in keys:
            found_callbacks = self.event.raise_priority(
                priority, priority in priorities_done
            )
            priorities_done.append(priority)
```

If the loop executes more than twice, a warning is logged indicating that callbacks were added during execution.

### Event Data Mutation Tracking

Event data records can be modified by callbacks, with changes tracked through the record system:

```python
event_record["key"] = new_value
event_record.addupdate("Modify", "Changed key to new_value")
```

This allows debugging of how event data changes through the callback chain.

### Event History

The `Event` class maintains a dictionary of raised events:

```python
self.raised_events = {}  # Maps UUID to ProcessRaisedEvent instances
```

This allows retrospective analysis of event execution.

## Common Event Names

### Core Events
- `ev_baseplugin_patched` - Base plugin class was reloaded
- `ev_plugin_loaded` - A plugin was loaded
- `ev_plugin_unloaded` - A plugin was unloaded
- `ev_plugin_save` - A plugin should save its state
- `ev_plugin_reset` - A plugin should reset to defaults

### Data Flow Events
- `ev_to_mud_data_modify` - Modify data before sending to mud
- `ev_to_client_data_modify` - Modify data before sending to client
- `ev_from_mud_event` - Raw data received from mud
- `ev_from_client_event` - Raw data received from client

### Network Events
- `ev_libs.net.mud_mudconnect` - Connected to mud
- `ev_libs.net.mud_from_mud_event` - Data received from mud

### Proxy Events
- `ev_bastproxy_proxy_ready` - Proxy is ready to accept connections
- `ev_plugins.core.proxy_shutdown` - Proxy is shutting down
- `ev_plugins.core.events_all_events_registered` - All events registered at startup

### Client Events
- `ev_plugins.core.clients_client_logged_in` - A client logged in to the proxy
