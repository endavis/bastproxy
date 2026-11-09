---
title: Data Flow
description: How network data moves between MUD servers and clients through the proxy
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - data-flow
  - networking
---

# Data Flow

## Overview

Data flow in bastproxy describes how network data moves between the MUD and the connected clients. The proxy sits in the middle, and every line in either direction passes through a fixed pipeline that plugins can hook.

The pipeline is built on:

- **Records**: every line, every batch of lines and every processing step is a record (see [Record System](record_system.md)). Records link to the record that was running when they were created, so one input line produces a tree of records.
- **Events**: plugins change data in transit by registering callbacks on the modify events and observe it on the read events.
- **Async I/O**: each connection has a reader coroutine and a writer coroutine joined by an `asyncio.Queue`.

The two directions are separate pipelines. Nothing links a client command to the MUD output it causes.

References in this page are to files and symbols, not line numbers, so they stay valid as the code changes.

## System Architecture

```
 client socket                                                    MUD socket
     │                                                                ▲
 ClientConnection.client_read                          MudConnection.mud_write
     │ one NetworkDataLine per input line                             │ send_queue
     ▼                                                                │
 ProcessDataToMud ──► ev_to_mud_data_modify ──► SendDataDirectlyToMud
 (split on separator)  (commands, watch)        (lock, format, queue,
                                                 raise ev_to_mud_data_read)

 MUD socket                                                       client socket(s)
     │                                                                ▲
 MudConnection.mud_read                                ClientConnection.client_write
     │ up to max_lines_to_process lines → one NetworkData             │ send_queue
     ▼                                                                │
 ProcessDataToClient ──► ev_to_client_data_modify ──► SendDataDirectlyToClient
                          (triggers)                   (lock, format, per-client
                                                        filter, raise ev_to_client_data_read)
```

| Component | File | Symbol |
|-----------|------|--------|
| Client connection | `src/bastproxy/libs/net/client.py` | `ClientConnection` |
| MUD connection | `src/bastproxy/libs/net/mud.py` | `MudConnection` |
| Line and batch records | `src/bastproxy/libs/records/rtypes/networkdata.py` | `NetworkDataLine`, `NetworkData` |
| Client → MUD steps | `src/bastproxy/libs/records/rtypes/muddata.py` | `ProcessDataToMud`, `SendDataDirectlyToMud` |
| MUD → client steps | `src/bastproxy/libs/records/rtypes/clientdata.py` | `ProcessDataToClient`, `SendDataDirectlyToClient` |
| Events | `src/bastproxy/plugins/core/events/plugin/_event.py` | `Event` |
| Event execution record | `src/bastproxy/plugins/core/events/libs/process/_raisedevent.py` | `ProcessRaisedEvent` |
| Event data record | `src/bastproxy/plugins/core/events/libs/data/_event.py` | `EventDataRecord` |
| Record store | `src/bastproxy/libs/records/managers/records.py` | `RecordManager` (`RMANAGER`) |

## Connection Management

### ClientConnection

`src/bastproxy/libs/net/client.py`, class `ClientConnection`: one instance per connected client.

| Method | Description |
|--------|-------------|
| `setup_client()` | Sends `WILL ECHO`, advertised telnet features and the password prompt (all `prelogin=True`) |
| `client_read()` | Reader coroutine: one `readline()` per line, then login handling or `ProcessDataToMud` |
| `process_data_from_not_logged_in_client()` | Compares the input with the proxy and view-only passwords |
| `process_data_from_view_only_client()` | Refuses input from view-only clients |
| `send_to()` | Puts a `NetworkDataLine` on `send_queue` through `loop.call_soon_threadsafe` |
| `client_write()` | Writer coroutine: writes queued lines, sends `IAC GA` after lines marked `is_prompt`, sets `was_sent` |

`client_read()` builds the record for each line from a logged-in, non-view-only client:

```python
ProcessDataToMud(
    NetworkData(
        NetworkDataLine(inp.rstrip("\r\n"), originated="client"),
        owner_id=f"client:{self.uuid}",
    ),
    client_id=self.uuid,
)()
```

