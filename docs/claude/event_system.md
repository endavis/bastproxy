---
title: Event System
description: Priority-based event registration and dispatch between plugins
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - events
---

# Event System

## Overview

The event system in bastproxy is a priority-based event dispatch system that allows plugins to register callbacks for specific events and process them in a defined order. Events can be raised by any component, and registered callbacks are executed based on their priority level (lower numbers execute first).

The defects found by the event system audit (#275 to #285) are fixed; [Event System Findings](event_system_findings.md) records each one and its fix.

## Key Components

### Event Class
**Location**: `src/bastproxy/plugins/core/events/plugin/_event.py`

The `Event` class is the core of the event system. Each event has:
- **name**: Unique event identifier
- **created_by**: The plugin or module that created the event
- **description**: List of strings describing the event
- **arg_descriptions**: Dictionary of argument names and their descriptions
- **priority_dictionary**: Maps priorities to registered callbacks
- **raised_count**: Number of times the event has been raised
- **current_callback**: The currently executing callback. `raise_event` saves it on entry and restores it when the raise ends, so a nested raise of the same event gives back the outer raise's callback and the outermost raise leaves `None` (an unloaded plugin is not kept alive)
- **active_event**: The ProcessRaisedEvent being processed; saved and restored by `raise_event` like `current_callback`, so after a nested raise of the same event it is the outer raise again (#281)

```python
class Event:
    MAX_RAISED_EVENTS: int = 10

    def __init__(self, name: str, created_by: str = "",
                 description: list | None = None,
                 arg_descriptions: dict[str, str] | None = None):
        self.name: str = name
        self.created_by: str = created_by
        self.description = description or []
        self.arg_descriptions = arg_descriptions or {}

        self.owner_id: str = f"plugins.core.events:{self.name}"
        self.api = API(owner_id=self.owner_id)
        self.priority_dictionary = {}
        self.raised_count = 0
        self.raised_events: OrderedDict[str, ProcessRaisedEvent] = OrderedDict()
        self.current_callback = None
        self.active_event = None
```

`priority_dictionary` maps a priority to a dictionary of `Callback` objects, each mapped to a flag that nothing reads: whether a callback has run is tracked per raise in `ProcessRaisedEvent.done` (a set, fresh for every item of a `data_list` raise), so a raise of the event from one of its own callbacks runs its own callbacks fully and leaves the outer raise untouched (#281). `Event.register(func, func_owner_id, prio=50)` adds a callback; `raise_event(data, actor, data_list=None, key_name=None)` raises the event, where `actor` is the owner id of the caller (see Actors below). Callbacks are called synchronously, so `register` rejects an `async def` callback: it logs an error naming the function and the event, returns `False` and registers nothing (#277).

### EventDataRecord
**Location**: `src/bastproxy/plugins/core/events/libs/data/_event.py`

A data container for event arguments that extends `BaseDictRecord`, a pydatatracker `TrackedDict` with the record interface:

```python
class EventDataRecord(BaseDictRecord):
    def __init__(self, owner_id: str = '', event_name: str = 'unknown',
                 data: dict | None = None):
        self.event_name = event_name
        self._received = False
        BaseDictRecord.__init__(self, owner_id, data)

    def add_receiving_event(self, raised) -> None: ...
```

- `add_receiving_event(raised)`: the first event that receives the record becomes its `parent` and replaces the creating record in `parents`. Each later event is added to `parents`, and `parent` stays the first event. `ProcessRaisedEvent.__init__` calls it.
- Every change to the data is logged. Once the record is locked, any write raises `RuntimeError`. Nothing in the bundled plugins locks an event data record.
- `.data` no longer exists; use `dict(record)` for a plain copy.

### ProcessRaisedEvent
**Location**: `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py`

A record type that tracks the execution of a raised event:

```python
class ProcessRaisedEvent(BaseRecord):
    def __init__(self, event: "Event", event_data: "EventDataRecord",
                 called_from=""):
        BaseRecord.__init__(self)
        self.event = event
        self.called_from = called_from
        self.event_name = event.name
        self.event_data = event_data
        self.event_data.add_receiving_event(self)
        self.times_invoked = 0
        self.id = f"{__name__}:{self.event.name}:{self.created}"
        self.addupdate(UpdateFlag.INFO, "Init")
```

### RegisterToEvent Decorator
**Location**: `src/bastproxy/plugins/core/events/libs/_utils.py`

Decorator class for registering functions to events:

```python
class RegisterToEvent:
    def __init__(self, **kwargs):
        # kwargs include:
        #   - event_name: the event to register to
        #   - priority: callback execution priority (default: 50)
        self.registration_args = {"event_name": "", "priority": 50} | kwargs

    def __call__(self, func):
        if not hasattr(func, "event_registration"):
            func.event_registration = []
        func.event_registration.append(self.registration_args)
        return func
```

Only methods whose name starts with `_eventcb_` are picked up (`get_event_registration_functions_in_object`); the decorator on any other name is ignored, and `_register_events_for_plugin` logs a WARNING naming the plugin, the method and the event names. The `priority` is honoured: `event.register.by.func` passes it to `event.register` as `prio`. The event name may contain `{attribute}` placeholders, filled from the plugin instance, as in `ev_{plugin_id}_var_raised_history_size_modified`.

### EventsPlugin
**Location**: `src/bastproxy/plugins/core/events/plugin/_events.py`

The core plugin that manages the event system, tracking all events and registrations.

## How It Works

### 1. Event Registration

Plugins register callbacks to events using the `RegisterToEvent` decorator:

```python
@RegisterToEvent(event_name="ev_to_mud_data_modify", priority=50)
def _eventcb_handle_data(self):
    event_record = self.api("plugins.core.events:event.current.record.get")()
    # Process the event data
```

The decorator marks the function with event registration metadata. The events plugin registers the decorated `_eventcb_*` methods of every loaded plugin once, when the post-startup event is raised, and afterwards on `ev_plugin_loaded` for each plugin that loads (the `ev_plugin_loaded` callback returns without registering while the proxy is still starting up).

A callback can also be registered at runtime, with the priority under the keyword `prio`:

```python
self.api("plugins.core.events:event.register")("ev_my_event", self._eventcb_mine, prio=30)
```

### 2. Event Creation

Events are created using the API:

```python
self.api("plugins.core.events:event.add")(
    "ev_my_custom_event",
    "plugins.my.plugin",
    description=["Event when something happens"],
    arg_descriptions={
        "data": "The data associated with the event",
        "client_id": "The client that triggered the event"
    }
)
```

The four events the processing records raise (`ev_to_client_data_modify`, `ev_to_client_data_read`, `ev_to_mud_data_modify` and `ev_to_mud_data_read`) are registered once, when the events plugin initializes, from `RECORD_EVENTS` in `src/bastproxy/libs/records/events.py`. Creating a record makes no `event.add` call.

The two protocol events are registered the same way, from `PROTOCOL_EVENTS` in `src/bastproxy/libs/net/protocols.py`:

| Event | Arguments | Raised |
|-------|-----------|--------|
| `ev_libs.net.mud_gmcp` | `package`, `data` | once per GMCP message from the MUD (`Core.*` excluded) |
| `ev_libs.net.mud_msdp` | `variable`, `data` | once per MSDP variable from the MUD |
| `ev_libs.net.mud_mssp` | `data` | once per MSSP table from the MUD; `data` is the whole table |

Each event gets its own copy of `data` (`copy.deepcopy`), so a callback cannot change the cached value or what is sent to clients. A plugin that wants a GMCP package announces it to the MUD with `gmcp.modules.add`, which adds to the `Core.Supports.Set` the proxy sends:

```python
@RegisterToEvent(event_name="ev_libs.net.mud_gmcp")
def _eventcb_mud_gmcp(self):
    event_record = self.api("plugins.core.events:event.current.record.get")()
    package, data = event_record["package"], event_record["data"]
    ...

def _phook_initialize(self):
    self.api("libs.net.protocols:gmcp.modules.add")(["Char 1", "Room 1"])
```

A plugin's modules leave the union when it uninitializes. The events cover what the MUD sends; clients' GMCP and MSDP are not raised as events.

Follow-up candidates (not part of #59): plugin APIs that send GMCP and MSDP to the MUD or to one client, and events for GMCP and MSDP that clients send to the proxy.

### 3. Event Raising

Events are raised by calling the `event.raise` API:

```python
self.api("plugins.core.events:event.raise")(
    "ev_my_custom_event",
    event_args={"data": some_data, "client_id": client_id}
)
```

When an event is raised:
1. A `ProcessRaisedEvent` instance is created
2. The event data is wrapped in an `EventDataRecord` if it's not already
3. Callbacks are executed in priority order (sorted by priority number)
4. Each callback is executed once per raise (and per item of a `data_list`)
5. If new callbacks are registered during execution, they are processed in subsequent passes, whichever pass registers them and at whatever priority; one registered at an already visited priority runs out of priority order and logs the out-of-order warning (#275)
6. The raise ends; its `done` set goes with it, and `active_event` and `current_callback` return to what they were before the raise
7. An exception in a callback is logged and the remaining callbacks still run; `raise_event` returns `None` and logs an error when the data is neither a dict nor an `EventDataRecord` (the error log names the `actor`, #276)

#### Actors

`event.raise` takes a `calledfrom` argument; when it is empty the events plugin looks up the owner id of the caller. That owner id is the `actor` passed to `Event.raise_event`, stored as `ProcessRaisedEvent.called_from`, used as the owner id of a new `EventDataRecord` and as `created_by` of an event that has none. Each callback runs under `tracking_actor("<owner_id>:<function name>")`, so changes it makes to the data are attributed to it.

### 4. Priority-Based Execution

Callbacks are organized by priority (default: 50):
- Lower numbers execute first (e.g., priority 0 before priority 1, priority 1 before priority 50); `prio=None` means 50
- Within one priority, callbacks run in registration order
- All callbacks at a given priority are executed before moving to the next priority
- The system uses a while loop to handle callbacks registered during event execution

```python
def raise_priority(self, priority, already_done: bool, done: set | None = None) -> bool:
    done = set() if done is None else done
    found = False
    for call_back in list(self.priority_dictionary[priority].keys()):
        try:
            if call_back in self.priority_dictionary[priority] and call_back not in done:
                self.current_callback = call_back
                done.add(call_back)
                with tracking_actor(f"{call_back.owner_id}:{call_back.name}"):
                    call_back.execute()
                found = True
                if already_done:
                    ...  # logs a WARNING that the callback ran out of order
        except Exception:
            ...  # logs an ERROR with exc_info; the next callback still runs
    return found
```

`already_done` is true when the priority was visited in an earlier pass; the warning is only logged then. A callback declared `async def` never reaches this method: `Event.register` rejects it (#277).

### 5. Event Stack

The names of the events being raised are held in the `event_stack` context variable (`src/bastproxy/libs/context.py`), which `event.raise` sets for the duration of the raise and resets also when a callback raises:
- Accessible via `api("plugins.core.events:event.stack.get")()`, which returns a list, outermost first
- Used to track the chain of events that led to the current execution
- Helpful for debugging and understanding event flow

### 6. Current Event Record

Callbacks can access the current event's data record:

```python
event_record = self.api("plugins.core.events:event.current.record.get")()
if event_record:
    # Access event data
    data = event_record["some_key"]
    # Modify event data
    event_record["some_key"] = new_value
```

## Important Files

### Core Event System
- `src/bastproxy/plugins/core/events/plugin/_event.py` - Event class implementation
- `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` - ProcessRaisedEvent class
- `src/bastproxy/plugins/core/events/libs/data/_event.py` - EventDataRecord class
- `src/bastproxy/plugins/core/events/libs/_utils.py` - RegisterToEvent decorator

### Event Plugin
- `src/bastproxy/plugins/core/events/plugin/_events.py` - EventsPlugin that manages events
- `src/bastproxy/plugins/core/events/__init__.py` - Plugin metadata and the `RegisterToEvent` export
- `src/bastproxy/plugins/core/events/plugin/__init__.py` - Exports the `Plugin` class

The package has no libs/_event.py or plugin/_process_event.py: #241 deleted those duplicate copies of `Event` and `ProcessRaisedEvent`.

### Events API
The APIs of `plugins.core.events` (names as registered with `AddAPI`): `event.add`, `event.get`, `event.exists`, `event.register`, `event.register.by.func`, `event.unregister`, `event.unregister.for.owner`, `event.is.registered`, `event.raise`, `event.current.name.get`, `event.current.record.get`, `event.stack.get`, `event.detail.get`, `detail.get.for.plugin` and `summary.get.for.plugin`. `event.get` creates and keeps an `Event` for any name it has not seen; use `event.exists` to look up without creating. The `raise` command checks `event.exists` first, so an unknown name answers "event does not exist" and creates nothing (#283).

## Code Examples

### Creating and Raising an Event

```python
# Create the event
self.api("plugins.core.events:event.add")(
    "ev_data_processed",
    self.plugin_id,
    description=["Raised when data has been processed"],
    arg_descriptions={
        "processed_data": "The data after processing",
        "status": "Processing status"
    }
)

# Raise the event later
self.api("plugins.core.events:event.raise")(
    "ev_data_processed",
    event_args={
        "processed_data": result,
        "status": "success"
    }
)
```

### Registering to an Event

```python
@RegisterToEvent(event_name="ev_to_client_data_modify", priority=1)  # stored at priority 1 (#278)
def _eventcb_process_client_data(self):
    """Process data before it's sent to the client."""
    event_record = self.api("plugins.core.events:event.current.record.get")()
    if event_record:
        # Access the line being sent to the client
        line = event_record["line"]
        # Modify it if needed
        line.line = "Modified: " + line.line
```

### Checking Event Registration

```python
# Check if a function is registered to an event
is_registered = self.api("plugins.core.events:event.is.registered")(
    "ev_my_event",
    my_callback_function
)

# Get event details
event_details = self.api("plugins.core.events:event.detail.get")("ev_my_event")
```

### Unregistering from an Event

```python
self.api("plugins.core.events:event.unregister")(
    "ev_my_event",
    my_callback_function
)
```

## Integration Points

### Plugin System
- At startup the events plugin registers the `@RegisterToEvent` decorated `_eventcb_*` methods of all loaded plugins when the post-startup event is raised; after startup it does the same for each plugin on `ev_plugin_loaded`
- The `EventsPlugin` listens to `ev_plugin_loaded` and `ev_plugin_unloaded` to manage registrations
- When a plugin unloads, all its event registrations are removed (`event.unregister.for.owner`); the `Event` objects stay

### Data Flow
- Events are the primary mechanism for data flow through the system
- Key data flow events:
  - `ev_to_mud_data_modify` - Data from client to mud
  - `ev_to_client_data_modify` - Data from mud to client
  - `ev_to_mud_data_read` and `ev_to_client_data_read` - The data after it was sent

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
            ran = self.event.raise_priority(
                priority, priority in priorities_done, self.done
            )
            found_callbacks = found_callbacks or bool(ran)
            priorities_done.append(priority)
```

If the loop executes more than twice, a warning is logged indicating that callbacks were added during execution.

`found_callbacks` is OR-ed across the priorities of a pass, so another pass runs whenever any priority ran a callback, and a callback registered from the second pass on at an already visited priority runs in that raise (#275). A callback registered during the first pass runs after the callbacks at higher priorities, not in priority order, and the out-of-order warning is logged only for an already visited priority.

### Event Data Mutation Tracking

Event data records can be modified by callbacks, with changes tracked through the record system:

```python
event_record["key"] = new_value
event_record.addupdate("Modify", "Changed key to new_value")
```

This allows debugging of how event data changes through the callback chain.

### Event History

The `Event` class keeps a bounded history of its raises:

```python
self.raised_events: OrderedDict[str, ProcessRaisedEvent]  # UUID -> record, newest last
```

The history is an `OrderedDict` capped at `Event.MAX_RAISED_EVENTS`. `EventsPlugin` sets that class attribute from the `plugins.core.events` setting `raised_history_size` (default 10; 0 keeps none; a negative value is clamped to 0), at initialize and whenever the setting changes. The oldest entry is evicted when a new raise is inserted, so a lowered cap applies on each event's next raise. `raise_event` returns the record of that raise even when the cap is 0.

The long history is in the records manager (`RMANAGER` keeps a `ProcessRaisedEvent` while its root tree is among the last `retained_trees` root trees, indexed by UUID), which the debug records plugin reads. The per-event history holds no callbacks, so it does not keep unloaded plugins alive (Bug #3 in [Event System Findings](event_system_findings.md), #153).

## Common Event Names

### Core Events
- `ev_plugin_loaded` - A plugin was loaded
- `ev_plugin_unloaded` - A plugin was unloaded
- `ev_plugin_save` - A plugin should save its state
- `ev_plugin_reset` - A plugin should reset to defaults

### Data Flow Events
- `ev_to_mud_data_modify` - Modify data before sending to mud
- `ev_to_client_data_modify` - Modify data before sending to client
- `ev_to_mud_data_read` - Data that was sent to the mud
- `ev_to_client_data_read` - Data that was sent to the client

### Network Events
- `ev_libs.net.mud_mudconnect` - Connected to mud
- `ev_libs.net.mud_from_mud_event` - Not raised by anything. The triggers plugin registers on it when its `enabled` setting changes ([Triggers System Findings](triggers_system_findings.md), TR-11); MUD lines arrive on `ev_to_client_data_modify`
- `ev_libs.net.mud_gmcp` - A GMCP message from the mud (args `package`, `data`)
- `ev_libs.net.mud_msdp` - An MSDP variable from the mud (args `variable`, `data`)
- `ev_libs.net.mud_mssp` - An MSSP table from the mud (arg `data`, the whole table)

### Proxy Events
- `ev_bastproxy_proxy_ready` - Proxy is ready to accept connections
- `ev_plugins.core.proxy_shutdown` - Proxy is shutting down
- `ev_plugins.core.events_all_events_registered` - All events registered at startup

### Client Events
- `ev_plugins.core.clients_client_logged_in` - A client logged in to the proxy
