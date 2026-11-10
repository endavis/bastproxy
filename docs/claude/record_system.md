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
- the event stack when it was created, and the call stack when stack capture is on
- its parent record, the one that was running when it was created
- a list of updates: changes and notes, each with an "actor" and, when stack capture is on, a stack
- its execution time, when the record is executable

A global manager, `RMANAGER`, keeps the most recent records of each type so they can be inspected later, mainly through the `plugins.debug.records` commands.

For how records move through the proxy, see [Data Flow](data_flow.md). For what the tracking misses, what the
store keeps and what it costs, see [Record System Findings](record_system_findings.md).

## Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `BaseRecord` | `src/bastproxy/libs/records/rtypes/base.py` | Base of every record: identity, parent, updates, execution |
| `BaseDictRecord` | `src/bastproxy/libs/records/rtypes/dictrecord.py` | A dict record on pydatatracker `TrackedDict` (base of `EventDataRecord`, `CmdArgsRecord`). `base.py` re-exports it lazily |
| `TrackedUpdate` | `src/bastproxy/libs/records/rtypes/update.py` | The display view of one update, for every record type |
| `RecordManager` (`RMANAGER`) | `src/bastproxy/libs/records/managers/records.py` | Stores records, tracks the active record, answers tree queries |
| `context.py` | `src/bastproxy/libs/context.py` | The context variables for the active record, the event stack and the running command's args |
| `RECORD_EVENTS` | `src/bastproxy/libs/records/events.py` | The four events the processing records raise, registered by the events plugin |

### BaseRecord

`BaseRecord` is a plain tree node for the processing records. It watches no attributes and does not intercept assignments.

```python
class BaseRecord(RecordDisplayMixin):
    def __init__(self, owner_id: str = "", track_record=True, parent=None):
        self.uuid = uuid4().hex
        self.owner_id = owner_id or ClassName
        self.api = API(owner_id=self.owner_id)
        self.created = datetime.datetime.now(datetime.UTC)
        self._updates = deque(maxlen=RMANAGER.max_changes)   # ChangeLogEntry objects
        self.execute_time_taken = -1
        self.track_record = track_record
        self.stack_at_creation = ...   # [] unless RMANAGER.capture_stacks is on
        self.event_stack = ...         # a tuple, read from the event_stack context variable
        self.parent = parent or RMANAGER.get_latest_record()
        self.parents = [self.parent] if self.parent else []
        RMANAGER.add(self)
        self.executing = False
```