`inp.rstrip("\r\n")` removes only the line ending, so leading whitespace in client input is kept.

### MudConnection

`src/bastproxy/libs/net/mud.py`, class `MudConnection`: the single connection to the MUD.

| Method | Description |
|--------|-------------|
| `connect_to_mud()` | Opens the telnetlib3 connection with `client_factory=MudTelnetClient` and `compression=False` |
| `setup_mud()` | Advertises the proxy's telnet features to the MUD |
| `mud_read()` | Reader coroutine: batches lines into one `NetworkData`, then `ProcessDataToClient` |
| `send_to()` | Puts a `NetworkDataLine` on `send_queue` through `loop.call_soon_threadsafe` |
| `mud_write()` | Writer coroutine: writes queued lines (`send_iac` for `COMMAND-TELNET`), sets `was_sent` |

`mud_read()` reads with the patched `unicode_readline_monkeypatch`, which splits on `\r\n`, `\n\r`, `\r\0`, `\r` and `\n`. It keeps reading complete lines into the same `NetworkData` until the reader's buffer holds no further newline or the batch reaches `max_lines_to_process` (15 by default). Then:

- If the buffer still holds a partial line (usually a prompt), it is read as one more line with `had_line_endings=False`.
- If the reader is at EOF, the connection is marked closed and the coroutine returns.
- Otherwise `ProcessDataToClient(data)()` runs for the batch, followed by `await asyncio.sleep(0)`.

## Data Records

### NetworkDataLine

`src/bastproxy/libs/records/rtypes/networkdata.py`, class `NetworkDataLine(TrackedRecordMixin, TrackedAttr)`: one line of data, tracked by pydatatracker ([ADR-0006](../decisions/0006-records-adapt-pydatatracker-containers-and-locked-writes-raise-runtimeerror.md)).

| Attribute | Meaning |
|-----------|---------|
| `line` | Current content. `bytes` for `COMMAND-TELNET` lines, `str` otherwise |
| `original_line` | Content at creation (a read-only property; writing it raises `RuntimeError`) |
| `originated` | `"mud"`, `"client"` or `"internal"` |
| `line_type` | `"IO"` or `"COMMAND-TELNET"` |
| `send` | `False` means the line is dropped (gagged) before sending |
| `is_prompt` | The client writer sends `IAC GA` after the line |
| `had_line_endings` | `add_line_endings()` only adds `\r\n` when this is set |
| `preamble`, `prelogin`, `color` | Formatting and client-filter flags |
| `was_sent` | Set by the writer coroutine |
| `line_modified` | Set when `line` changes |
| `split_from` | The line this one was split from by command splitting |

Properties: `noansi` (ANSI stripped), `colorcoded`, `is_io`, `is_command_telnet`, `internal`, `fromclient`, `frommud`.

`format()` runs at send time. For internal I/O lines it calls `add_preamble()` (`#BP: `). For client lines it calls `fix_double_command_seperator()`. Then it calls `color_line()` and `add_line_endings()`. `lock()` locks the eight content and flag fields, not `was_sent`; a write to a locked field raises `RuntimeError`. A second `lock()` and a `format()` on a locked line do nothing.

### NetworkData

`src/bastproxy/libs/records/rtypes/networkdata.py`, class `NetworkData(TrackedRecordMixin, TrackedList)`: a batch of lines.

- One hook, `_tracking_convert_item`, handles every way of storing an item: the constructor, `append`, `insert`, `extend`, `+=`, item and slice assignment. Strings, bytes and bytearrays become `NetworkDataLine`, other types raise `TypeError`, and the batch becomes the line's parent, also for a `NetworkDataLine` object passed in.
- After `lock()`, every mutation (`append`, `insert`, `extend`, `pop`, `sort`, `+=`, item assignment and so on) raises `RuntimeError`. `lock()` also locks the lines, so the send steps format the lines first and lock the batch after.
- It is a `list` subclass: there is no `.data`, and `.locked` is read-only.

## Processing Records

