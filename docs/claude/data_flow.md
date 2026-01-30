# Data Flow

## Overview

Data flow in bastproxy describes how network data moves through the system between MUDs (Multi-User Dungeons) and connected clients. The proxy sits between clients and the MUD, intercepting, processing, and potentially modifying all data in both directions.

The data flow system is built on:
- **Record-based tracking**: Every piece of data is wrapped in a record with full change history
- **Event-driven processing**: Data transformation happens through prioritized events
- **Plugin extensibility**: Plugins can intercept and modify data at multiple points
- **Async I/O**: All network operations use asyncio with queue-based message passing
- **Bidirectional flow**: Data flows from MUD to clients and from clients to MUD

## System Architecture

```
                           BASTPROXY
    ┌────────────────────────────────────────────────────────┐
    │                                                        │
    │   ┌──────────────────┐      ┌────────────────────┐    │
    │   │ ClientConnection │      │   MudConnection    │    │
    │   │  (client.py)     │      │    (mud.py)        │    │
    │   │                  │      │                    │    │
    │   │  client_read()   │      │    mud_read()      │    │
    │   │  client_write()  │      │    mud_write()     │    │
    │   │  send_queue      │      │    send_queue      │    │
    │   └────────┬─────────┘      └─────────┬──────────┘    │
    │            │                          │               │
    │            ▼                          ▼               │
    │   ┌────────────────────────────────────────────┐      │
    │   │            Processing Records              │      │
    │   │  ProcessDataToMud / SendDataDirectlyToMud  │      │
    │   │  ProcessDataToClient / SendDataDirectlyToClient   │
    │   └────────────────────┬───────────────────────┘      │
    │                        │                              │
    │                        ▼                              │
    │   ┌────────────────────────────────────────────┐      │
    │   │              Event System                  │      │
    │   │  ev_to_mud_data_modify                     │      │
    │   │  ev_to_client_data_modify                  │      │
    │   │  ev_to_mud_data_read                       │      │
    │   │  ev_to_client_data_read                    │      │
    │   └────────────────────┬───────────────────────┘      │
    │                        │                              │
    │                        ▼                              │
    │   ┌────────────────────────────────────────────┐      │
    │   │                PLUGINS                     │      │
    │   │  Commands, Triggers, Aliases, etc.         │      │
    │   └────────────────────────────────────────────┘      │
    │                                                        │
    └────────────────────────────────────────────────────────┘
            │                               │
            ▼                               ▼
    ┌───────────────┐               ┌───────────────┐
    │   CLIENT(S)   │               │     MUD       │
    │  (telnet)     │               │   (server)    │
    └───────────────┘               └───────────────┘
```

## Connection Management

### ClientConnection Class

**Location**: `libs/net/client.py:66-477`

Manages individual client connections to the proxy.

```python
class ClientConnection:
    def __init__(self, addr, port, conn_type, reader, writer, rows=24):
        self.uuid = uuid4().hex           # Unique client identifier
        self.connected: bool = True        # Connection state
        self.state = {"logged in": False}  # Login state
        self.view_only = False             # View-only mode flag
        self.send_queue: asyncio.Queue     # Outbound message queue
        self.reader: TelnetReaderUnicode   # telnetlib3 reader
        self.writer: TelnetWriterUnicode   # telnetlib3 writer
```

**Key Methods**:

| Method | Lines | Description |
|--------|-------|-------------|
| `setup_client()` | 163-234 | Sends initial telnet options and login prompt |
| `client_read()` | 330-399 | Async loop reading from client, creates `ProcessDataToMud` |
| `client_write()` | 401-477 | Async loop writing from `send_queue` to client |
| `send_to()` | 125-161 | Adds `NetworkDataLine` to `send_queue` |

**Data Reception Flow** (`client_read` lines 330-399):
```python
async def client_read(self):
    while self.connected:
        inp: str = await self.reader.readline()  # Line 354

        if not self.state["logged in"]:
            self.process_data_from_not_logged_in_client(inp)
            continue

        if self.view_only:
            self.process_data_from_view_only_client(inp)
        else:
            # Lines 383-389: Create and execute ProcessDataToMud
            ProcessDataToMud(
                NetworkData(
                    NetworkDataLine(inp.strip(), originated="client"),
                    owner_id=f"client:{self.uuid}",
                ),
                client_id=self.uuid,
            )()
```

