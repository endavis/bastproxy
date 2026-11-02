---
title: Record System
description: Records that track data and operations, their lifecycle and relationships
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - records
---

# Record System

## Overview

bastproxy wraps its significant data and operations in **records**: log messages, network lines and batches, the steps that process them, raised events and command arguments. A record is a normal mutable object that also keeps a history:

- a UUID, an owner ID and its creation time
- the call stack and event stack when it was created
- its parent record, the one that was running when it was created
- a list of updates: changes and notes, each with the stack and an "actor"
- its execution time, when the record is executable

A global manager, `RMANAGER`, keeps the most recent records of each type so they can be inspected later, mainly through the `plugins.debug.records` commands.

For how records move through the proxy, see [Data Flow](data_flow.md).

## Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `BaseRecord` | `src/bastproxy/libs/records/rtypes/base.py` | Base of every record: identity, parent, updates, execution |
| `TrackedUserList` | `src/bastproxy/libs/records/rtypes/base.py` | A list record whose main mutations are tracked (base of `NetworkData`) |
| `BaseListRecord` | `src/bastproxy/libs/records/rtypes/base.py` | A list record with text helpers (base of `LogRecord`) |
| `BaseDictRecord` | `src/bastproxy/libs/records/rtypes/base.py` | A dict record (base of `EventDataRecord`, `CmdArgsRecord`) |
| `UpdateRecord` | `src/bastproxy/libs/records/rtypes/update.py` | One change or note on a record |
| `UpdateManager` | `src/bastproxy/libs/records/managers/updates.py` | A record's updates |
| `RecordManager` (`RMANAGER`) | `src/bastproxy/libs/records/managers/records.py` | Stores records, tracks the active record, answers tree queries |
| `AttributeMonitor` | `src/bastproxy/libs/tracking/utils/attributes.py` | Records reassignment of chosen attributes, and attribute locks |

### BaseRecord

```python
class BaseRecord(AttributeMonitor):
    def __init__(self, owner_id: str = "", track_record=True, parent=None):
        self.uuid = uuid4().hex
        self.owner_id = owner_id or f"{ClassName}:{uuid}"
        self.api = API(owner_id=self.owner_id)
        self.created = datetime.datetime.now(datetime.UTC)
        self.updates = UpdateManager()
        self.execute_time_taken = -1
        self.track_record = track_record
        self.stack_at_creation = ...   # traceback.format_stack(limit=10), one line per entry
        self.event_stack = ...         # plugins.core.events:get.event.stack, if available
        self.parent = parent or RMANAGER.get_latest_record()
        self.parents = [self.parent] if self.parent else []
        RMANAGER.add(self)
        self.executing = False
```

`BaseRecord` itself adds no update at creation. Subclasses usually do: `BaseListRecord` and `BaseDictRecord` add an `Info` "Init" update, and `TrackedUserList` and `NetworkDataLine` add a `Modify` "original input" update.

Records compare and hash by UUID (`__eq__`, `__hash__`) and sort by creation time (`__lt__`). `BaseListRecord` lists `UserList` before `BaseRecord` among its bases, so it overrides `__eq__` and `__hash__` to use the `BaseRecord` versions: it too compares and hashes by UUID, not by content.

### UpdateRecord

```python
class UpdateRecord:
    def __init__(self, parent, flag: str, action: str, extra: dict | None = None, data=None):
        self.uuid = uuid4().hex
        self.time_taken = datetime.datetime.now(datetime.UTC)  # when the update happened
        self.parent = parent           # the record that was updated
        self.flag = flag               # "Modify", "Set Flag" or "Info"
        self.action = action           # what happened
        self.extra = extra or {}       # details
        self.data = data               # a copy of the record's data (list and dict records)
        self.stack = ...               # traceback.format_stack(limit=15)
        self.actor = ...               # see "How the actor is chosen"
        self.event_stack = ...         # the event names being processed
```

| Flag | Used for |
|------|----------|
| `Modify` | Data or an attribute changed |
| `Set Flag` | A flag was set (`format()` shows "set <action> to <data>") |
| `Info` | Lifecycle notes: "Init", "_exec_ start", "Invoked", attempted writes to locked attributes |

#### How the actor is chosen

`UpdateRecord.find_relevant_actor()` walks the formatted stack and keeps the innermost `File ...` line whose path contains none of `libs/records/`, `libs/data`, `libs/process` or `tracking/utils`, together with the source line after it. A change made by a plugin callback is therefore attributed to the plugin's file and line. A change made by record code itself (for example `NetworkDataLine.format()` adding line endings) is attributed to the code that started the pipeline, such as `MudConnection.mud_read`, because every frame in between is excluded.