### ProcessDataToMud

`src/bastproxy/libs/records/rtypes/muddata.py`, class `ProcessDataToMud(BaseRecord)`. `_exec_()`:

1. `seperate_commands()`: each I/O line is split with `api.command_split_regex` (the proxy's `cmdseperator` setting, `|` by default). Each piece becomes a new `NetworkDataLine`, given the original's attributes by `copy_attributes()` (which also sets `split_from`).
2. Raises `ev_to_mud_data_modify` with `data_list=[client I/O lines]`, `key_name="line"` and the event arguments `showinhistory` and `client_id`.
3. Runs `SendDataDirectlyToMud(self.message, client_id=..., parent=self)()`.

### SendDataDirectlyToMud

Same file, class `SendDataDirectlyToMud(BaseRecord)`. `_exec_()`:

1. `message.lock()`
2. For each line with `send` set: `line.format()`, `line.lock()`, `mud_connection.send_to(line)`
3. Raises `ev_to_mud_data_read` with `data_list=[line ...]` (locked `NetworkDataLine` records)

Code that wants to send to the MUD without the modify event calls this directly.

### ProcessDataToClient

`src/bastproxy/libs/records/rtypes/clientdata.py`, class `ProcessDataToClient(BaseRecord)`. `_exec_()`:

1. Raises `ev_to_client_data_modify` with `data_list=[MUD I/O lines]`, `key_name="line"`
2. If `send_to_clients` is still set, runs `SendDataDirectlyToClient(self.message, clients=..., exclude_clients=...)()`

The constructor also accepts `preamble`, `prelogin`, `error` and `color_for_all_lines`, but `_exec_()` does not apply them, and the class's own `can_send_to_client()` is never called (#50).

### SendDataDirectlyToClient

Same file, class `SendDataDirectlyToClient(BaseRecord)`. `_exec_()`:

1. `message.lock()`
2. For each line with `send` set: `line.format()`, `line.lock()`, then for each target client (`clients`, or every client) that passes `can_send_to_client()`, `plugins.core.clients:client.send`
3. Raises `ev_to_client_data_read` with `data_list=[line ...]` (locked `NetworkDataLine` records)

`can_send_to_client(client_uuid, line)` refuses a client that is in `exclude_clients`, refuses internal lines to view-only clients that were not named in `clients`, and otherwise requires the client to be in `clients` (when set) and logged in, unless the line is `prelogin`.

Internal output (proxy messages, command output) starts here: code builds a `NetworkData` and calls `SendDataDirectlyToClient(...)()` directly, or `ProcessDataToClient(...)()` to let plugins see it first.

## Event Integration

### How a data event runs

`Event.raise_event()` (`src/bastproxy/plugins/core/events/plugin/_event.py`) wraps the event arguments in an `EventDataRecord`, a dict record, and runs a `ProcessRaisedEvent` record for it. With `data_list` and `key_name`, `ProcessRaisedEvent._exec_multi()` reuses the same `EventDataRecord` for every item. It sets `event_data["line"]` to the item and calls every callback in priority order, lower numbers first, before moving to the next item. A callback registered while the event is running is picked up on a further pass.

Callbacks fetch the record with `plugins.core.events:event.current.record.get` and change the `NetworkDataLine` inside it directly:

```python
from bastproxy.plugins.core.events import RegisterToEvent

class MyPlugin(BasePlugin):
    @RegisterToEvent(event_name="ev_to_client_data_modify", priority=50)
    def _eventcb_process_mud_output(self):
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if "spam" in line.noansi:
            line.send = False  # gag this line
```

An exception in a callback is caught and logged by `Event.raise_priority()`. The remaining callbacks still run.

### Data flow events

| Event | Raised by | `event_record["line"]` | Core listeners |
|-------|-----------|------------------------|----------------|
| `ev_to_mud_data_modify` | `ProcessDataToMud` | `NetworkDataLine` (client I/O lines) | commands, watch |
| `ev_to_mud_data_read` | `SendDataDirectlyToMud` | `NetworkDataLine` (locked, after formatting) | none |
| `ev_to_client_data_modify` | `ProcessDataToClient` | `NetworkDataLine` (MUD I/O lines) | triggers |
| `ev_to_client_data_read` | `SendDataDirectlyToClient` | `NetworkDataLine` (locked, after formatting) | none |

`ev_to_mud_data_modify` also carries `showinhistory` and `client_id`.

### Core listeners

All three register at the default priority, 50.

- **Commands** (`src/bastproxy/plugins/core/commands/plugin/_commands.py`, `_eventcb_check_for_command`): a line starting with the command prefix (`#bp`) is run as a proxy command, its `send` flag is cleared and the output is sent to the client. Other lines pass through. Lines not from the proxy are added to the command history when `showinhistory` is set.
- **Watch** (`src/bastproxy/plugins/core/watch/plugin/_watch.py`, `_eventcb_check_command`): meant to match client input against registered watch regexes and raise a per-watch event. It skips lines that are not I/O (such as `COMMAND-TELNET`) and matches each regex against the line's text; the raised event's `data` argument is that text.
- **Triggers** (`src/bastproxy/plugins/core/triggers/plugin/_triggers.py`, `_eventcb_check_trigger`): skips internal lines, matches `line.noansi` against one combined regex of all triggers, and raises the matching trigger events. Triggers can gag or change the line.

## Data Flow Paths

### Client command to MUD

```
"say hello" from a logged-in client
  ClientConnection.client_read
    └─ ProcessDataToMud(NetworkData(NetworkDataLine("say hello", originated="client")))()
         ├─ seperate_commands()                 split on the command separator
         ├─ raise ev_to_mud_data_modify          commands: "#bp..." → run, send=False
         │                                       watch: match watch regexes
         └─ SendDataDirectlyToMud(...)()
              ├─ lock message; per line: format() → "say hello\r\n", lock()
              ├─ MudConnection.send_to(line)     → send_queue
              └─ raise ev_to_mud_data_read
  MudConnection.mud_write                       writer.write(line.line), was_sent = True
```

### MUD output to clients

```
'You say, "hello"' from the MUD
  MudConnection.mud_read                        batch of complete lines (+ partial prompt line)
    └─ ProcessDataToClient(NetworkData([...]))()
         ├─ raise ev_to_client_data_modify       triggers: match, gag or change lines
         └─ SendDataDirectlyToClient(...)()
              ├─ lock message; per line: format() → adds "\r\n", lock()
              ├─ per client: can_send_to_client() → clients:client.send → send_queue
              └─ raise ev_to_client_data_read
  ClientConnection.client_write                 writer.write(line.line), IAC GA after prompts
```

### Internal message to clients

```
SendDataDirectlyToClient(NetworkData("Timer completed"))()
  per line: format() → add_preamble() "#BP: ", color_line(), add_line_endings()
  sent to every logged-in client (internal lines are not sent to view-only clients)
```

## How Each Step Is Tracked

### The record tree

Every record captures, at creation (`BaseRecord.__init__` in `src/bastproxy/libs/records/rtypes/base.py`):

- a UUID, an owner ID and the creation time
- a formatted call stack (10 frames)
- the current event stack: the names of the events being processed, from `plugins.core.events:event.stack.get`
- a parent: the one passed in, or the record on top of `RMANAGER.active_record_stack`

Calling a record (`BaseRecord.__call__`) pushes it on the active stack, runs `_exec_()`, pops it and stores `execute_time_taken`. Every record created during `_exec_()` therefore becomes its child. `__call__` uses `try/finally`, so a record whose `_exec_()` raises is still popped and no longer executing.

`RMANAGER` keeps the most recent records of each type (5000 per type by default, `RecordManager.max_records`) and finds children by scanning the stored records' `parents`.

This is the tree bastproxy built for one `say tracking demo two` round trip against a real MUD (Evennia), printed by `#bp.debug.records.children`:

```
ProcessDataToMud           23.14ms
 |-> NetworkData              'say tracking demo two'
 |   |-> NetworkDataLine      client 'say tracking demo two\r\n'
 |-> ProcessRaisedEvent       6.47ms ev_to_mud_data_modify 1
 |   |-> EventDataRecord      ev_to_mud_data_modify
 |-> SendDataDirectlyToMud    8.86ms
     |-> NetworkData          (the same record, second parent)
     |   |-> NetworkDataLine
     |-> ProcessRaisedEvent   3.37ms ev_to_mud_data_read 1
         |-> EventDataRecord

ProcessDataToClient        22.07ms   'You say, "tracking demo two"'
 |-> NetworkData                      ← no NetworkDataLine child: appended lines get no parent (#47)
 |-> ProcessRaisedEvent       4.07ms ev_to_client_data_modify 1
 |   |-> EventDataRecord
 |-> SendDataDirectlyToClient 9.92ms
     |-> NetworkData
     |-> ProcessRaisedEvent   3.61ms ev_to_client_data_read 1
         |-> EventDataRecord
```

The timings are from one run on a development machine and vary with load and plugins.

With all bundled plugins loaded (the audit probe, [Record System Findings](record_system_findings.md#q2-is-the-parentchild-tree-right)), two things differ from the tree above:

- The triggers plugin raises two more events for each MUD line, `event_t_plugins.core.triggers_beall` and `event_t_plugins.core.triggers_all`. They are children of the `ev_to_client_data_modify` event. The triggers plugin passes that event's `EventDataRecord` to them. The record keeps every event that received it as a parent (`EventDataRecord.add_receiving_event`), so it is printed under all three events. This was seen in a live run against Evennia, with `#bp.debug.records.children` on the `ev_to_client_data_modify` event, and `tests/plugins/core/events/test_event_data_parents.py` covers it:

```
ProcessRaisedEvent ev_to_client_data_modify
 |-> EventDataRecord ev_to_client_data_modify
 |-> ProcessRaisedEvent event_t_plugins.core.triggers_beall
 |   |-> EventDataRecord (same uuid)
 |-> ProcessRaisedEvent event_t_plugins.core.triggers_all
     |-> EventDataRecord (same uuid)
```
- When the client sends `say a|say b`, `seperate_commands` replaces the line with two new lines. Their `parents` is the original line, which is no longer in the `NetworkData`, so the tree prints the original line under the `NetworkData` and the two lines under it:

```
ProcessDataToMud
 |-> NetworkData
 |   |-> NetworkDataLine      client 'say a|say b'      ← no longer in the NetworkData
 |       |-> NetworkDataLine  client 'say a'
 |       |-> NetworkDataLine  client 'say b'
 |-> ProcessRaisedEvent       ev_to_mud_data_modify
 |-> SendDataDirectlyToMud    (the same NetworkData, second parent)
```

### How changes are tracked

Two systems add updates to a record's `updates`.

`NetworkDataLine` and `NetworkData` use pydatatracker ([ADR-0006](../decisions/0006-records-adapt-pydatatracker-containers-and-locked-writes-raise-runtimeerror.md)). Their `updates` is a read-only list of `TrackedUpdate` views over the container's own change entries, capped at `MAX_CHANGES` (1000).

| Mechanism | Fires on | Example |
|-----------|----------|---------|
| pydatatracker | A monitored field is reassigned, or the list is mutated, locked or unlocked | `line.send = False` records an `update` entry for `send`; `NetworkData.append(...)` records an `add` entry |
| `addupdate(...)` | Code recording what it did | Commands: "Antispam Command sent"; `ProcessRaisedEvent`: "Invoked" |

The **actor** is the context name set by `tracking_actor(...)`: the events plugin sets `<owner_id>:<callback name>` around each callback, the commands plugin sets `<plugin_id>:<command name>` around each command. Code outside both (the raw network read path) has no actor and the details show "Unknown". Entries carry no stack, and `-ss` shows nothing for these two types.

The other records (processing records, `LogRecord`, the dict records) still use `AttributeMonitor`, `TrackedUserList` and `UpdateRecord` (`src/bastproxy/libs/records/rtypes/update.py`). Each `UpdateRecord` stores the flag (`Modify`, `Set Flag` or `Info`), the action, any extra data, the event stack and a formatted call stack (15 frames). The actor is the innermost stack frame outside `libs/records/`, `libs/data`, `libs/process` and `tracking/utils`. A locked attribute ignores writes there: the attempt is recorded as an `Info` update and no error is raised (#48), and in-place changes to a monitored mutable attribute are not seen (#48).

Update history of a line, produced by a script that creates a `NetworkData`, changes the line under `tracking_actor("plugins.core.proxy:ev_mud_read")`, locks the batch and sets `was_sent` (flag, action, actor, location):

```
Modify  update  plugins.core.proxy:ev_mud_read  line
Modify  update  plugins.core.proxy:ev_mud_read  line_modified
Info    lock    (none)                          (one entry per locked field, 8 in all)
Modify  update  (none)                          was_sent
```

The details of a processing record list the updates of its child lines once each, because a record's `updates` leaves out the child entries pydatatracker copies onto the parent.

### Inspecting records

The inspection commands live in `plugins.debug.records`, which is not loaded by default:

```
#bp.core.pluginm.load plugins.debug.records
#bp.debug.records.types                       record types and how many of each are stored
#bp.debug.records.list ProcessDataToMud -c 20 the most recent records of a type
#bp.debug.records.children <uuid>             the tree under a record
#bp.debug.records.detail <uuid> [-u <update>] attributes, stacks and updates
```

Every line these commands print is itself a `NetworkDataLine`, so a long `detail` or `children` listing adds many records and can push the record you are looking for out of the store. Look up the UUIDs you need right after the data of interest arrives.

## Async Queue Pattern

Both connection classes write through an `asyncio.Queue`:

```
record / plugin ──send_to(line)──► send_queue ──await get()──► *_write() ──► socket
                (call_soon_threadsafe)
```

- `send_to()` uses `loop.call_soon_threadsafe(self.send_queue.put_nowait, line)`, so it can be called from any thread.
- The queues are unbounded (`asyncio.Queue()`). There is no backpressure: a slow client or MUD makes its queue grow.
- The writer coroutines yield with `await asyncio.sleep(0)` every `max_lines_to_process` lines, so one busy connection does not starve the others.

## Known Gaps

| Issue | Gap |
|-------|-----|
| #47 | `TrackedUserList` (not `NetworkData`) leaves several mutations untracked and ignores `lock()` |
| #48 | On `AttributeMonitor` records, locked attributes ignore writes silently and in-place changes are not tracked |
| #50 | `ProcessDataToClient` ignores `preamble`, `error` and `color_for_all_lines` |
| #43 | Replacement of the record tracking with pydatatracker: `NetworkDataLine` and `NetworkData` done; #246 to #249 remain |
| #81 | Every record and every update captures a formatted call stack and the event stack; this diagnostic capture is not configurable or cheap by default |
| #82 | Records are kept only in memory: those beyond the retention window are lost, and none survive a restart |
| #83 | Telnet negotiation and protocol messages are not tracked as records |

The audit of the record system lists the measurements and the new defects: [Record System Findings](record_system_findings.md).

## Best Practices

### Event callbacks

1. Name callbacks `_eventcb_<what>` and register them with `@RegisterToEvent`
2. Get the record with `plugins.core.events:event.current.record.get` and return early when it is `None`
3. Check the origin first: `line.frommud`, `line.fromclient`, `line.internal`
4. Match against `line.noansi`, change `line.line`
5. Gag with `line.send = False`. Don't remove lines from the list
6. Don't add line endings: `format()` does it at send time
7. Keep callbacks fast and non-blocking. They run synchronously inside the pipeline, once per line

### Debugging

1. Load `plugins.debug.records` and follow a record's tree and updates (see [Inspecting records](#inspecting-records))
2. Use `LogRecord(..., sources=[...])()`. A `LogRecord` without `sources` is not logged (#46)
3. The `data.mud` and `data.client.<uuid>` loggers record raw I/O to the network data log