### MudConnection Class

**Location**: `libs/net/mud.py:63-412`

Manages the connection to the MUD server.

```python
class MudConnection:
    def __init__(self, addr: str, port: str):
        self.addr: str = addr
        self.port: str = port
        self.connected = True
        self.send_queue: asyncio.Queue[NetworkDataLine]  # Outbound queue
        self.reader: TelnetReaderUnicode | None = None
        self.writer: TelnetWriterUnicode | None = None
```

**Key Methods**:

| Method | Lines | Description |
|--------|-------|-------------|
| `setup_mud()` | 167-201 | Advertises telnet features to MUD |
| `mud_read()` | 203-279 | Async loop reading from MUD, creates `ProcessDataToClient` |
| `mud_write()` | 281-351 | Async loop writing from `send_queue` to MUD |
| `send_to()` | 131-165 | Adds `NetworkDataLine` to `send_queue` |

**Data Reception Flow** (`mud_read` lines 203-279):
```python
async def mud_read(self):
    while self.connected and self.reader:
        data = NetworkData([], owner_id="mud_read")
        while True:
            inp = await self.reader.readline()  # Line 229
            if not inp:
                break
            data.append(NetworkDataLine(inp.rstrip(), originated="mud"))
            if len(self.reader._buffer) <= 0 or b"\n" not in self.reader._buffer:
                break

        # Line 274: Create and execute ProcessDataToClient
        ProcessDataToClient(data)()
```

## Data Records

### NetworkDataLine

**Location**: `libs/records/rtypes/networkdata.py:17-301`

Represents a single line of network data with full change tracking.

```python
class NetworkDataLine(BaseRecord):
    def __init__(
        self,
        line: str | bytes | bytearray,
        originated: str = "internal",     # "mud", "client", or "internal"
        line_type: str = "IO",            # "IO" or "COMMAND-TELNET"
        had_line_endings: bool = True,
        preamble: bool = True,
        prelogin: bool = False,
        color: str = "",
    ):
        self.line = line                  # Current content (mutable)
        self.original_line = line         # Original content (locked)
        self.send: bool = True            # Whether to send this line
        self.is_prompt: bool = False      # Mark as MUD prompt
        self.was_sent: bool = False       # Tracking flag
```

**Key Properties**:

| Property | Lines | Description |
|----------|-------|-------------|
| `noansi` | 103-113 | Line with ANSI codes stripped |
| `colorcoded` | 115-125 | Line with ANSI converted to color codes |
| `is_command_telnet` | 156-158 | True if telnet command |
| `is_io` | 160-163 | True if normal I/O |
| `internal` | 165-168 | True if originated internally |
| `fromclient` | 170-173 | True if from client |
| `frommud` | 175-178 | True if from MUD |

**Key Methods**:

| Method | Lines | Description |
|--------|-------|-------------|
| `lock()` | 127-137 | Lock all attributes to prevent modification |
| `format()` | 239-249 | Apply preamble, colors, line endings |
| `color_line()` | 201-226 | Apply color and convert to ANSI |
| `add_preamble()` | 293-300 | Add "#BP:" prefix for internal messages |
| `add_line_endings()` | 180-183 | Add `\n\r` to line |

### NetworkData

**Location**: `libs/records/rtypes/networkdata.py:303-412`

Container for multiple `NetworkDataLine` objects with automatic conversion.

```python
class NetworkData(TrackedUserList):
    def __init__(
        self,
        message: NetworkDataLine | str | bytes | list | None = None,
        owner_id: str = "",
    ):
        # Automatically converts strings/bytes to NetworkDataLine
        # All items are NetworkDataLine objects with parent tracking
```

**Key Features**:
- Automatic conversion of strings/bytes to `NetworkDataLine`
- Type validation on all list operations
- Parent-child relationship tracking
- Change history via `TrackedUserList`