The owner ID is per class so that API stats stay bounded (#232); `uuid` is the record's identity. Creating a record and calling `addupdate()` make no API call.

`BaseRecord` itself adds no update at creation. `__call__` adds `Info` updates around `_exec_()`.

Records compare and hash by UUID (`__eq__`, `__hash__`) and sort by creation time (`__lt__`).

### Updates

`addupdate(flag, action, extra=None)` builds a pydatatracker `ChangeLogEntry` and appends it to the record's capped deque. `updates` returns a `TrackedUpdate` view of each entry, oldest first. Every record type shows its updates through `TrackedUpdate`, whether it is a processing record or a pydatatracker container.

| Part of an update | Where it comes from |
|-------------------|---------------------|
| `flag` | The argument: an `UpdateFlag` or its string (`Modify`, `Set Flag` or `Info`). An unknown value raises `ValueError` |
| `action`, `extra` | The arguments. A key of `extra` that the entry reads itself (`action`, `flag`, `type`, `locked`, `actor`, `location`, `method`, `event_stack`) is stored as `extra_<key>` |
| `actor` | The tracking actor of the context (`tracking_actor(...)`); with none set, the innermost caller outside `bastproxy.libs.records`, as `module:function` (found by walking frame objects, not by formatting a stack) |
| `event_stack` | The `event_stack` context variable, joined with ` > `. Shown as an `Event Stack` section in the details when it is not empty |
| `stack` | Empty unless `capture_stacks` is on, then the last 15 frames |
| time, uuid | Set by pydatatracker |

| Flag | Used for |
|------|----------|
| `UpdateFlag.MODIFY` (`Modify`) | Data or an attribute changed |
| `UpdateFlag.SET_FLAG` (`Set Flag`) | A flag was set |
| `UpdateFlag.INFO` (`Info`) | Lifecycle notes: "_exec_ start", "Invoked", "already executing" |

`get_update(uuid)` and `get_all_updates()` live in `RecordDisplayMixin`, so every record type shares them. `get_update` searches the record's own updates first and then those of its child records. `get_all_updates()` returns the record's updates and its children's, in time order.

### Context variables

`src/bastproxy/libs/context.py` holds three context variables, each set for the duration of the work and reset with its token, also when the work raises:

| Variable | Set by | Read by |
|----------|--------|---------|
| `active_records` (a tuple, outermost first) | `RMANAGER.start()` and `end()`, called from `BaseRecord.__call__` | `RMANAGER.get_latest_record()` (the parent of a new record, and the logger's per-record buffer) and the prune |
| `event_stack` (a tuple of event names) | `event.raise` in the events plugin | `BaseRecord.__init__` and `addupdate`, and the `event.stack.get`, `event.current.name.get` and `event.current.record.get` APIs |
| `command_args` (a mapping or `None`) | `CommandClass.run`, around the command function | `TrackedUpdate.format_detailed` and the `command.current.args.get` API, which returns `{}` when no command runs |

Asyncio copies the current context into each task. `TaskItem.create` passes `fresh_context()` as the task's context, which resets the three variables, so a task spawned while a record, event or command is running does not inherit it. The tracking actor is left alone.

A nested command no longer clears the outer command's args when it finishes.

### Stack capture

A call stack is captured only while `RMANAGER.capture_stacks` is on. It is off by default and is the `capture_stacks` setting of `plugins.debug.records`.

- **On:** `BaseRecord.stack_at_creation` holds the last 10 frames, each `BaseRecord` update holds the last 15, and new data records (`NetworkDataLine`, `NetworkData`, `BaseDictRecord`) pass `tracking_capture_stack=True` to pydatatracker. Pydatatracker captures a stack only for a change made with no actor set, so a data record shows stacks only on paths without an actor, such as the raw network read.
- **Off:** no `traceback` call is made, and the details show `Call Stack at Creation : not captured (set capture_stacks in plugins.debug.records)`.
- A stack cannot be captured after the fact. Turn the setting on before the traffic you want to inspect; records that already exist keep what they captured.

### Events the processing records raise

`ProcessDataToClient`, `SendDataDirectlyToClient`, `ProcessDataToMud` and `SendDataDirectlyToMud` only name their events (class constants `MODIFY_EVENT` and `READ_EVENT`). `RECORD_EVENTS` in `src/bastproxy/libs/records/events.py` holds the description of each, and `EventsPlugin` registers them with `event.add` once, when it initializes. Creating a record makes no `event.add` call.

### RecordManager

```python
class RecordManager:
    def __init__(self):
        self.max_trees = 100                       # root trees kept (DEFAULT_MAX_TREES)
        self.max_changes = 1000                    # change entries per new record (DEFAULT_MAX_CHANGES)
        self.records: dict[str, dict] = {}         # class name -> {UUID: record}, oldest first
        self.record_instances = {}                 # UUID -> record
        self.capture_stacks = False                # capture call stacks, off by default
```

- `add(record)` stores a new record under its class name and UUID and counts a new root. There is no per-type cap.
- **Roots, pending records and trees.** A root is a record with no `parents` whose class has `retention_root = True`: the processing records (`ProcessDataToClient`, `ProcessDataToMud`, `ProcessRaisedEvent`, `SendDataDirectlyToClient`, `SendDataDirectlyToMud`). `TrackedRecordMixin` sets it to `False`, so a parentless `NetworkData`, `NetworkDataLine`, `EventDataRecord` or `CmdArgsRecord` is a pending record: it is not counted, and it joins a tree once something adopts it through `parents`. `mud_read` creates its `NetworkData` this way and may hold it for minutes.
- `prune()` keeps the last `max_trees` roots (oldest first by insertion) and evicts the rest whole. One pass scans `record_instances` and builds a parent-to-children map, then collects the subtrees of the excess roots. A node in an evicted subtree survives when one of its parents is stored and not evicted, and so do its descendants: a record shared by two trees (an `EventDataRecord` passed to a second event) stays while either tree is kept. A root that is executing, or that is an ancestor of an active record, is never evicted. A stored record whose parents are all gone (dangling) is evicted. An evicted record's `parents` are left as they were, so a surviving node still shows its evicted parent. Pending records past `MAX_PENDING` (1000, a module constant) are evicted oldest first.
- **When it runs.** `end()` prunes once no record is active and at least `max(1, max_trees // 10)` roots have been added since the last pass, so nothing executing is mid-tree. `set_max_trees()` prunes at once. A failure is logged and never raised. So the store holds about `max_trees` to `max_trees + max_trees // 10` roots.
- `set_max_trees(n)` (below 1 logs a warning and uses 1) and `set_max_changes(n)` (below 0 logs a warning and uses 0) are plain setters. The `plugins.debug.records` plugin owns the `retained_trees` and `tracking_max_changes` settings and calls them; without that plugin loaded the built-in defaults apply. `max_changes` applies to records created after a change. `root_count()` counts the stored roots.
- `start(record)` / `end(record)` add the record to and remove it from the `active_records` context variable. `end()` with a record that is not the innermost removes it from the middle and logs a warning through the `libs.records.managers.records` logger (#46, #247).
- `capture_stacks` and `set_capture_stacks(bool)` switch stack capture; the `plugins.debug.records` plugin owns the `capture_stacks` setting and calls the setter.
- `get_children()` scans every stored record's `parents`. `get_all_children_dict()`, `get_all_children_list()` and `format_all_children()` repeat that scan at each level of the tree.

### List and dict records

**`NetworkData` and `NetworkDataLine`** are built on pydatatracker (`TrackedList` and `TrackedAttr`) through `TrackedRecordMixin` in `src/bastproxy/libs/records/tracking.py` ([ADR-0006](../decisions/0006-records-adapt-pydatatracker-containers-and-locked-writes-raise-runtimeerror.md)).

**`BaseDictRecord(TrackedRecordMixin, TrackedDict)`** keeps `original_data`. Every mutation (set, `del`, `pop`, `popitem`, `update`, `clear`, `setdefault`, `|=`) adds a `Modify` update, and once the record is locked each of them raises `RuntimeError` ([ADR-0006](../decisions/0006-records-adapt-pydatatracker-containers-and-locked-writes-raise-runtimeerror.md)). `copy()` is a read and returns a plain `dict`. `track_record` is accepted and ignored, because dict records are never executed. A stored value that is itself a record (`NetworkData`, `NetworkDataLine`) is not linked as a pydatatracker child, so it keeps its own parents and lock; a plain `TrackedDict` or `TrackedList` value is linked and locked with the record. A plain mutable value (list, dict, set) is stored as is: in-place changes to it are not tracked or locked, and `original_data` is a shallow copy. Assign a new value, or store a `TrackedList` or `TrackedDict`, to have changes tracked (#48). `.data` is gone. `EventDataRecord` and `CmdArgsRecord` are dict records.

## How It Works

### 1. Creating a record

1. A UUID and the creation time are set
2. The event stack is read from the context variable, and the call stack is captured only when stack capture is on
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
- `NetworkDataLine.add_parent()` keeps only one parent by default (`reset=True` replaces the list); `reset=False` adds another. It checks `isinstance(parent, (NetworkData, NetworkDataLine))`, so subclasses are accepted, and it ignores any other parent without an error or a log. That is on purpose: `_init_record` offers the executing processing record on almost every line created during execution, so a log would spam

### 3. Tracking changes

There are two ways an update gets recorded:

```python
# 1. Explicit
record.addupdate("Modify", "Converted color codes", extra={"line": 3})

# 2. Tracked containers (NetworkData, NetworkDataLine and the dict records, on pydatatracker)
network_data.append("look")   # converted to a NetworkDataLine whose parent is network_data
```

Each update holds the flag, action and extra details, the time, the actor and the event stack (for the processing records), and a stack when capture is on. No update carries a copy of the data.

The processing records keep their updates in a deque of pydatatracker `ChangeLogEntry` objects. `NetworkDataLine`, `NetworkData` and the dict records keep them in pydatatracker's change log. For the containers, `updates` is a read-only list of `TrackedUpdate` views over the container's own entries (a child entry that pydatatracker re-homes onto the parent is left out). The actor is the context name set by `tracking_actor(...)`: the events plugin sets `<owner_id>:<callback name>` around each callback and the commands plugin sets `<plugin_id>:<command name>` around each command. For a container it is empty on the raw network read path, which the details show as "Unknown"; a processing record falls back to its caller, as above. Each record keeps up to `RMANAGER.max_changes` entries, 1000 by default (the `tracking_max_changes` setting of `plugins.debug.records`; `MAX_CHANGES` is the default). Pydatatracker's own entries use the actions `update`, `add` and `lock`, flagged `Modify`, or `Info` for `init`, `lock` and `unlock`.

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
3. If `track_record` is set: starts a timer, makes the record active, runs `_exec_()`, removes it from the active records and stores `execute_time_taken`. Otherwise it only runs `_exec_()`.
4. Adds `Info` "_exec_ finish" and clears `executing`

`__call__` uses `try/finally`. If `_exec_()` raises, the record is still removed from the active records and `executing` is cleared, so later records do not get it as their parent.

`track_record=False` only skips the timer and making the record active, so records created inside it are not attributed to it. Every update is still recorded. `CmdArgsRecord` passes it, but a dict record ignores it.

### 5. Retrieving records

```python
RMANAGER.get_types()                 # [("NetworkDataLine", 120), ...]
RMANAGER.get_records("NetworkDataLine", count=10)
RMANAGER.get_record(uuid)
RMANAGER.get_children(parent_record)             # direct children
RMANAGER.get_all_children_list(parent_record)    # all descendants
RMANAGER.format_all_children(parent_record)      # tree as lines
```

### 6. Formatting

```python
record.one_line_summary()   # "NetworkDataLine      <uuid> a line of text"
record.get_formatted_details(
    full_children_records=False,  # True: full details of each child
    include_updates=True,         # updates of this record and its children
    update_filter=[],             # record class names to leave out
    include_children_records=True,
)
```

The details list the identity fields, the creation event stack and call stack (or the note that the call stack was not captured), the children tree and the updates.

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
| `NetworkDataLine` | `src/bastproxy/libs/records/rtypes/networkdata.py` | `TrackedRecordMixin`, `TrackedAttr` | One line to or from the MUD or a client |
| `NetworkData` | `src/bastproxy/libs/records/rtypes/networkdata.py` | `TrackedRecordMixin`, `TrackedList` | A batch of `NetworkDataLine` records |
| `ProcessDataToMud` | `src/bastproxy/libs/records/rtypes/muddata.py` | `BaseRecord` | Client input before plugins see it |
| `SendDataDirectlyToMud` | `src/bastproxy/libs/records/rtypes/muddata.py` | `BaseRecord` | Formats and queues lines for the MUD |
| `ProcessDataToClient` | `src/bastproxy/libs/records/rtypes/clientdata.py` | `BaseRecord` | MUD output before plugins see it |
| `SendDataDirectlyToClient` | `src/bastproxy/libs/records/rtypes/clientdata.py` | `BaseRecord` | Formats and queues lines for clients |
| `ProcessRaisedEvent` | `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` | `BaseRecord` | One raise of an event |
| `EventDataRecord` | `src/bastproxy/plugins/core/events/libs/data/_event.py` | `BaseDictRecord` | The arguments of a raised event |
| `CmdArgsRecord` | `src/bastproxy/plugins/core/commands/libs/data/cmdargs.py` | `BaseDictRecord` | Parsed arguments of a proxy command |

The network records and the four processing steps are described in [Data Flow](data_flow.md).

`ProcessRaisedEvent` is defined once, in `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py`. The unused copies of it and of `Event` were deleted in #241. See [Record System Findings](record_system_findings.md#other-observations).

### Logging

Log messages are not records. `LogRecord` was removed in #247. The last 50 log lines written while a record was active are kept for it and shown by `#bp.debug.records.detail <uid>` when the `showRecordLogs` setting is on; see [Logging System](logging_system.md#log-lines-for-each-record).

### Event records

`Event.raise_event()` wraps the event arguments in an `EventDataRecord` and runs a `ProcessRaisedEvent` for them. The `ProcessRaisedEvent` is the active record while callbacks run, so records the callbacks create become its children. For events raised with `data_list`, the same `EventDataRecord` is reused and its `key_name` entry is set to each item in turn. Each invocation adds an `Info` "Invoked" update with a copy of the event data. If the caller passes an `EventDataRecord` instead of a dict, `EventDataRecord.add_receiving_event` records the event: the first event becomes `parent` and replaces the creating record in `parents`, and every later event is added to `parents`. A record passed to a second event is therefore listed under both events by `RMANAGER.get_children`. The triggers plugin does this with the data of `ev_to_client_data_modify`.

## Tracked network data

`NetworkDataLine` (`TrackedAttr`) declares its monitored fields with `_tracking_fields`, so the first assignment records nothing and later ones record an `update` entry. `line_modified` is set when `line` changes to a different value. `original_line` is a read-only property. A `bytearray` line, given to `__init__` or assigned to `line`, is stored as `bytes`, so it cannot change in place and `original_line` is a snapshot (#48).

`originated` and `line_type` are the `StrEnum`s `Originated` and `LineType` (in `src/bastproxy/libs/records/enums.py`, exported from `bastproxy.libs.records`). `NetworkDataLine.__init__` coerces its arguments first, so a string still works and an unknown value raises `ValueError` before any record is registered. A member equals its old string, so logs and debug output do not change. Locking these fields is tracked in #264.

`NetworkData` (`TrackedList`) converts every stored item through one hook, `_tracking_convert_item`: str, bytes and bytearray become a `NetworkDataLine`, any other type raises `TypeError`, and the list becomes the line's parent (including for a `NetworkDataLine` object given to `append`, `insert`, `extend`, `+=` or item or slice assignment). A line the list stops holding (item or slice assignment, `del`, `remove`, `pop`, `clear`, `*= 0`) is detached through the `_tracking_remove_child_tracked_item` override: the list leaves its `parents`, its `parent` becomes `None`, and `get_children` no longer lists it. A line still held at another index keeps its parent. A detached line is a pending record for the prune. `NetworkDataLine.copy_attributes` sets no parent; `split_from` links a piece to the line it came from.

**A locked write raises `RuntimeError`**:

```python
data = NetworkData("look")
data.lock()
data.append("x")        # RuntimeError (also pop, sort, +=, insert, extend, item assignment)
data[0].line = "x"      # RuntimeError
data[0].was_sent = True # allowed
```

`NetworkDataLine.lock()` locks the eleven tracked fields, including `originated`, `line_type` and `split_from` (all but `was_sent`, #264, which the network layer sets after the line is locked). `NetworkData.lock()` locks its lines through it. A second `lock()` does nothing, and `format()` does nothing on a locked line. The send steps (`SendDataDirectlyToClient`, `SendDataDirectlyToMud`) format the lines first and then lock the message, so unsent lines are locked too.

**Plugin note:** a callback on `ev_to_client_data_read` or `ev_to_mud_data_read` that writes to a line now gets a `RuntimeError`. `Event.raise_priority` logs it and continues. No bundled plugin writes in those events. Change the line in the `*_data_modify` events, before the lock.

## Common Patterns

### A custom record

```python
from bastproxy.libs.records import BaseRecord

class MyCustomRecord(BaseRecord):
    def __init__(self, data, owner_id=""):
        super().__init__(owner_id)
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
        self.addupdate("Modify", "status changed", extra={"new": "processing"})
        self.status = "complete"

MyCustomRecord({"key": "value"}, owner_id=self.plugin_id)()
```

`get_attributes_to_format()` returns sections `0` (top), `1` (middle) and `2` (bottom) of the details output.

### Logging

```python
from bastproxy.libs.logger import get_logger

logger = get_logger(__name__)
logger.info("Something happened")
get_logger(self.plugin_id).debug("Line 1\nLine 2")
logger.error("Lookup failed", exc_info=True)
```

### Recording a change

```python
record.addupdate("Modify", "Converted color codes", extra={"line": 3})

for update in record.updates:
    print(update.format_detailed())
```

### Querying relationships

```python
children = RMANAGER.get_children(record, record_filter=["NetworkDataLine"])
descendants = RMANAGER.get_all_children_list(record)
for line in RMANAGER.format_all_children(record):
    print(line)

current = record
while current.parent:
    print(current.parent.one_line_summary())
    current = current.parent
```

`record_filter` and `update_filter` take record class names. No class is filtered out by default (`RMANAGER.default_filter` was removed in #247).

## Performance Considerations

- **`NetworkDataLine` and `NetworkData` capture no stack and build no `API` per line.** Measured medians with `uv run pytest tests/benchmarks/test_bench_networkdataline.py --benchmark-enable --benchmark-only` (Python 3.12.12, one run): 18.0 us per line created (270.2 us per 15), 6.5 us per change, 26.7 us per line to build a `NetworkData`. The benchmark asserts the ADR-0005 targets of 50 us and 20 us. Locking a line records one entry per field: 70.2 us per line in the same run, with no target.
- **Processing records capture no stack and make no API call to create a record or add an update.** Measured medians with `uv run pytest tests/benchmarks/test_bench_processing_records.py --benchmark-enable --benchmark-only` (Python 3.12.12, 200 rounds, a 15-line message built outside the timed call), one run each:

  | Operation | Before #248 | After #248 |
  |-----------|-------------|------------|
  | `addupdate` | 76.8 us | 2.1 us |
  | `ProcessDataToClient` created | 92.7 us | 10.5 us |
  | created and called, no-op `_exec_` | 311.8 us | 45.6 us |

  The "before" run used a temporary patch that set the old `_SETUP_EVENTS` flag so that no events plugin was needed. The benchmark asserts the ADR-0005 target of 20 us for `addupdate`.
- **With `capture_stacks` on**, each record and update pays for a formatted call stack (10 frames per record, 15 per update) again.
- **Retention:** `RMANAGER` keeps the last `retained_trees` root trees (100 by default) and evicts each older tree whole, and each record keeps up to `tracking_max_changes` updates (1000 by default). The cap counts trees, not bytes. Measured with 15-line `ProcessDataToClient` rounds under `tracemalloc` (1,500 rounds, one run): before this change traced memory grew by about 0.68 MB per round, to 1012.3 MB; with 100 trees it stayed at 68.5 MB from round 250 to round 1,500, with 2,424 stored records. One `prune()` took 1.9 to 2.3 ms in steady state (3.5 ms for the first). See [Record System Findings](record_system_findings.md#q3-what-is-kept-and-what-does-it-cost) for measurements.
- **Records are kept only in memory, by design.** Trees beyond the last `retained_trees` are gone, and none survive a restart. Persisting records was considered in #82 and not pursued: the retention cap already bounds memory, writing every line and change to disk would cost time on the hot path, and the raw MUD and client I/O already persists in the network data log (`data/logs/networkdata/networkdata.log` under `BASTPROXY_HOME`, rotated at midnight).
- **Inspecting adds records:** every line printed by the records commands is a `NetworkDataLine`, so a long listing can push older records out of the store.
- **Tree queries scan every stored record** at each level of the tree.

#43 replaced the tracking with pydatatracker in slices; #248 is the last one.

## Known Gaps

| Issue | Gap |
|-------|-----|
| #83 | Telnet negotiation and protocol messages are not tracked as records |

## Best Practices

1. **Give records a meaningful owner ID**, usually `self.plugin_id`
2. **Record state changes with `addupdate()`**: a plain `BaseRecord` watches no attributes
3. **Run record code under a `tracking_actor(...)`** so the update shows who made it
4. **Write clear update actions** and put details in `extra`
5. **Log through `get_logger` or `log_to`** with lazy `%` arguments, see [Logging System](logging_system.md)
6. **Don't hold references to old records** longer than needed: they keep their parents and updates alive
7. **When debugging**, load `plugins.debug.records`, follow `parent` up and `children` down, and read each update's `actor`; turn on `capture_stacks` when you need stacks
