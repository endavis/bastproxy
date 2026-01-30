# Record System

## Overview

The record system in bastproxy is a comprehensive tracking and auditing framework that creates immutable records for all significant data and operations flowing through the proxy. Records track their lifecycle, modifications, parent-child relationships, and execution context, providing complete visibility into system behavior.

Every piece of data (logs, network messages, events, commands) is wrapped in a record that automatically tracks:
- Creation time and location
- Modification history
- Call stack at creation
- Event stack at creation
- Parent-child relationships
- Execution time
- Updates and changes

## Key Components

### BaseRecord Class
**Location**: `libs/records/rtypes/base.py`

The foundation class for all record types:

```python
class BaseRecord(AttributeMonitor):
    def __init__(self, owner_id: str = "", track_record=True, parent=None):
        self.uuid = uuid4().hex  # Unique identifier
        self.owner_id = owner_id  # Owner (typically plugin ID)
        self.api = API(owner_id=owner_id)
        self.created = datetime.now(UTC)  # Creation timestamp
        self.updates = UpdateManager()  # Track all updates
        self.execute_time_taken = -1  # Execution time in ms
        self.parent = parent  # Parent record
        self.parents = []  # All parent records
        self.stack_at_creation = []  # Call stack when created
        self.event_stack = []  # Event stack when created
```

Features:
- **Unique UUID**: Every record has a globally unique identifier
- **Automatic Parent Tracking**: Records automatically link to parent records
- **Stack Capture**: Captures call stack and event stack at creation
- **Update Tracking**: All modifications are logged
- **Attribute Monitoring**: Changes to attributes trigger update records
- **Execution Tracking**: Can track execution time when called

### UpdateRecord Class
**Location**: `libs/records/rtypes/update.py`

Tracks individual changes to records:

```python
class UpdateRecord:
    def __init__(self, parent, flag: str, action: str,
                 extra: dict | None = None, data=None):
        self.uuid = uuid4().hex
        self.time_taken = datetime.now(UTC)
        self.parent = parent  # The record being updated
        self.flag = flag  # 'Modify', 'Set Flag', 'Info'
        self.action = action  # Description of the update
        self.extra = extra or {}  # Additional metadata
        self.data = data  # Snapshot of data after update
        self.stack = []  # Call stack at update
        self.actor = ""  # Who made the update
        self.event_stack = []  # Event stack at update
```

Update flags:
- **Modify**: Data or attribute was changed
- **Set Flag**: A flag was set
- **Info**: Informational update (lifecycle events, etc.)

### UpdateManager Class
**Location**: `libs/records/managers/updates.py`

Manages updates for a record:

```python
class UpdateManager(deque):
    def __init__(self):
        super().__init__(maxlen=1000)  # Last 1000 updates
        self.uid_mapping = {}  # UUID -> Update mapping
```

Features:
- Limited to last 1000 updates per record
- Fast UUID lookup
- Ordered by time

### RecordManager Class
**Location**: `libs/records/managers/records.py`

Global manager tracking all records:

```python
class RecordManager:
    def __init__(self):
        self.max_records = 5000  # Keep last 5000 of each type
        self.records: dict[str, SimpleQueue] = {}  # Type -> Records
        self.record_instances = {}  # UUID -> Record
        self.active_record_stack = SimpleStack()  # Active records
        self.default_filter = ["LogRecord"]  # Don't show in details
```

Responsibilities:
- Store the last 5000 records of each type
- Track currently active records
- Provide parent-child relationship queries
- Format record trees
- Garbage collect old records

### Specialized Record Types

#### BaseListRecord
**Location**: `libs/records/rtypes/base.py`

Base class for list-based records (network data, logs):

```python
class BaseListRecord(UserList, BaseRecord):
    def __init__(self, message: list | str, message_type: str = "IO",
                 internal: bool = True, owner_id: str = ""):
        self.internal = internal  # Internal vs external message
        self.message_type = message_type  # "IO", "COMMAND-TELNET", etc.
        self.original_data = []  # Original data (immutable)
        self.data = []  # Current data (mutable via tracking)
```