## Processing Records

### ProcessDataToMud

**Location**: `libs/records/rtypes/muddata.py:19-142`

Processes client input before sending to MUD. Allows plugins to modify/intercept commands.

```python
class ProcessDataToMud(BaseRecord):
    def __init__(
        self,
        message: NetworkData,
        show_in_history: bool = True,
        client_id=None,
        parent=None,
    ):
        self.message = message
        self.client_id = client_id
        self.modify_data_event_name = "ev_to_mud_data_modify"
```

**Execution Flow** (`_exec_` lines 123-142):
```python
def _exec_(self):
    # Step 1: Split multi-commands (lines 83-121)
    self.seperate_commands()

    # Step 2: Raise modify event for client I/O lines
    if data_for_event := [
        line for line in self.message if line.fromclient and line.is_io
    ]:
        self.api("plugins.core.events:raise.event")(
            self.modify_data_event_name,  # "ev_to_mud_data_modify"
            event_args={
                "showinhistory": self.show_in_history,
                "client_id": self.client_id,
            },
            data_list=data_for_event,
            key_name="line",
        )

    # Step 3: Send to MUD
    SendDataDirectlyToMud(self.message, client_id=self.client_id, parent=self)()
```

### SendDataDirectlyToMud

**Location**: `libs/records/rtypes/muddata.py:145-200`

Sends data directly to MUD bypassing modification events.

```python
class SendDataDirectlyToMud(BaseRecord):
    def __init__(
        self,
        message: NetworkData,
        show_in_history: bool = True,
        client_id=None,
        parent=None,
    ):
        self.message = message
        self.read_data_event_name = "ev_to_mud_data_read"
```

**Execution Flow** (`_exec_` lines 185-200):
```python
def _exec_(self):
    self.message.lock()
    if mud_connection := self.api("plugins.core.proxy:get.mud.connection")():
        for line in self.message:
            if line.send:
                line.format()        # Apply formatting
                line.lock()          # Lock from further changes
                mud_connection.send_to(line)  # Add to MUD's send_queue

    # Raise read-only event for observation
    if data_for_event := [line.line for line in self.message if line.send]:
        self.api("plugins.core.events:raise.event")(
            self.read_data_event_name,  # "ev_to_mud_data_read"
            data_list=data_for_event,
            key_name="line"
        )
```

### ProcessDataToClient

**Location**: `libs/records/rtypes/clientdata.py:19-177`

Processes MUD output before sending to clients. Allows plugins to modify/filter output.

```python
class ProcessDataToClient(BaseRecord):
    def __init__(
        self,
        message: NetworkData,
        clients: list | None = None,
        exclude_clients: list | None = None,
        preamble=True,
        prelogin: bool = False,
        error: bool = False,
        color_for_all_lines=None,
    ):
        self.message = message
        self.send_to_clients: bool = True
        self.clients: list[str] = clients or []
        self.exclude_clients: list[str] = exclude_clients or []
        self.modify_data_event_name = "ev_to_client_data_modify"
```

**Execution Flow** (`_exec_` lines 162-176):
```python
def _exec_(self):
    # Raise modify event for MUD I/O lines
    if data_for_event := [
        line for line in self.message if line.frommud and line.is_io
    ]:
        self.api("plugins.core.events:raise.event")(
            self.modify_data_event_name,  # "ev_to_client_data_modify"
            data_list=data_for_event,
            key_name="line"
        )

    # Send to clients if not blocked
    if self.send_to_clients:
        SendDataDirectlyToClient(
            self.message,
            exclude_clients=self.exclude_clients,
            clients=self.clients
        )()
```

### SendDataDirectlyToClient

**Location**: `libs/records/rtypes/clientdata.py:179-283`

Sends data directly to clients bypassing modification events.

```python
class SendDataDirectlyToClient(BaseRecord):
    def __init__(
        self,
        message: NetworkData,
        clients: list | None = None,
        exclude_clients: list | None = None,
    ):
        self.message = message
        self.clients: list[str] = clients or []
        self.exclude_clients: list[str] = exclude_clients or []
        self.read_data_event_name = "ev_to_client_data_read"
```