### UpdateManager

```python
class UpdateManager(deque):
    def __init__(self):
        super().__init__(maxlen=1000)  # the most recent 1000 updates
        self.uid_mapping = {}          # update UUID -> UpdateRecord
```

`uid_mapping` is not trimmed when the deque drops old updates, so a record keeps references to every update it ever had.

### RecordManager

```python
class RecordManager:
    def __init__(self):
        self.max_records = 5000                    # per record type
        self.records: dict[str, SimpleQueue] = {}  # class name -> recent records
        self.record_instances = {}                 # UUID -> record
        self.active_record_stack = SimpleStack()   # records currently executing
        self.default_filter = ["LogRecord"]        # left out of tree queries by default
```

- `add(record)` stores a new record and drops the record evicted from its type's queue from `record_instances`. Children still hold a reference to an evicted parent through `parent` and `parents`.
- `start(record)` / `end(record)` push and pop the active record. `end()` with a record that is not on top removes it from the middle of the stack and is meant to log a warning, but the warning `LogRecord` is never executed (#46).
- `get_children()` scans every stored record's `parents`. `get_all_children_dict()`, `get_all_children_list()` and `format_all_children()` repeat that scan at each level of the tree.

### List and dict records

**`TrackedUserList(BaseRecord, UserList)`** records `__setitem__`, `insert`, `append` and `extend`, and its `lock()` stops those four. `pop`, `remove`, `del`, `clear`, `sort`, `reverse`, `+=` and `*=` are neither tracked nor stopped by the lock (#47). `NetworkData` is a `TrackedUserList` of `NetworkDataLine` records.

**`BaseListRecord(UserList, BaseRecord)`** adds `message_type`, `internal`, `original_data` and text helpers: `clean()`, `color_lines()`, `add_line_endings()` and `replace()`. Its `addupdate()` takes `savedata` (default `True`) and stores a copy of the list with the update. `LogRecord` is the only subclass.

**`BaseDictRecord(BaseRecord, UserDict)`** keeps `original_data`, and its `addupdate()` also takes `savedata`. Setting keys is not tracked; code that changes the dict records an update itself. `EventDataRecord` and `CmdArgsRecord` are dict records.

## How It Works

### 1. Creating a record

1. A UUID and the creation time are set
2. The call stack and event stack are captured
3. The parent is the one passed in, or the active record
4. The record is added to `RMANAGER`
5. The subclass usually adds an initial update

### 2. Parent-child relationships

```python
class Outer(BaseRecord):
    def _exec_(self):
        inner = SomeRecord()  # inner.parent is this Outer record

Outer()()
```

- `parent` is the record that was active at creation, or the one passed in
- `parents` is the list of parents added with `add_parent()`. It holds direct parents, not ancestors. A record can have several: a `NetworkData` gets a second parent when `SendDataDirectlyToMud` takes it over from `ProcessDataToMud`.
- `NetworkDataLine.add_parent()` keeps only one parent, and only accepts `NetworkData` or `NetworkDataLine` parents

### 3. Tracking changes

There are three ways an update gets recorded:

```python
# 1. Explicit
record.addupdate("Modify", "Converted color codes", extra={"line": 3})

# 2. Monitored attributes (AttributeMonitor); see "Attribute Monitoring"
record.status = "done"   # records "status attribute changed", if "status" is monitored

# 3. Tracked list operations (TrackedUserList / NetworkData)
network_data.append("look")
```

Each update holds the flag, action and extra details, the time, the stack, the actor, the event stack and, for list and dict records, a copy of the data.

### 4. Execution

```python
class MyRecord(BaseRecord):
    def _exec_(self):
        ...

MyRecord()()  # calling the record runs _exec_()
```

`BaseRecord.__call__`:

1. If the record is already executing, adds an `Info` "already executing" update and returns
2. Sets `executing` and adds `Info` "_exec_ start"
3. If `track_record` is set: starts a timer, pushes the record on the active stack, runs `_exec_()`, pops it and stores `execute_time_taken`. Otherwise it only runs `_exec_()`.
4. Adds `Info` "_exec_ finish" and clears `executing`

`__call__` uses `try/finally`. If `_exec_()` raises, the record is still popped from the active stack and `executing` is cleared, so later records do not get it as their parent.

`track_record=False` only skips the timer and the active-stack push, so records created inside it are not attributed to it. It does not reduce what is captured: the creation stack, the event stack and every update are still recorded. `LogRecord` and `CmdArgsRecord` use `track_record=False`.

### 5. Retrieving records

```python
RMANAGER.get_types()                 # [("LogRecord", 13), ("NetworkDataLine", 120), ...]
RMANAGER.get_records("LogRecord", count=10)
RMANAGER.get_record(uuid)
RMANAGER.get_children(parent_record)             # direct children
RMANAGER.get_all_children_list(parent_record)    # all descendants
RMANAGER.format_all_children(parent_record)      # tree as lines
```

### 6. Formatting

```python
record.one_line_summary()   # "LogRecord            <uuid> Something happened"
record.get_formatted_details(
    full_children_records=False,  # True: full details of each child
    include_updates=True,         # updates of this record and its children
    update_filter=["LogRecord"],  # record class names to leave out
    include_children_records=True,
)
```

The details list the identity fields, each monitored attribute (with "changed from ... to ..." when it differs from its first value), the creation event and call stacks, the children tree and the updates.

From a client, the same information is available through `plugins.debug.records`, which is not loaded by default:

```
#bp.core.pluginm.load plugins.debug.records
#bp.debug.records.types
#bp.debug.records.list <RecordType> [-c <count>]
#bp.debug.records.detail <uuid> [-u <update uuid>]
#bp.debug.records.children <uuid>
```

## Record Types

| Record | File | Base | What it is |
|--------|------|------|------------|
| `NetworkDataLine` | `src/bastproxy/libs/records/rtypes/networkdata.py` | `BaseRecord` | One line to or from the MUD or a client |
| `NetworkData` | `src/bastproxy/libs/records/rtypes/networkdata.py` | `TrackedUserList` | A batch of `NetworkDataLine` records |
| `ProcessDataToMud` | `src/bastproxy/libs/records/rtypes/muddata.py` | `BaseRecord` | Client input before plugins see it |
| `SendDataDirectlyToMud` | `src/bastproxy/libs/records/rtypes/muddata.py` | `BaseRecord` | Formats and queues lines for the MUD |
| `ProcessDataToClient` | `src/bastproxy/libs/records/rtypes/clientdata.py` | `BaseRecord` | MUD output before plugins see it |
| `SendDataDirectlyToClient` | `src/bastproxy/libs/records/rtypes/clientdata.py` | `BaseRecord` | Formats and queues lines for clients |
| `LogRecord` | `src/bastproxy/libs/records/rtypes/log.py` | `BaseListRecord` | A log message |
| `ProcessRaisedEvent` | `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` | `BaseRecord` | One raise of an event |
| `EventDataRecord` | `src/bastproxy/plugins/core/events/libs/data/_event.py` | `BaseDictRecord` | The arguments of a raised event |
| `CmdArgsRecord` | `src/bastproxy/plugins/core/commands/libs/data/cmdargs.py` | `BaseDictRecord` | Parsed arguments of a proxy command |

The network records and the four processing steps are described in [Data Flow](data_flow.md).

### LogRecord

```python
LogRecord(
    "Something happened",                # str or list of str
    level="info",                        # debug, info, warning, error, critical
    sources=["plugins.core.commands"],   # logger names to emit through
)()                                      # nothing is logged until the record is called
```

When called, a `LogRecord` cleans and colors its lines, then calls the logger of each name in `sources` at its level. Any other keyword argument is passed on to that logger call, so only arguments `logging` accepts (such as `exc_info=True` or `stack_info=True`) can be used. Pitfalls:

- Without `sources`, nothing is logged (#46)
- A `LogRecord` that is created but not called is never logged (#46)
- `LogRecord` is created with `track_record=False`. Passing `track_record=` yourself sends it to the logger and raises `TypeError`

`wasemitted` (`console`, `file`, `client`) is set by the log handlers in `src/bastproxy/plugins/core/log/libs/_custom_logger.py`, so each destination emits a record once.

### Event records

`Event.raise_event()` wraps the event arguments in an `EventDataRecord` and runs a `ProcessRaisedEvent` for them. The `ProcessRaisedEvent` is the active record while callbacks run, so records the callbacks create become its children. For events raised with `data_list`, the same `EventDataRecord` is reused and its `key_name` entry is set to each item in turn. Each invocation adds an `Info` "Invoked" update with a copy of the event data.

## Attribute Monitoring

`BaseRecord` inherits from `AttributeMonitor` (`src/bastproxy/libs/tracking/utils/attributes.py`), which overrides `__setattr__`.

### Monitored attributes

```python
class MyRecord(BaseRecord):
    def __init__(self):
        super().__init__()
        self._attributes_to_monitor.append("status")
        self.status = "pending"   # first assignment: stored as the original value, no update
```

After the first assignment, assigning a different value adds a `Modify` update with `extra={"original": old, "new": new}` and calls `_am_onchange_<name>(old, new)` if the class defines it. Assigning an equal value records nothing.

Only **reassignment** is seen. Changing a monitored list or dict in place (for example `self.parents.append(...)`) records nothing, and because the original value is stored by reference, the "original" changes too (#48).

### Locked attributes

```python
record._am_lock_attribute("line")
record.line = "new"     # ignored; adds an Info "Attempted to update a locked attribute" update
record._am_unlock_attribute("line")
```

A write to a locked attribute is dropped without raising an error (#48). `NetworkDataLine.lock()` locks its content and flag attributes, and the send steps call it before queuing a line.

## Common Patterns

### A custom record

```python
from bastproxy.libs.records import BaseRecord

class MyCustomRecord(BaseRecord):
    def __init__(self, data, owner_id=""):
        super().__init__(owner_id)
        self._attributes_to_monitor.extend(["status", "count"])
        self.status = "pending"
        self.count = 0
        self.data = data
        self.addupdate("Info", "MyCustomRecord created")

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[1].extend([("Status", "status"), ("Count", "count"), ("Data", "data")])
        return attributes

    def _exec_(self):
        self.status = "processing"
        self.count += 1
        self.status = "complete"

MyCustomRecord({"key": "value"}, owner_id=self.plugin_id)()
```

`get_attributes_to_format()` returns sections `0` (top), `1` (middle) and `2` (bottom) of the details output.

### Logging

```python
from bastproxy.libs.records import LogRecord

LogRecord("Something happened", level="info", sources=[__name__])()
LogRecord(["Line 1", "Line 2"], level="debug", sources=[self.plugin_id])()
LogRecord("Lookup failed", level="error", sources=[__name__], exc_info=True)()
```

### Recording a data change

```python
from bastproxy.libs.records.rtypes.base import BaseListRecord

data = BaseListRecord(["line 1", "line 2"])
data.replace(["modified line"], actor=__name__, extra={"reason": "cleanup"})

for update in data.updates:
    print(update.format())
```

`replace()` only records an update when the new data differs.

### Querying relationships

```python
children = RMANAGER.get_children(record, record_filter=["LogRecord"])
descendants = RMANAGER.get_all_children_list(record)
for line in RMANAGER.format_all_children(record):
    print(line)

current = record
while current.parent:
    print(current.parent.one_line_summary())
    current = current.parent
```

`record_filter` and `update_filter` take record class names. `LogRecord` is always filtered out of tree queries (`RMANAGER.default_filter`).

## Performance Considerations

- **Creation and every update capture a formatted call stack** (10 frames per record, 15 per update). This is most of the cost of creating a record or changing a monitored attribute, and it is paid for every network line and log message.
- **Every record and every update creates an `API` instance.**
- **Retention:** `RMANAGER` keeps the most recent `max_records` (5000) records of each type, and each record keeps up to 1000 updates. List and dict records store a copy of their data in each update.
- **Inspecting adds records:** every line printed by the records commands is a `NetworkDataLine`, so a long listing can push older records out of the store.
- **Tree queries scan every stored record** at each level of the tree.
- **`track_record=False` does not reduce this cost.** It only skips the execution timer and the active-stack push.
- **`savedata=False`** (on `BaseListRecord.addupdate` and `BaseDictRecord.addupdate` only) skips the data copy for one update. `BaseRecord.addupdate()` does not accept it.

#43 plans to replace the tracking with pydatatracker, which captures stacks only on request.

## Known Gaps

| Issue | Gap |
|-------|-----|
| #46 | `LogRecord`s without `sources`, or never called, are not logged |
| #47 | `TrackedUserList` misses several mutations and its lock does not stop them; lines appended to `NetworkData` get no parent |
| #48 | `AttributeMonitor` misses in-place changes and silently drops writes to locked attributes |
| #49 | `get_update()` never finds child updates; `str()` on a telnet line raises; `one_line_summary()` bugs |
| #43 | Planned replacement of the tracking with pydatatracker |
| #81 | The per-update diagnostic capture (call stacks, data copies) is not configurable or cheap by default |
| #82 | Records are kept only in memory: those beyond `max_records` are lost, and none survive a restart |
| #83 | Telnet negotiation and protocol messages are not tracked as records |

## Best Practices

1. **Give records a meaningful owner ID**, usually `self.plugin_id`
2. **Monitor the attributes that describe state**, and set them once in `__init__` so the first value is the original
3. **Reassign instead of mutating** monitored lists and dicts, or record the change with `addupdate()`
4. **Write clear update actions** and put details in `extra`
5. **Always pass `sources` to `LogRecord`, and call it**
6. **Don't hold references to old records** longer than needed: they keep their parents and updates alive
7. **When debugging**, load `plugins.debug.records`, follow `parent` up and `children` down, and read each update's `actor` and `stack`