Methods:
- `clean()`: Clean and decode data
- `color_lines()`: Add color codes
- `add_line_endings()`: Add line endings
- `replace()`: Replace data (tracked)

#### BaseDictRecord
**Location**: `libs/records/rtypes/base.py`

Base class for dictionary-based records:

```python
class BaseDictRecord(BaseRecord, UserDict):
    def __init__(self, owner_id: str = "", data: dict | None = None):
        self.original_data = {}  # Original data (immutable)
        self.data = {}  # Current data (mutable via tracking)
```

Provides dictionary interface with automatic update tracking.

#### LogRecord
**Location**: `libs/records/rtypes/log.py`

Specialized record for log messages:

```python
class LogRecord(BaseListRecord):
    def __init__(self, message: list[str] | str, level: str = "info",
                 sources: list | None = None):
        self.level = level  # Log level: debug, info, warning, error, critical
        self.sources = []  # Source identifiers for logging
        self.wasemitted = {"console": False, "file": False, "client": False}
```

Features:
- Multiple log levels
- Multiple sources (for hierarchical loggers)
- Tracks where it was emitted
- Automatic coloring based on level
- Integration with Python logging

## How It Works

### 1. Record Creation

When a record is created:

```python
from bastproxy.libs.records import LogRecord

# Create a log record
log = LogRecord(
    "Something happened",
    level="info",
    sources=["plugins.core.commands"]
)
```

Automatically:
1. UUID is generated
2. Creation timestamp is set
3. Call stack is captured
4. Event stack is captured (if events are running)
5. Parent record is determined from active record stack
6. Record is added to RecordManager
7. Initial "Info" update is created

### 2. Parent-Child Relationships

Records automatically link to their parent:

```python
# When record B is created while record A is active:
RMANAGER.start(record_a)  # Mark A as active
record_b = SomeRecord()    # B automatically becomes child of A
RMANAGER.end(record_a)     # Mark A as complete
```

The relationship is captured in:
- `record_b.parent`: Direct parent
- `record_b.parents`: List of all parents

### 3. Update Tracking

Records track all modifications:

```python
record = BaseListRecord(["line 1", "line 2"])

# Method 1: Explicit update
record.addupdate(
    "Modify",
    "Changed first line",
    extra={"old": "line 1", "new": "modified"}
)

# Method 2: Attribute monitoring (automatic)
record.some_attribute = "new value"  # Automatically creates update
```

Updates capture:
- What changed
- When it changed
- Who changed it (from stack)
- Event context
- Data snapshot (optional)

### 4. Execution Tracking

Records can be callable to track execution:

```python
class MyRecord(BaseRecord):
    def _exec_(self):
        # Do work here
        pass

# Create and execute
record = MyRecord()
record()  # Executes _exec_() with automatic timing and tracking
```

Execution tracking:
1. Marks record as executing
2. Starts timing
3. Pushes onto active record stack
4. Calls `_exec_()`
5. Pops from active record stack
6. Records execution time
7. Adds start/finish updates

### 5. Record Retrieval

Get records from the manager:

```python
# Get records by type
log_records = RMANAGER.get_records("LogRecord", count=10)

# Get specific record by UUID
record = RMANAGER.get_record(uuid)

# Get all record types and counts
types = RMANAGER.get_types()  # [("LogRecord", 100), ("MudData", 50), ...]

# Get children of a record
children = RMANAGER.get_children(parent_record)

# Get all descendants (recursive)
all_children = RMANAGER.get_all_children_list(parent_record)
```

### 6. Formatting and Display

Records provide formatted output:

```python
# One-line summary
summary = record.one_line_summary()
# "LogRecord            abc123 Something happened"

# Detailed formatted output
details = record.get_formatted_details(
    full_children_records=True,  # Include full child details
    include_updates=True,         # Include update history
    update_filter=["UpdateRecord"],  # Filter out update records
    include_children_records=True  # Include children tree
)
```