**Execution Flow** (`_exec_` lines 253-282):
```python
def _exec_(self):
    self.message.lock()
    for line in self.message:
        if line.send:
            line.format()  # Apply preamble, colors, line endings
            line.lock()    # Lock from further changes

            # Get target clients
            clients = self.clients or self.api(
                "plugins.core.clients:get.all.clients"
            )(uuid_only=True)

            for client_uuid in clients:
                if self.can_send_to_client(client_uuid, line):
                    self.api("plugins.core.clients:send.to.client")(
                        client_uuid, line
                    )

    # Raise read-only event for observation
    if data_for_event := [line.line for line in self.message if line.send]:
        self.api("plugins.core.events:raise.event")(
            self.read_data_event_name,  # "ev_to_client_data_read"
            data_list=data_for_event,
            key_name="line"
        )
```

**Client Filtering** (`can_send_to_client` lines 229-251):
- Checks `exclude_clients` list first
- Blocks internal messages to view-only clients
- Verifies client is logged in or `prelogin` flag is set

## Event Integration

### Event System Overview

**Location**: `plugins/core/events/libs/_event.py:27-287`

Events use priority-based execution where lower numbers execute first.

```python
class Event:
    def __init__(self, name, created_by="", description=None, arg_descriptions=None):
        self.name: str = name
        self.priority_dictionary = {}  # {priority: {callback: executed}}
        self.raised_count = 0
```

**Registration** (`register` lines 80-102):
```python
def register(self, func, func_owner_id, prio=50):
    priority = prio or 50
    if priority not in self.priority_dictionary:
        self.priority_dictionary[priority] = {}

    call_back = Callback(func.__name__, func_owner_id, func)
    self.priority_dictionary[priority][call_back] = False
```

**Raising Events** (`raise_event` lines 254-286):
```python
def raise_event(self, data, actor, data_list=None, key_name=None):
    self.raised_count += 1

    if not isinstance(data, EventDataRecord):
        data = EventDataRecord(owner_id=actor, event_name=self.name, data=data)

    self.active_event = ProcessRaisedEvent(self, data, actor)
    self.active_event(actor, data_list=data_list, key_name=key_name)
```

### Data Flow Events

| Event | Type | Raised By | Purpose |
|-------|------|-----------|---------|
| `ev_to_mud_data_modify` | Modify | `ProcessDataToMud` | Intercept/modify client commands before MUD |
| `ev_to_mud_data_read` | Read-only | `SendDataDirectlyToMud` | Observe data sent to MUD |
| `ev_to_client_data_modify` | Modify | `ProcessDataToClient` | Intercept/modify MUD output before clients |
| `ev_to_client_data_read` | Read-only | `SendDataDirectlyToClient` | Observe data sent to clients |

### Event Priority Guidelines

| Priority Range | Purpose | Examples |
|----------------|---------|----------|
| 1-25 | Early inspection | Logging, raw data capture |
| 26-49 | Pre-processing | Command detection, prompt handling |
| 50 | Default | Most plugin registrations |
| 51-75 | Post-processing | Triggers, gagging, highlighting |
| 76-99 | Final formatting | Color application, cleanup |

### Using @RegisterToEvent Decorator

```python
from bastproxy.plugins.core.events import RegisterToEvent

class MyPlugin(BasePlugin):
    @RegisterToEvent(event_name="ev_to_client_data_modify", priority=50)
    def _eventcb_process_mud_output(self):
        event_record = self.api("plugins.core.events:get.current.event.record")()
        line = event_record["line"]

        # Modify the line
        if "spam" in line.noansi:
            line.send = False  # Gag this line
```

## Data Flow Paths

### Client Command to MUD

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        CLIENT COMMAND TO MUD                               │
└────────────────────────────────────────────────────────────────────────────┘

Client                                                                    MUD
  │                                                                        │
  │  "cast fireball"                                                       │
  ▼                                                                        │