Output includes:
- Record type and UUID
- Owner ID and creation time
- All tracked attributes
- Call stack at creation
- Event stack at creation
- Child records tree
- All updates with details

## Record Types

### Network Data Records

#### MudData
**Location**: `libs/records/rtypes/muddata.py`

Data received from or sent to the MUD:
- Tracks origin (from MUD vs to MUD)
- Network line tracking
- Telnet command handling
- Color code processing

#### ClientData
**Location**: `libs/records/rtypes/clientdata.py`

Data received from or sent to a client:
- Client ID tracking
- Line processing
- Color conversion
- Command detection

#### NetworkData
**Location**: `libs/records/rtypes/networkdata.py`

Base class for network communication records.

### Log Records

**Location**: `libs/records/rtypes/log.py`

Logging with levels and sources:

```python
LogRecord(
    "Debug message",
    level="debug",
    sources=["plugins.core.commands", "commands.handler"]
)()  # Execute to emit to loggers
```

Levels: debug, info, warning, error, critical

### Event Records

Event-related records:
- ProcessRaisedEvent: Tracks an event being raised
- EventDataRecord: Wraps event arguments

## Attribute Monitoring

Records inherit from `AttributeMonitor` which provides:

### Tracked Attributes

```python
class MyRecord(BaseRecord):
    def __init__(self):
        super().__init__()
        # Attributes to monitor
        self._attributes_to_monitor.append("my_attribute")
```

### Automatic Updates

When a monitored attribute changes:

```python
record.my_attribute = "new value"
# Automatically creates update:
# Flag: "Modify"
# Action: "my_attribute attribute changed"
# Extra: {"original": "old value", "new": "new value"}
```

### Locked Attributes

Prevent modification of attributes:

```python
record._am_lock_attribute("some_attr")
record.some_attr = "new"  # Creates update but doesn't change value
```

## Important Files

### Core Record System
- `libs/records/rtypes/base.py` - Base record classes
- `libs/records/rtypes/log.py` - Log record type
- `libs/records/rtypes/update.py` - Update record type
- `libs/records/rtypes/networkdata.py` - Network data base
- `libs/records/rtypes/muddata.py` - MUD data records
- `libs/records/rtypes/clientdata.py` - Client data records

### Managers
- `libs/records/managers/records.py` - RecordManager (RMANAGER)
- `libs/records/managers/updates.py` - UpdateManager

### Exports
- `libs/records/__init__.py` - Exports record types

## Common Patterns

### Creating a Custom Record Type

```python
from bastproxy.libs.records import BaseRecord

class MyCustomRecord(BaseRecord):
    def __init__(self, data, owner_id=""):
        super().__init__(owner_id, track_record=True)

        # Add attributes to monitor
        self._attributes_to_monitor.extend(["status", "count"])

        # Initialize state
        self.status = "pending"
        self.count = 0
        self.data = data

        # Initial update
        self.addupdate("Info", "MyCustomRecord created")

    def get_attributes_to_format(self):
        """Define which attributes to show in formatted output."""
        attributes = super().get_attributes_to_format()
        # Add to middle section
        attributes[1].extend([
            ("Status", "status"),
            ("Count", "count"),
            ("Data", "data")
        ])
        return attributes

    def _exec_(self):
        """Execute the record's action."""
        self.status = "processing"
        # Do work
        self.count += 1
        self.status = "complete"
```

### Logging with Records

```python
from bastproxy.libs.records import LogRecord

# Simple log
LogRecord("Something happened", sources=["my.module"])()

# With level
LogRecord(
    "Error occurred",
    level="error",
    sources=["plugins.core.commands"]
)()

# Multiple sources (hierarchical logging)
LogRecord(
    ["Line 1", "Line 2"],
    level="debug",
    sources=["plugins.core", "plugins.core.commands"]
)()
```

### Tracking Data Modifications

```python
from bastproxy.libs.records import BaseListRecord

# Create data record
data = BaseListRecord(["line 1", "line 2"])
data.addupdate("Info", "Initial data")

# Modify data
data.replace(["modified line"], extra={"reason": "cleanup"})

# Get modification history
for update in data.updates:
    print(update.format())
```

### Querying Record Relationships

```python
# Get children of a record
children = RMANAGER.get_children(parent_record)

# Get all descendants
all_descendants = RMANAGER.get_all_children_list(parent_record)

# Format as tree
tree = RMANAGER.format_all_children(parent_record)
for line in tree:
    print(line)
```

### Filtering Records

```python
# Get updates with filter
updates = record.get_all_updates(
    update_filter=["UpdateRecord", "LogRecord"]
)

# Get children with filter
children = RMANAGER.get_children(
    record,
    record_filter=["LogRecord"]
)
```

## Integration Points

### Event System

Records integrate with events:
- Event stack is captured at record creation
- ProcessRaisedEvent is a record type
- Event data is wrapped in EventDataRecord

### Logging System

LogRecord integrates with Python logging:
- Emits to configured loggers
- Supports hierarchical sources
- Tracks emission to console/file/client

### Network System

Network data flows through records:
- MudData for MUD communication
- ClientData for client communication
- All modifications tracked
- Complete audit trail of data transformation

### Command System

Commands create and track records:
- Command execution creates records
- Command output wrapped in records
- Complete execution history

## Performance Considerations

### Record Limits

- RecordManager keeps last 5000 records per type
- UpdateManager keeps last 1000 updates per record
- Older records/updates are automatically removed

### Tracking Control

Control tracking overhead:

```python
# Disable tracking for a record
record = BaseRecord(track_record=False)

# Don't save data in updates (saves memory)
record.addupdate("Modify", "changed", savedata=False)
```

### Filtered Queries

Use filters to reduce output:

```python
# Exclude log records from children
children = RMANAGER.get_all_children_list(
    record,
    record_filter=["LogRecord", "UpdateRecord"]
)
```

## Best Practices

### Record Creation
1. **Set Owner ID**: Always provide meaningful owner ID
   ```python
   record = MyRecord(owner_id=self.plugin_id)
   ```

2. **Initial Update**: Add informational update explaining creation
   ```python
   record.addupdate("Info", "Created for processing user input")
   ```

3. **Track Important Attributes**: Monitor attributes that change state
   ```python
   self._attributes_to_monitor.append("status")
   ```

### Updates
1. **Meaningful Descriptions**: Use clear action descriptions
   ```python
   record.addupdate("Modify", "Converted color codes to ANSI")
   ```

2. **Include Context**: Use extra dict for details
   ```python
   record.addupdate(
       "Modify",
       "Removed line",
       extra={"line_number": 5, "reason": "empty"}
   )
   ```

3. **Data Snapshots**: Save data only when needed
   ```python
   record.addupdate("Modify", "Changed", savedata=True)
   ```

### Performance
1. **Disable Tracking When Not Needed**: For high-frequency records
   ```python
   record = LogRecord("Debug", track_record=False)
   ```

2. **Use Filters**: When querying large record trees
   ```python
   children = RMANAGER.get_children(record, record_filter=["LogRecord"])
   ```

3. **Clean Up**: Don't hold references to old records unnecessarily

### Debugging
1. **Use Formatted Details**: For comprehensive debugging
   ```python
   details = record.get_formatted_details(
       include_updates=True,
       full_children_records=True
   )
   ```

2. **Check Stack Traces**: Updates capture stack at modification
   ```python
   for update in record.updates:
       print(update.actor)  # Who made the change
       print(update.stack)   # Stack at change
   ```

3. **Follow Parent Chain**: Understand data flow
   ```python
   current = record
   while current.parent:
       print(current.parent.one_line_summary())
       current = current.parent
   ```