┌─────────────────────────────────────────┐                                │
│ ClientConnection.client_read()          │ libs/net/client.py:330-399     │
│   inp = await self.reader.readline()    │ Line 354                       │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ ProcessDataToMud(NetworkData(...))()    │ libs/net/client.py:383-389     │
│   message = NetworkData(                │                                │
│     NetworkDataLine(inp, "client")      │                                │
│   )                                     │                                │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ ProcessDataToMud._exec_()               │ muddata.py:123-142             │
│   1. seperate_commands()                │ Line 127 (split on |)          │
│   2. raise "ev_to_mud_data_modify"      │ Lines 129-140                  │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ Event: ev_to_mud_data_modify            │                                │
│                                         │                                │
│ Priority 50: Commands plugin            │ _commands.py:1224-1260         │
│   - Check for command prefix (#bp)      │                                │
│   - Execute internal commands           │                                │
│   - Set line.send = False if handled    │                                │
│                                         │                                │
│ Priority 50: Aliases plugin             │                                │
│   - Expand alias patterns               │                                │
│   - Modify line.line content            │                                │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ SendDataDirectlyToMud._exec_()          │ muddata.py:185-200             │
│   1. message.lock()                     │ Line 187                       │
│   2. for line in message:               │                                │
│        line.format()                    │ Line 191                       │
│        line.lock()                      │ Line 192                       │
│        mud_connection.send_to(line)     │ Line 193                       │
│   3. raise "ev_to_mud_data_read"        │ Lines 197-200                  │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ MudConnection.send_to(line)             │ libs/net/mud.py:131-165        │
│   send_queue.put_nowait(line)           │ Line 165                       │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ MudConnection.mud_write()               │ libs/net/mud.py:281-351        │
│   msg = await send_queue.get()          │ Line 305                       │
│   self.writer.write(msg.line)           │ Line 319                       │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    └──────────────────────────────────────────────────────▶
                                                                    "cast fireball\n\r"
```

### MUD Response to Client

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        MUD RESPONSE TO CLIENT                              │
└────────────────────────────────────────────────────────────────────────────┘

MUD                                                                   Client
  │                                                                        │
  │  "You cast fireball!"                                                  │
  ▼                                                                        │
┌─────────────────────────────────────────┐                                │
│ MudConnection.mud_read()                │ libs/net/mud.py:203-279        │
│   data = NetworkData([])                │ Line 227                       │
│   while True:                           │                                │
│     inp = await reader.readline()       │ Line 229                       │
│     data.append(NetworkDataLine(        │ Line 243                       │
│       inp, originated="mud"))           │                                │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ ProcessDataToClient(data)()             │ libs/net/mud.py:274            │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ ProcessDataToClient._exec_()            │ clientdata.py:162-176          │
│   raise "ev_to_client_data_modify"      │ Lines 166-171                  │
│     for frommud and is_io lines         │                                │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ Event: ev_to_client_data_modify         │                                │
│                                         │                                │
│ Priority 50: Triggers plugin            │ _triggers.py:652-692           │
│   - Match line against trigger patterns │                                │
│   - Execute trigger actions             │                                │
│   - Can gag (line.send = False)         │                                │
│                                         │                                │
│ Priority 50: Highlights plugin          │                                │
│   - Apply color highlights              │                                │
│   - Modify line.line with colors        │                                │
│                                         │                                │
│ Priority 50: Substitutions plugin       │                                │
│   - Replace text patterns               │                                │
│   - Modify line.line content            │                                │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ SendDataDirectlyToClient._exec_()       │ clientdata.py:253-282          │
│   1. message.lock()                     │ Line 255                       │
│   2. for line in message:               │                                │
│        line.format()                    │ Line 258                       │
│        line.lock()                      │ Line 259                       │
│        for client in clients:           │                                │
│          if can_send_to_client():       │ Lines 261-268                  │
│            send.to.client(uuid, line)   │ Line 266-267                   │
│   3. raise "ev_to_client_data_read"     │ Lines 279-282                  │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ ClientConnection.send_to(line)          │ libs/net/client.py:125-161     │
│   send_queue.put_nowait(line)           │ Line 161                       │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ ClientConnection.client_write()         │ libs/net/client.py:401-477     │
│   msg = await send_queue.get()          │ Line 424                       │
│   self.writer.write(msg.line)           │ Line 438                       │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    └──────────────────────────────────────────────────────▶
                                                             "You cast fireball!\n\r"
```

### Internal Message to Client

```
┌────────────────────────────────────────────────────────────────────────────┐
│                     INTERNAL MESSAGE TO CLIENT                             │
└────────────────────────────────────────────────────────────────────────────┘

Plugin                                                                Client
  │                                                                        │
  │  "Timer completed"                                                     │
  ▼                                                                        │
┌─────────────────────────────────────────┐                                │
│ Plugin creates message:                 │                                │
│   msg = NetworkData("Timer completed")  │                                │
│   SendDataDirectlyToClient(msg)()       │                                │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    ▼                                                      │
┌─────────────────────────────────────────┐                                │
│ SendDataDirectlyToClient._exec_()       │ clientdata.py:253-282          │
│   line.format():                        │                                │
│     - add_preamble() → "#BP: "          │ networkdata.py:293-300         │
│     - color_line()                      │ networkdata.py:201-226         │
│     - add_line_endings() → "\n\r"       │ networkdata.py:180-183         │
│   send to all logged-in clients         │                                │
└───────────────────┬─────────────────────┘                                │
                    │                                                      │
                    └──────────────────────────────────────────────────────▶
                                                          "#BP: Timer completed\n\r"
```

## Plugin Interaction Patterns

### Commands Plugin

**Location**: `plugins/core/commands/plugin/_commands.py:1224-1260`

```python
@RegisterToEvent(event_name="ev_to_mud_data_modify")
def _eventcb_check_for_command(self) -> None:
    """Check if the line is a command from the client."""
    commandprefix = self.api("plugins.core.settings:get")(
        self.plugin_id, "cmdprefix"
    )

    event_record = self.api("plugins.core.events:get.current.event.record")()

    if event_record["line"].line.startswith(commandprefix):
        self.run_internal_command_from_event()  # Handles #bp commands
    else:
        self.pass_through_command_from_event()  # Passes to MUD
```

### Triggers Plugin

**Location**: `plugins/core/triggers/plugin/_triggers.py:652-692`

```python
@RegisterToEvent(event_name="ev_to_client_data_modify")
def _eventcb_check_trigger(self):
    """Check a line of text from the mud to see if it matches any triggers."""
    event_record = self.api("plugins.core.events:get.current.event.record")()

    line = event_record["line"]
    if line.internal:
        return  # Don't process internal messages

    data = line.noansi

    # Check against compiled regex patterns
    if self.created_regex["created_regex_compiled"]:
        match_data = self.created_regex["created_regex_compiled"].match(data)
        if match_data:
            self.process_match(line, match_data.groupdict().keys())
```

### Common Patterns

#### Gag (Hide) Lines

```python
@RegisterToEvent(event_name="ev_to_client_data_modify", priority=50)
def _eventcb_gag_spam(self):
    """Gag spam lines."""
    event_record = self.api("plugins.core.events:get.current.event.record")()
    line = event_record["line"]

    if "spam message" in line.noansi:
        line.send = False  # Line will not be sent to clients
```

#### Highlight Text

```python
@RegisterToEvent(event_name="ev_to_client_data_modify", priority=50)
def _eventcb_highlight(self):
    """Highlight important text."""
    event_record = self.api("plugins.core.events:get.current.event.record")()
    line = event_record["line"]

    if "important" in line.noansi:
        line.line = f"@R{line.noansi}@w"  # Make red
        line.color = "@R"
```

#### Alias Expansion

```python
@RegisterToEvent(event_name="ev_to_mud_data_modify", priority=50)
def _eventcb_alias(self):
    """Expand aliases."""
    event_record = self.api("plugins.core.events:get.current.event.record")()
    line = event_record["line"]

    if line.noansi == "gg":
        line.line = "get gold from corpse"
```

#### Send Data to Clients

```python
from bastproxy.libs.records import SendDataDirectlyToClient, NetworkData

# Send to all clients
msg = NetworkData("Message to clients")
SendDataDirectlyToClient(msg)()

# Send to specific client
SendDataDirectlyToClient(msg, clients=["client-uuid"])()
```

#### Send Data to MUD

```python
from bastproxy.libs.records import SendDataDirectlyToMud, NetworkData

# Send directly (bypass events)
command = NetworkData("look")
SendDataDirectlyToMud(command)()

# Or use ProcessDataToMud to go through event system
from bastproxy.libs.records import ProcessDataToMud
ProcessDataToMud(NetworkData("look"))()
```

## Async Queue Pattern

Both connection classes use async queues for outbound data:

```
┌─────────────────┐     send_to(line)     ┌────────────────┐
│  Plugin/Record  │ ───────────────────▶  │   send_queue   │
└─────────────────┘                       │  asyncio.Queue │
                                          └───────┬────────┘
                                                  │
                                    await queue.get()
                                                  │
                                                  ▼
                                          ┌────────────────┐
                                          │   *_write()    │
                                          │  coroutine     │
                                          └───────┬────────┘
                                                  │
                                        writer.write(line)
                                                  │
                                                  ▼
                                          ┌────────────────┐
                                          │    Network     │
                                          └────────────────┘
```

This pattern:
- Allows thread-safe message queuing via `loop.call_soon_threadsafe`
- Decouples data generation from network I/O
- Enables backpressure handling through queue size
- Supports batching multiple lines before yielding

## File Reference Summary

| Component | File Path | Key Lines |
|-----------|-----------|-----------|
| **Connection Classes** | | |
| ClientConnection | `src/bastproxy/libs/net/client.py` | 66-477 |
| MudConnection | `src/bastproxy/libs/net/mud.py` | 63-412 |
| **Data Records** | | |
| NetworkDataLine | `src/bastproxy/libs/records/rtypes/networkdata.py` | 17-301 |
| NetworkData | `src/bastproxy/libs/records/rtypes/networkdata.py` | 303-412 |
| **Processing Records** | | |
| ProcessDataToMud | `src/bastproxy/libs/records/rtypes/muddata.py` | 19-142 |
| SendDataDirectlyToMud | `src/bastproxy/libs/records/rtypes/muddata.py` | 145-200 |
| ProcessDataToClient | `src/bastproxy/libs/records/rtypes/clientdata.py` | 19-177 |
| SendDataDirectlyToClient | `src/bastproxy/libs/records/rtypes/clientdata.py` | 179-283 |
| **Event System** | | |
| Event class | `src/bastproxy/plugins/core/events/libs/_event.py` | 27-287 |
| EventsPlugin | `src/bastproxy/plugins/core/events/plugin/_events.py` | 25-400 |
| **Plugin Hooks** | | |
| Commands (ev_to_mud_data_modify) | `src/bastproxy/plugins/core/commands/plugin/_commands.py` | 1224-1260 |
| Triggers (ev_to_client_data_modify) | `src/bastproxy/plugins/core/triggers/plugin/_triggers.py` | 652-692 |

## Best Practices

### Event Registration
1. Use descriptive function names starting with `_eventcb_`
2. Choose appropriate priority (default 50 is usually fine)
3. Always get event record via API, not from parameters
4. Check for `None` event record before processing

### Data Modification
1. **Check origin**: Use `line.frommud`, `line.fromclient`, `line.internal`
2. **Use noansi**: Search/match against `line.noansi`, modify `line.line`
3. **Preserve structure**: Don't add/remove line endings manually
4. **Set flags**: Use `line.send = False` instead of removing from list

### Performance
1. Skip processing early if line doesn't match criteria
2. Cache API lookups when used in loops
3. Use batch operations when modifying multiple lines
4. Don't block the event loop with synchronous operations

### Debugging
1. Use `LogRecord` with appropriate sources
2. Check `line.updates` to see modification history
3. Trace data through parent chain
4. Use data loggers (`data.client.*`, `data.mud`) for raw I/O
