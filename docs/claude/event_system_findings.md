# Event System Analysis and Findings

**Date:** 2025-12-09
**Analyzer:** Claude Sonnet 4.5
**Scope:** Event system implementation in BastProxy

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Critical Bugs](#critical-bugs)
3. [Design Issues](#design-issues)
4. [Enhancement Recommendations](#enhancement-recommendations)
5. [Refactoring Opportunities](#refactoring-opportunities)
6. [Alternative Libraries](#alternative-libraries)
7. [Implementation Priority](#implementation-priority)
8. [Migration Strategies](#migration-strategies)

---

## Executive Summary

The BastProxy event system is a custom-built, priority-based event dispatch system that enables loose coupling between plugins. While functional, the analysis reveals several critical bugs, design limitations, and opportunities for improvement. The system lacks async support despite running in an asyncio environment, has potential memory leaks, and contains code duplication and naming inconsistencies.

**Key Findings:**
- 4 critical bugs requiring immediate attention
- 5 significant design issues affecting performance and reliability
- Multiple enhancement opportunities for async support and monitoring
- Viable migration path to battle-tested libraries like `blinker`

---

## Critical Bugs

### Bug #1: Duplicate ProcessRaisedEvent Classes ⚠️ HIGH SEVERITY

**Location:**
- `src/plugins/core/events/libs/process/_raisedevent.py:15694`
- `src/plugins/core/events/plugin/_process_event.py:17075`

**Issue:**
Two identical `ProcessRaisedEvent` class definitions exist in the codebase. This duplication creates maintenance burden and confusion about which implementation is canonical.

**Impact:**
- Code maintenance complexity
- Potential divergence between implementations
- Import confusion

**Recommendation:**
Consolidate to a single location, preferably `libs/process/_raisedevent.py`, and remove the duplicate from the plugin directory.

**Fix:**
```python
# Remove: plugins/core/events/plugin/_process_event.py
# Keep only: plugins/core/events/libs/process/_raisedevent.py

# Update imports in plugins/core/events/plugin/_event.py:
from bastproxy.plugins.core.events.libs.process._raisedevent import ProcessRaisedEvent
```

---

### Bug #2: Incomplete Refactoring - EventArgsRecord → EventDataRecord ⚠️ HIGH SEVERITY

**Location:** Multiple files

**Issue:**
`EventArgsRecord` was renamed to `EventDataRecord` but not all references were updated. This is an incomplete refactoring that will cause ImportErrors.

**Files with outdated references to EventArgsRecord:**

1. **`src/bastproxy/libs/records/__init__.py:16`** (docstring)
   ```python
   # Line 16 - needs update
   EventArgsRecord - data to send to event callbacks.
   # Should be:
   EventDataRecord - data to send to event callbacks.
   ```

2. **`src/bastproxy/plugins/core/events/libs/_event.py:21`** (import)
   ```python
   # Line 21 - needs update
   from bastproxy.libs.records import EventArgsRecord, LogRecord
   # Should be:
   from bastproxy.plugins.core.events.libs.data._event import EventDataRecord
   from bastproxy.libs.records import LogRecord
   ```

3. **`src/bastproxy/plugins/core/events/libs/_event.py:220`** (comment)
   ```python
   # Line 220 - needs update in comment
   # which returns event_name, EventArgsRecord
   # Should be:
   # which returns event_name, EventDataRecord
   ```

4. **`src/bastproxy/plugins/core/events/libs/_event.py:254-255`** (type hints)
   ```python
   # Lines 254-255 - needs update
   def raise_event(
       self, data: dict | EventArgsRecord, actor: str, data_list=None, key_name=None
   ) -> EventArgsRecord | None:
   # Should be:
   def raise_event(
       self, data: dict | EventDataRecord, actor: str, data_list=None, key_name=None
   ) -> EventDataRecord | None:
   ```

5. **`src/bastproxy/plugins/core/events/libs/_event.py:259-262`** (comment and error message)
   ```python
   # Lines 259-262 - needs update
   # If data is not a dict or EventArgsRecord object, log an error...
   if not isinstance(data, EventArgsRecord) and not isinstance(data, dict):
       LogRecord(
           f"... did not pass a dict or EventArgsRecord object",
   # Should be:
   # If data is not a dict or EventDataRecord object, log an error...
   if not isinstance(data, EventDataRecord) and not isinstance(data, dict):
       LogRecord(
           f"... did not pass a dict or EventDataRecord object",
   ```

6. **`src/bastproxy/plugins/core/events/libs/_event.py:273-274`** (isinstance and constructor)
   ```python
   # Lines 273-274 - needs update
   if not isinstance(data, EventArgsRecord):
       data = EventArgsRecord(owner_id=actor, event_name=self.name, data=data)
   # Should be:
   if not isinstance(data, EventDataRecord):
       data = EventDataRecord(owner_id=actor, event_name=self.name, data=data)
   ```

7. **`src/bastproxy/plugins/core/events/libs/process/_raisedevent.py:71`** (comment)
   ```python
   # Line 71 - needs update in comment
   # convert a dict to an EventArgsRecord object
   # Should be:
   # convert a dict to an EventDataRecord object
   ```

8. **`src/bastproxy/plugins/core/events/plugin/_process_event.py:71`** (comment in duplicate file)
   ```python
   # Line 71 - needs update in comment
   # convert a dict to an EventArgsRecord object
   # Should be:
   # convert a dict to an EventDataRecord object
   ```

**Impact:**
- **ImportError** when `plugins/core/events/libs/_event.py` is imported
- Code in `plugins/core/events/libs/_event.py` cannot execute
- Type hints are incorrect, confusing for developers and type checkers

**Why it hasn't failed yet:**
- The actual plugin uses `plugins/core/events/plugin/_event.py` which was correctly updated (line 22)
- The file with the bad import (`plugins/core/events/libs/_event.py`) may not be imported at runtime
- There appear to be two Event implementations (see Bug #1)

**Fix Required:**
Update all 8 locations listed above to use `EventDataRecord` instead of `EventArgsRecord`.

---

### Bug #3: Memory Leak - Unbounded Event History ⚠️ HIGH SEVERITY

**Location:** `plugins/core/events/plugin/_event.py:16224`

**Issue:**
```python
self.raised_count = 0
# NOTE : this is an unbound dictionary, may need to limit the size
#           because of how many events will be raised
self.raised_events = {}
```

Every raised event is stored in `self.raised_events` dictionary indefinitely. In a long-running proxy with frequent events, this will cause continuous memory growth.

**Impact:**
- Memory leak in long-running processes
- Potential OOM (Out of Memory) crashes
- Performance degradation as dictionary grows

**Calculation:**
- If 100 events/second with 1KB each = 360MB/hour
- 24-hour session = 8.6GB of event history

**Recommendation:**
Implement size-limited history using `collections.OrderedDict`:

```python
from collections import OrderedDict

class Event:
    MAX_HISTORY_SIZE = 1000  # Configurable via settings

    def __init__(self, ...):
        self.raised_events = OrderedDict()

    def raise_event(self, ...):
        self.active_event = ProcessRaisedEvent(self, data, actor)
        uuid = self.active_event.uuid
        self.raised_events[uuid] = self.active_event

        # Trim old events if limit exceeded
        while len(self.raised_events) > self.MAX_HISTORY_SIZE:
            self.raised_events.popitem(last=False)

        self.active_event(actor, data_list=data_list, key_name=key_name)
        self.active_event = None
        return self.raised_events[uuid]
```

**Alternative:** Use `collections.deque` with maxlen:
```python
from collections import deque

self.raised_events_list = deque(maxlen=1000)
self.raised_events = {}  # Keep for UUID lookup, but clean periodically
```

---

### Bug #4: AttributeError in raise_event ⚠️ MEDIUM SEVERITY

**Location:** `plugins/core/events/plugin/_event.py:16087`

**Issue:**
```python
LogRecord(
    f"raise_event - event {self.name} raised by {self.called_from} did not pass...",
    level="error",
    sources=[self.created_by, "plugins.core.events"],
)()
```

The `Event` class does not have a `self.called_from` attribute. Only `ProcessRaisedEvent` has this attribute (line 15698).

**Impact:**
- `AttributeError` when logging invalid event data
- Error handling fails, masking the original issue

**Recommendation:**
```python
# Use actor parameter instead
LogRecord(
    f"raise_event - event {self.name} raised by {actor} did not pass a dict or EventDataRecord object",
    level="error",
    sources=[self.created_by, "plugins.core.events"],
)()
```

---

## Design Issues

### Issue #1: Overly Broad Exception Handling

**Location:** `plugins/core/events/plugin/_event.py:16413`

**Code:**
```python
except Exception:  # pylint: disable=broad-except
    LogRecord(
        f"raise_event - event {self.name} with function {call_back.name} raised an exception",
        level="error",
        sources=[call_back.owner_id, self.created_by],
        exc_info=True,
    )()
```

**Issue:**
Catches ALL exceptions including `KeyboardInterrupt` and `SystemExit`, preventing graceful shutdown.

**Recommendation:**
```python
except (KeyboardInterrupt, SystemExit):
    raise  # Don't catch these
except Exception as e:
    LogRecord(
        f"raise_event - event {self.name} with function {call_back.name} raised {type(e).__name__}: {e}",
        level="error",
        sources=[call_back.owner_id, self.created_by],
        exc_info=True,
    )()
```

---

### Issue #2: No Async/Await Support

**Problem:**
BastProxy is built on `asyncio`, but the event system is entirely synchronous. Event callbacks block the event loop.

**Impact:**
- I/O-bound callbacks block other async operations
- Cannot use `await` in event handlers
- Performance bottleneck for slow operations

**Example Problem:**
```python
@RegisterToEvent(event_name="ev_data_received")
def _eventcb_process_data(self):
    # This blocks the entire event loop
    result = requests.get("http://api.example.com/process")
    event_record = self.api("plugins.core.events:get.current.event.record")()
    event_record["processed"] = result.json()
```

**Recommendation:**
Add async event support:

```python
import asyncio
from typing import Union, Callable, Awaitable

class Event:
    def __init__(self, ..., async_enabled: bool = False):
        self.async_enabled = async_enabled
        # ...

    async def raise_event_async(
        self, data: dict | EventDataRecord, actor: str, **kwargs
    ) -> EventDataRecord | None:
        """Async version of raise_event."""
        self.raised_count += 1

        if not isinstance(data, EventDataRecord):
            data = EventDataRecord(owner_id=actor, event_name=self.name, data=data)

        self.active_event = ProcessRaisedEvent(self, data, actor)

        for priority in sorted(self.priority_dictionary.keys()):
            for callback in self.priority_dictionary[priority]:
                if not self.priority_dictionary[priority][callback]:
                    self.priority_dictionary[priority][callback] = True
                    result = callback.execute()

                    # Handle both sync and async callbacks
                    if asyncio.iscoroutine(result):
                        await result

        self.event.reset_event()
        return self.active_event

# Usage:
@RegisterToEvent(event_name="ev_data_received", async_callback=True)
async def _eventcb_process_data(self):
    # Can now use await
    async with aiohttp.ClientSession() as session:
        async with session.get("http://api.example.com/process") as resp:
            data = await resp.json()
    event_record = self.api("plugins.core.events:get.current.event.record")()
    event_record["processed"] = data
```

---

### Issue #3: No Thread Safety

**Problem:**
No locking mechanisms protect shared state (`priority_dictionary`, `raised_events`, `current_callback`).

**Impact:**
- Race conditions if events raised from multiple threads
- Corrupted event state
- Unpredictable behavior

**Affected Code:**
- `Event.register()` - modifies `priority_dictionary`
- `Event.unregister()` - modifies `priority_dictionary`
- `Event.raise_event()` - reads/writes multiple attributes

**Recommendation:**
```python
import threading

class Event:
    def __init__(self, ...):
        self._lock = threading.RLock()
        # ... existing init

    def register(self, func: Callable, func_owner_id: str, prio: int = 50) -> bool:
        with self._lock:
            priority = prio or 50
            if priority not in self.priority_dictionary:
                self.priority_dictionary[priority] = {}
            # ... rest of method

    def raise_event(self, ...):
        with self._lock:
            # ... event raising logic
```

Or use `asyncio.Lock` for async contexts.

---

### Issue #4: Inefficient Priority Execution Loop

**Location:** `plugins/core/events/libs/process/_raisedevent.py:15753-15767`

**Code:**
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
            priorities_done.append(priority)  # Duplicates on each iteration!
```

**Problems:**
1. `priorities_done` grows with duplicates on each iteration
2. Loop continues even when no callbacks are found
3. Inefficient `priority in priorities_done` check (O(n) for lists)

**Impact:**
- Memory waste with duplicate priority values
- Extra iterations checking already-processed priorities
- O(n²) complexity for priority checks

**Recommendation:**
```python
priorities_done = set()  # Use set for O(1) lookups
found_callbacks = True
count = 0

while found_callbacks:
    count += 1
    found_callbacks = False

    priorities = sorted(self.event.priority_dictionary.keys())
    for priority in priorities:
        if priority not in priorities_done:
            if self.event.raise_priority(priority, False):
                found_callbacks = True
            priorities_done.add(priority)

if count > 2:
    LogRecord(
        f"raise_event - event {self.event_name} required {count} passes "
        f"(callbacks registered during execution)",
        level="warning",
        sources=[self.event.created_by],
    )()
```

---

### Issue #5: Weak Type Hints

**Problems:**
1. Uses old-style union syntax (`dict | list` instead of `Union[dict, list]`)
2. String-based forward references when not necessary
3. Inconsistent type hint coverage
4. Missing generic type parameters

**Examples:**
```python
# Old style
def raise_event(
    self, data: dict | EventArgsRecord, actor: str, ...
) -> EventArgsRecord | None:

# Should be (Python 3.10+)
from typing import Optional
def raise_event(
    self, data: dict | EventDataRecord, actor: str, ...
) -> Optional[EventDataRecord]:
```

**Recommendation:**
```python
from typing import Optional, Dict, List, Callable, Any

class Event:
    def __init__(
        self,
        name: str,
        created_by: str = "",
        description: Optional[List[str]] = None,
        arg_descriptions: Optional[Dict[str, str]] = None,
    ):
        self.name: str = name
        self.created_by: str = created_by
        self.description: List[str] = description or []
        self.arg_descriptions: Dict[str, str] = arg_descriptions or {}
        self.priority_dictionary: Dict[int, Dict[Callback, bool]] = {}
        self.raised_count: int = 0
        self.raised_events: Dict[str, ProcessRaisedEvent] = {}
        self.current_callback: Optional[Callback] = None
        self.active_event: Optional[ProcessRaisedEvent] = None
```

---

## Enhancement Recommendations

### Enhancement #1: Event History Management

**Implementation:**
```python
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

@dataclass
class EventHistoryEntry:
    """Single entry in event history."""
    uuid: str
    event: ProcessRaisedEvent
    timestamp: datetime
    execution_time_ms: float

class Event:
    def __init__(self, ..., max_history: int = 1000):
        self.max_history = max_history
        self.raised_events: OrderedDict[str, EventHistoryEntry] = OrderedDict()

    def add_to_history(self, event: ProcessRaisedEvent):
        """Add event to history with size limit."""
        entry = EventHistoryEntry(
            uuid=event.uuid,
            event=event,
            timestamp=datetime.now(),
            execution_time_ms=event.execute_time_taken
        )

        self.raised_events[event.uuid] = entry

        # Trim if exceeded
        while len(self.raised_events) > self.max_history:
            self.raised_events.popitem(last=False)

    def get_history(self, limit: int = 100) -> List[EventHistoryEntry]:
        """Get recent event history."""
        return list(self.raised_events.values())[-limit:]

    def get_slow_events(self, threshold_ms: float = 100.0) -> List[EventHistoryEntry]:
        """Get events that took longer than threshold."""
        return [
            entry for entry in self.raised_events.values()
            if entry.execution_time_ms > threshold_ms
        ]
```

---

### Enhancement #2: Event Wildcards and Pattern Matching

**Use Case:**
Subscribe to multiple events with a single registration:
```python
@RegisterToEvent(event_name="ev_plugin_*", priority=50)
def _eventcb_handle_any_plugin_event(self):
    event_record = self.api("plugins.core.events:get.current.event.record")()
    # Handle any plugin-related event
```

**Implementation:**
```python
import re
from fnmatch import fnmatch

class EventsPlugin(BasePlugin):
    def __init__(self):
        self.pattern_registrations: Dict[str, List[Tuple[Callable, int]]] = {}

    @AddAPI("register.to.event.pattern", description="register to events matching pattern")
    def _api_register_to_event_pattern(self, pattern: str, func: Callable, priority: int = 50):
        """Register callback for events matching glob pattern.

        Args:
            pattern: Glob pattern like "ev_plugin_*" or "ev_*_loaded"
            func: Callback function
            priority: Execution priority
        """
        if pattern not in self.pattern_registrations:
            self.pattern_registrations[pattern] = []

        self.pattern_registrations[pattern].append((func, priority))

        # Register to all existing matching events
        for event_name in self.events.keys():
            if fnmatch(event_name, pattern):
                self.api("plugins.core.events:register.to.event")(
                    event_name, func, priority=priority
                )

    @AddAPI("add.event", description="add an event")
    def _api_add_event(self, event_name: str, created_by: str, **kwargs):
        """Override to handle pattern registrations."""
        # Create event
        event = self.api("plugins.core.events:get.event")(event_name)
        event.created_by = created_by
        # ...

        # Register pattern-matched callbacks
        for pattern, callbacks in self.pattern_registrations.items():
            if fnmatch(event_name, pattern):
                for func, priority in callbacks:
                    event.register(func, func.__self__.plugin_id, priority)
```

---

### Enhancement #3: Event Middleware/Interceptors

**Use Case:**
- Log all events
- Modify event data globally
- Implement access control
- Performance monitoring

**Implementation:**
```python
from typing import Protocol

class EventMiddleware(Protocol):
    """Protocol for event middleware."""

    def before_event(self, event: Event, data: EventDataRecord) -> EventDataRecord:
        """Called before event is raised. Can modify data."""
        ...

    def after_event(self, event: Event, data: EventDataRecord):
        """Called after event completes."""
        ...

class LoggingMiddleware:
    """Logs all events."""

    def before_event(self, event: Event, data: EventDataRecord) -> EventDataRecord:
        LogRecord(
            f"Event {event.name} starting with data: {data}",
            level="debug",
            sources=["middleware", event.created_by]
        )()
        return data

    def after_event(self, event: Event, data: EventDataRecord):
        LogRecord(
            f"Event {event.name} completed",
            level="debug",
            sources=["middleware", event.created_by]
        )()

class Event:
    def __init__(self, ...):
        self.middleware: List[EventMiddleware] = []

    def add_middleware(self, middleware: EventMiddleware):
        """Add middleware to event."""
        self.middleware.append(middleware)

    def raise_event(self, data: dict | EventDataRecord, actor: str, **kwargs):
        """Raise event with middleware support."""
        if not isinstance(data, EventDataRecord):
            data = EventDataRecord(owner_id=actor, event_name=self.name, data=data)

        # Run before middleware
        for mw in self.middleware:
            data = mw.before_event(self, data)

        # Raise event (existing logic)
        self.active_event = ProcessRaisedEvent(self, data, actor)
        # ... existing code ...

        # Run after middleware
        for mw in self.middleware:
            mw.after_event(self, data)

        return result
```

---

### Enhancement #4: Performance Monitoring

**Implementation:**
```python
from dataclasses import dataclass, field
from typing import List
from statistics import mean, median

@dataclass
class EventStats:
    """Statistics for an event."""
    event_name: str
    total_raised: int = 0
    total_callbacks_executed: int = 0
    execution_times_ms: List[float] = field(default_factory=list)
    slow_event_count: int = 0  # > 100ms
    error_count: int = 0

    @property
    def avg_execution_time_ms(self) -> float:
        return mean(self.execution_times_ms) if self.execution_times_ms else 0.0

    @property
    def median_execution_time_ms(self) -> float:
        return median(self.execution_times_ms) if self.execution_times_ms else 0.0

    @property
    def max_execution_time_ms(self) -> float:
        return max(self.execution_times_ms) if self.execution_times_ms else 0.0

class EventsPlugin(BasePlugin):
    def __init__(self):
        self.event_stats: Dict[str, EventStats] = {}

    @AddAPI("get.event.stats", description="get statistics for an event")
    def _api_get_event_stats(self, event_name: str) -> EventStats:
        """Get performance statistics for an event."""
        if event_name not in self.event_stats:
            self.event_stats[event_name] = EventStats(event_name=event_name)
        return self.event_stats[event_name]

    @AddParser(description="show event performance statistics")
    @AddArgument("event", help="event name", default="", nargs="?")
    @AddArgument("-t", "--top", help="show top N slowest events", type=int, default=10)
    def _command_stats(self):
        """Show event performance statistics."""
        args = self.api("plugins.core.commands:get.current.command.args")()

        if args["event"]:
            # Show stats for specific event
            stats = self.event_stats.get(args["event"])
            if not stats:
                return False, [f"No statistics for event {args['event']}"]

            msg = [
                f"Event: {stats.event_name}",
                f"Total Raised: {stats.total_raised}",
                f"Total Callbacks: {stats.total_callbacks_executed}",
                f"Avg Time: {stats.avg_execution_time_ms:.2f}ms",
                f"Median Time: {stats.median_execution_time_ms:.2f}ms",
                f"Max Time: {stats.max_execution_time_ms:.2f}ms",
                f"Slow Events (>100ms): {stats.slow_event_count}",
                f"Errors: {stats.error_count}",
            ]
        else:
            # Show top N slowest events
            sorted_stats = sorted(
                self.event_stats.values(),
                key=lambda s: s.avg_execution_time_ms,
                reverse=True
            )[:args["top"]]

            msg = [f"Top {args['top']} Slowest Events:", ""]
            for stats in sorted_stats:
                msg.append(
                    f"{stats.event_name:<40} "
                    f"Avg: {stats.avg_execution_time_ms:>6.2f}ms "
                    f"Max: {stats.max_execution_time_ms:>6.2f}ms "
                    f"Raised: {stats.total_raised}"
                )

        return True, msg
```

---

### Enhancement #5: Event Replay for Debugging

**Use Case:**
Replay events to reproduce bugs or test changes.

**Implementation:**
```python
import json
from pathlib import Path

class EventRecorder:
    """Record and replay events."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.recording = False
        self.recorded_events: List[Dict] = []

    def start_recording(self):
        """Start recording events."""
        self.recording = True
        self.recorded_events = []

    def stop_recording(self):
        """Stop recording events."""
        self.recording = False

    def record_event(self, event_name: str, event_data: EventDataRecord, actor: str):
        """Record an event."""
        if not self.recording:
            return

        self.recorded_events.append({
            "event_name": event_name,
            "event_data": dict(event_data.data),  # Serialize
            "actor": actor,
            "timestamp": datetime.now().isoformat()
        })

    def save_recording(self, filename: str):
        """Save recording to file."""
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(self.recorded_events, f, indent=2)

    def load_recording(self, filename: str) -> List[Dict]:
        """Load recording from file."""
        filepath = self.output_dir / filename
        with open(filepath, 'r') as f:
            return json.load(f)

    def replay(self, events_api, recorded_events: List[Dict]):
        """Replay recorded events."""
        for event_data in recorded_events:
            events_api("plugins.core.events:raise.event")(
                event_data["event_name"],
                event_args=event_data["event_data"],
                calledfrom=event_data["actor"]
            )

# Usage in EventsPlugin:
@AddParser(description="record events")
@AddArgument("action", choices=["start", "stop", "save", "replay"])
@AddArgument("-f", "--file", help="filename for save/replay")
def _command_record(self):
    """Record and replay events for debugging."""
    args = self.api("plugins.core.commands:get.current.command.args")()

    if args["action"] == "start":
        self.recorder.start_recording()
        return True, ["Started recording events"]
    elif args["action"] == "stop":
        self.recorder.stop_recording()
        return True, [f"Stopped recording. Recorded {len(self.recorder.recorded_events)} events"]
    # ... etc
```

---

### Enhancement #6: Event Validation and Schema

**Use Case:**
Ensure event data conforms to expected schema.

**Implementation:**
```python
from typing import Any, Dict, Type
from dataclasses import dataclass

@dataclass
class EventSchema:
    """Schema for event data validation."""
    event_name: str
    required_fields: Dict[str, Type]
    optional_fields: Dict[str, Type] = None

    def validate(self, data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate event data against schema.

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # Check required fields
        for field_name, field_type in self.required_fields.items():
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")
            elif not isinstance(data[field_name], field_type):
                errors.append(
                    f"Field {field_name} has wrong type. "
                    f"Expected {field_type.__name__}, got {type(data[field_name]).__name__}"
                )

        # Check optional fields if present
        if self.optional_fields:
            for field_name, field_type in self.optional_fields.items():
                if field_name in data and not isinstance(data[field_name], field_type):
                    errors.append(
                        f"Optional field {field_name} has wrong type. "
                        f"Expected {field_type.__name__}, got {type(data[field_name]).__name__}"
                    )

        return len(errors) == 0, errors

class Event:
    def __init__(self, ..., schema: Optional[EventSchema] = None):
        self.schema = schema
        # ... existing init

    def raise_event(self, data: dict | EventDataRecord, actor: str, **kwargs):
        """Raise event with optional schema validation."""
        if not isinstance(data, EventDataRecord):
            data_dict = data
            data = EventDataRecord(owner_id=actor, event_name=self.name, data=data_dict)
        else:
            data_dict = data.data

        # Validate if schema is defined
        if self.schema:
            is_valid, errors = self.schema.validate(data_dict)
            if not is_valid:
                LogRecord(
                    f"Event {self.name} data validation failed: {'; '.join(errors)}",
                    level="error",
                    sources=[actor, self.created_by]
                )()
                return None

        # ... rest of raise_event logic

# Usage:
schema = EventSchema(
    event_name="ev_to_mud_data_modify",
    required_fields={
        "line": NetworkDataLine,
        "client_id": str
    },
    optional_fields={
        "priority": int
    }
)

self.api("plugins.core.events:add.event")(
    "ev_to_mud_data_modify",
    "plugins.core.commands",
    schema=schema
)
```

---

## Refactoring Opportunities

### Refactoring #1: Extract Priority Management

**Current Problem:**
Priority management logic is scattered across `Event` and `ProcessRaisedEvent`.

**Proposed:**
```python
from dataclasses import dataclass, field
from typing import Dict, List, Set

@dataclass
class PriorityManager:
    """Manages priority-based callback execution."""
    callbacks: Dict[int, Dict[Callback, bool]] = field(default_factory=dict)

    def add_callback(self, priority: int, callback: Callback) -> bool:
        """Add a callback at a specific priority."""
        if priority not in self.callbacks:
            self.callbacks[priority] = {}

        if callback not in self.callbacks[priority]:
            self.callbacks[priority][callback] = False
            return True
        return False

    def remove_callback(self, callback: Callback) -> bool:
        """Remove a callback from all priorities."""
        for priority in self.callbacks:
            if callback in self.callbacks[priority]:
                del self.callbacks[priority][callback]
                return True
        return False

    def get_priorities(self) -> List[int]:
        """Get all priorities in sorted order."""
        return sorted(self.callbacks.keys())

    def get_callbacks_at_priority(self, priority: int) -> List[Callback]:
        """Get all callbacks at a specific priority."""
        return list(self.callbacks.get(priority, {}).keys())

    def mark_executed(self, priority: int, callback: Callback):
        """Mark a callback as executed."""
        if priority in self.callbacks and callback in self.callbacks[priority]:
            self.callbacks[priority][callback] = True

    def is_executed(self, priority: int, callback: Callback) -> bool:
        """Check if callback has been executed."""
        return self.callbacks.get(priority, {}).get(callback, False)

    def reset(self):
        """Reset all callbacks to not executed."""
        for priority in self.callbacks:
            for callback in self.callbacks[priority]:
                self.callbacks[priority][callback] = False

    def count(self) -> int:
        """Count total callbacks across all priorities."""
        return sum(len(callbacks) for callbacks in self.callbacks.values())

    def execute_all(self, executor_func: Callable[[Callback], None]) -> int:
        """Execute all callbacks in priority order.

        Args:
            executor_func: Function that executes a single callback

        Returns:
            Number of passes required (for detecting dynamic registration)
        """
        executed_priorities: Set[int] = set()
        found_callbacks = True
        pass_count = 0

        while found_callbacks:
            pass_count += 1
            found_callbacks = False

            for priority in self.get_priorities():
                was_done = priority in executed_priorities

                for callback in list(self.get_callbacks_at_priority(priority)):
                    if not self.is_executed(priority, callback):
                        executor_func(callback)
                        self.mark_executed(priority, callback)
                        found_callbacks = True

                        if was_done:
                            # Callback added during execution
                            LogRecord(
                                f"Callback {callback.name} added during event execution at priority {priority}",
                                level="warning",
                                sources=[callback.owner_id]
                            )()

                executed_priorities.add(priority)

        return pass_count

# Usage in Event class:
class Event:
    def __init__(self, ...):
        self.priority_manager = PriorityManager()
        # Remove self.priority_dictionary

    def register(self, func: Callable, func_owner_id: str, prio: int = 50) -> bool:
        callback = Callback(func.__name__, func_owner_id, func)
        return self.priority_manager.add_callback(prio, callback)

    def unregister(self, func) -> bool:
        return self.priority_manager.remove_callback(func)

    def count(self) -> int:
        return self.priority_manager.count()
```

---

### Refactoring #2: Use Dataclasses for Configuration

**Current Problem:**
Event initialization has many parameters, hard to extend.

**Proposed:**
```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass
class EventConfig:
    """Configuration for an Event."""
    name: str
    created_by: str = ""
    description: List[str] = field(default_factory=list)
    arg_descriptions: Dict[str, str] = field(default_factory=dict)
    max_history: int = 1000
    async_enabled: bool = False
    validation_schema: Optional[EventSchema] = None
    middleware: List[EventMiddleware] = field(default_factory=list)

    def validate(self) -> tuple[bool, List[str]]:
        """Validate configuration."""
        errors = []

        if not self.name:
            errors.append("Event name cannot be empty")

        if not self.name.startswith("ev_"):
            errors.append("Event name should start with 'ev_'")

        if self.max_history < 1:
            errors.append("max_history must be at least 1")

        return len(errors) == 0, errors

class Event:
    def __init__(self, config: EventConfig):
        """Initialize event with configuration."""
        is_valid, errors = config.validate()
        if not is_valid:
            raise ValueError(f"Invalid event configuration: {'; '.join(errors)}")

        self.config = config
        self.name = config.name
        self.created_by = config.created_by
        self.description = config.description
        self.arg_descriptions = config.arg_descriptions
        # ... rest of init

# Usage:
config = EventConfig(
    name="ev_plugin_loaded",
    created_by="plugins.core.events",
    description=["Raised when a plugin is loaded"],
    arg_descriptions={"plugin_id": "The ID of the loaded plugin"},
    max_history=500,
    async_enabled=True
)

event = Event(config)
```

---

### Refactoring #3: Improve Error Handling

**Proposed:**
```python
class EventError(Exception):
    """Base exception for event system errors."""
    pass

class EventCallbackError(EventError):
    """Exception raised when event callback fails."""
    def __init__(self, event_name: str, callback_name: str, original_error: Exception):
        self.event_name = event_name
        self.callback_name = callback_name
        self.original_error = original_error
        super().__init__(
            f"Callback {callback_name} failed in event {event_name}: {original_error}"
        )

class EventValidationError(EventError):
    """Exception raised when event data validation fails."""
    pass

class EventNotFoundError(EventError):
    """Exception raised when event doesn't exist."""
    pass

# Usage:
def raise_priority(self, priority, already_done: bool) -> bool:
    """Raise the event at a specific priority."""
    found = False

    for call_back in list(self.priority_dictionary[priority].keys()):
        try:
            if (...):
                call_back.execute()
                found = True

        except (KeyboardInterrupt, SystemExit):
            raise

        except Exception as e:
            error = EventCallbackError(
                event_name=self.name,
                callback_name=call_back.name,
                original_error=e
            )

            LogRecord(
                str(error),
                level="error",
                sources=[call_back.owner_id, self.created_by],
                exc_info=True,
            )()

            # Store error for later analysis
            if not hasattr(self, 'errors'):
                self.errors = []
            self.errors.append(error)

    return found
```

---

### Refactoring #4: Separate Concerns with Protocols

**Proposed:**
```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class EventCallback(Protocol):
    """Protocol for event callbacks."""

    def __call__(self) -> None:
        """Execute the callback."""
        ...

@runtime_checkable
class AsyncEventCallback(Protocol):
    """Protocol for async event callbacks."""

    async def __call__(self) -> None:
        """Execute the callback asynchronously."""
        ...

@runtime_checkable
class EventDataProvider(Protocol):
    """Protocol for objects that provide event data."""

    @property
    def data(self) -> Dict[str, Any]:
        """Get event data."""
        ...

    def __getitem__(self, key: str) -> Any:
        """Get data item by key."""
        ...

    def __setitem__(self, key: str, value: Any):
        """Set data item by key."""
        ...

# Type-safe event registration:
def register(self, func: Union[EventCallback, AsyncEventCallback], ...) -> bool:
    """Register a callback."""
    if not isinstance(func, (EventCallback, AsyncEventCallback)):
        raise TypeError(f"Callback must implement EventCallback protocol, got {type(func)}")

    # ... rest of registration
```

---

## Alternative Libraries

### Option 1: blinker (Recommended)

**Description:**
Fast, simple signal/event system used by Flask, Django, and other major frameworks.

**Pros:**
- Battle-tested and widely used
- Thread-safe by default
- Automatic weak reference cleanup (prevents memory leaks)
- Very fast (C extension available)
- Supports temporary connections
- Named signals (like events)

**Cons:**
- No built-in priority system
- Would need custom wrapper for priority support
- Less flexible than custom implementation

**Installation:**
```bash
pip install blinker
```

**Example Usage:**
```python
from blinker import signal

# Define signals (equivalent to events)
plugin_loaded = signal('plugin-loaded')
data_modified = signal('data-modified')

# Connect callbacks (with custom priority support)
class PriorityConnection:
    def __init__(self, signal_obj):
        self.signal = signal_obj
        self.connections = {}  # priority -> [callbacks]

    def connect(self, callback, priority=50):
        if priority not in self.connections:
            self.connections[priority] = []
        self.connections[priority].append(callback)

        # Wrap to maintain priority order
        def wrapper(sender, **kwargs):
            for prio in sorted(self.connections.keys()):
                for cb in self.connections[prio]:
                    cb(sender, **kwargs)

        self.signal.connect(wrapper, weak=False)

# Usage
priority_conn = PriorityConnection(plugin_loaded)
priority_conn.connect(my_callback, priority=10)

# Send signal (equivalent to raising event)
plugin_loaded.send(self, plugin_id='plugins.core.commands')

# Temporary connection
with plugin_loaded.connected_to(temp_handler):
    # temp_handler only called during this block
    plugin_loaded.send(self)
```

**Migration Effort:** Medium (2-3 weeks)

---

### Option 2: PyPubSub

**Description:**
Publish-subscribe messaging system with topic-based routing.

**Pros:**
- Topic-based hierarchy (e.g., `data.modified.client`)
- Argument specification and validation
- Supports both sync and async
- Good documentation

**Cons:**
- Heavier than blinker
- More complex API
- Topic strings can get verbose

**Installation:**
```bash
pip install pypubsub
```

**Example:**
```python
from pubsub import pub

# Subscribe
def on_plugin_loaded(plugin_id):
    print(f"Plugin {plugin_id} loaded")

pub.subscribe(on_plugin_loaded, 'plugin.loaded')

# Publish
pub.sendMessage('plugin.loaded', plugin_id='plugins.core.commands')

# Topic hierarchy
pub.subscribe(handler, 'mud.data')  # Catches mud.data.* topics
pub.sendMessage('mud.data.received', data="...")
```

**Migration Effort:** Medium (2-3 weeks)

---

### Option 3: python-dispatch

**Description:**
Property-based dispatch with multiple strategies.

**Pros:**
- Property-based events
- Thread-safe
- Multiple dispatch strategies
- Good for object-oriented code

**Cons:**
- Less widely used
- More opinionated design

**Installation:**
```bash
pip install python-dispatch
```

**Example:**
```python
from pydispatch import dispatcher

# Connect
def on_event(signal, sender, **kwargs):
    print(f"Signal {signal} from {sender}")

dispatcher.connect(on_event, signal='plugin_loaded', sender=dispatcher.Any)

# Send
dispatcher.send(signal='plugin_loaded', sender=self, plugin_id='...')
```

**Migration Effort:** Low-Medium (1-2 weeks)

---

### Option 4: Custom AsyncIO-Based System

**Description:**
Build lightweight async event system using asyncio primitives.

**Pros:**
- Perfect fit for asyncio architecture
- Full control over implementation
- No external dependencies
- Can maintain exact current API

**Cons:**
- Must maintain ourselves
- Need to ensure thread safety
- More testing required

**Example:**
```python
import asyncio
from typing import Callable, Dict, List, Awaitable, Union
from collections import defaultdict

class AsyncEventSystem:
    def __init__(self):
        self._handlers: Dict[str, Dict[int, List[Callable]]] = defaultdict(lambda: defaultdict(list))
        self._lock = asyncio.Lock()

    async def emit(self, event_name: str, **kwargs):
        """Emit an event asynchronously."""
        async with self._lock:
            handlers = self._handlers[event_name]

        # Execute in priority order
        for priority in sorted(handlers.keys()):
            for handler in handlers[priority]:
                if asyncio.iscoroutinefunction(handler):
                    await handler(**kwargs)
                else:
                    # Run sync handlers in executor to not block
                    await asyncio.get_event_loop().run_in_executor(
                        None, handler, **kwargs
                    )

    async def on(self, event_name: str, handler: Callable, priority: int = 50):
        """Register event handler."""
        async with self._lock:
            self._handlers[event_name][priority].append(handler)

    async def off(self, event_name: str, handler: Callable):
        """Unregister event handler."""
        async with self._lock:
            for priority_handlers in self._handlers[event_name].values():
                if handler in priority_handlers:
                    priority_handlers.remove(handler)

# Usage
events = AsyncEventSystem()

@events.on('data.received', priority=10)
async def handle_data(**kwargs):
    data = kwargs['data']
    # Process data
    await asyncio.sleep(0.1)  # Can await!

await events.emit('data.received', data={'key': 'value'})
```

**Migration Effort:** High (4-6 weeks)

---

### Comparison Matrix

| Feature | Current | blinker | PyPubSub | python-dispatch | Custom Async |
|---------|---------|---------|----------|-----------------|--------------|
| **Priority Support** | ✅ Yes | ❌ No | ❌ No | ❌ No | ✅ Yes |
| **Async/Await** | ❌ No | ❌ No | ✅ Yes | ❌ No | ✅ Yes |
| **Thread Safety** | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Memory Leak Risk** | ⚠️ Yes | ✅ No (weak refs) | ✅ No | ✅ No | ⚠️ Depends |
| **Battle Tested** | ⚠️ Custom | ✅ Yes | ✅ Yes | ⚠️ Moderate | ❌ No |
| **Performance** | ⚠️ Good | ✅ Excellent | ⚠️ Good | ⚠️ Good | ✅ Excellent |
| **Learning Curve** | N/A | ✅ Low | ⚠️ Medium | ⚠️ Medium | ⚠️ Medium |
| **Maintenance** | ⚠️ High | ✅ Low | ✅ Low | ⚠️ Medium | ⚠️ High |
| **Event History** | ✅ Yes | ❌ No | ❌ No | ❌ No | ✅ Yes |
| **Pattern Matching** | ❌ No | ❌ No | ✅ Yes | ❌ No | ✅ Yes |

**Recommendation:**
1. **Short-term**: Fix critical bugs in current system
2. **Medium-term**: Add async support to current system
3. **Long-term**: Consider migrating to **blinker** with custom priority wrapper

---

## Implementation Priority

### Phase 1: Critical Bug Fixes (Week 1) 🔴 HIGH PRIORITY

**Must Fix Immediately:**

1. **Fix EventArgsRecord/EventDataRecord naming**
   - Impact: ImportError at runtime
   - Effort: 1-2 hours
   - Files: 2-3 files

2. **Remove duplicate ProcessRaisedEvent**
   - Impact: Code clarity, future bugs
   - Effort: 1-2 hours
   - Files: 2 files

3. **Fix AttributeError in raise_event**
   - Impact: Error handling broken
   - Effort: 30 minutes
   - Files: 1 file

4. **Implement event history size limit**
   - Impact: Memory leak prevention
   - Effort: 2-4 hours
   - Files: 1 file

**Deliverables:**
- [ ] All imports work correctly
- [ ] No duplicate classes
- [ ] Error messages display correctly
- [ ] Memory usage stable over 24-hour run

---

### Phase 2: Design Improvements (Week 2-3) 🟡 MEDIUM PRIORITY

**Should Fix Soon:**

1. **Improve exception handling**
   - Don't catch KeyboardInterrupt/SystemExit
   - Effort: 1-2 hours
   - Files: 2 files

2. **Optimize priority execution loop**
   - Use set instead of list for priorities_done
   - Effort: 2-3 hours
   - Files: 1 file

3. **Add thread safety**
   - Add locks to Event class
   - Effort: 4-6 hours
   - Files: 2 files

4. **Improve type hints**
   - Consistent, complete type hints
   - Effort: 3-4 hours
   - Files: 4-5 files

**Deliverables:**
- [ ] Graceful shutdown works
- [ ] No duplicate priority processing
- [ ] Thread-safe event raising
- [ ] Type checking passes with mypy

---

### Phase 3: Major Enhancements (Week 4-8) 🟢 LOW PRIORITY

**Nice to Have:**

1. **Add async/await support**
   - Parallel sync/async paths
   - Effort: 2-3 weeks
   - Files: 5-10 files

2. **Add event wildcards**
   - Pattern-based subscriptions
   - Effort: 1 week
   - Files: 2-3 files

3. **Add performance monitoring**
   - Stats collection and commands
   - Effort: 1 week
   - Files: 3-4 files

4. **Add event middleware**
   - Interceptor support
   - Effort: 1-2 weeks
   - Files: 3-5 files

**Deliverables:**
- [ ] Async callbacks work
- [ ] Can subscribe with patterns
- [ ] Performance stats available
- [ ] Logging middleware works

---

### Phase 4: Architecture Evolution (Month 3+) 🔵 FUTURE

**Consider for Future:**

1. **Evaluate migration to blinker**
   - Research and prototyping
   - Effort: 2 weeks

2. **Build migration wrapper**
   - Adapter for priority support
   - Effort: 2-3 weeks

3. **Gradual migration**
   - Move events one at a time
   - Effort: 4-6 weeks

4. **Remove custom implementation**
   - Cleanup after full migration
   - Effort: 1-2 weeks

**Deliverables:**
- [ ] Proof of concept with blinker
- [ ] Priority wrapper working
- [ ] All events migrated
- [ ] Legacy code removed

---

## Migration Strategies

### Strategy 1: Fix-in-Place (Recommended for Short-Term)

**Approach:**
Fix bugs and add features to existing system.

**Pros:**
- Minimal disruption
- Quick wins
- Maintains compatibility
- Low risk

**Cons:**
- Still maintaining custom code
- Doesn't solve all architectural issues
- Technical debt remains

**Timeline:** 4-6 weeks

**Steps:**
1. Week 1: Fix critical bugs
2. Week 2-3: Design improvements
3. Week 4-6: Major enhancements
4. Ongoing: Monitoring and refinement

---

### Strategy 2: Hybrid Approach

**Approach:**
Fix critical bugs, then gradually introduce blinker alongside existing system.

**Pros:**
- Gets battle-tested library benefits
- Can migrate incrementally
- Low risk (can roll back)
- Performance improvements

**Cons:**
- Dual systems temporarily
- More complex codebase
- Need adapter layer

**Timeline:** 12-16 weeks

**Steps:**
1. Week 1-2: Fix critical bugs in current system
2. Week 3-4: Add blinker dependency and create priority wrapper
3. Week 5-8: Migrate high-traffic events to blinker
4. Week 9-12: Migrate remaining events
5. Week 13-16: Remove legacy system, cleanup

**Example Priority Wrapper:**
```python
from blinker import signal
from typing import Callable, Dict, List
import functools

class PrioritySignal:
    """Wrapper for blinker signal with priority support."""

    def __init__(self, name: str):
        self.name = name
        self.signal = signal(name)
        self.priority_handlers: Dict[int, List[Callable]] = {}

    def connect(self, handler: Callable, priority: int = 50):
        """Connect handler with priority."""
        if priority not in self.priority_handlers:
            self.priority_handlers[priority] = []
        self.priority_handlers[priority].append(handler)

        # Don't connect directly to blinker signal
        # We'll handle dispatch ourselves

    def send(self, sender, **kwargs):
        """Send signal to all handlers in priority order."""
        for priority in sorted(self.priority_handlers.keys()):
            for handler in self.priority_handlers[priority]:
                try:
                    handler(sender, **kwargs)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    # Log error
                    print(f"Handler {handler.__name__} failed: {e}")

        # Also send via blinker for any direct connections
        self.signal.send(sender, **kwargs)

    def disconnect(self, handler: Callable):
        """Disconnect handler."""
        for priority_list in self.priority_handlers.values():
            if handler in priority_list:
                priority_list.remove(handler)

# Adapter for existing API
class BlinkerEventAdapter:
    """Adapter to use blinker with existing event API."""

    def __init__(self):
        self.signals: Dict[str, PrioritySignal] = {}

    def get_event(self, event_name: str) -> PrioritySignal:
        """Get or create signal."""
        if event_name not in self.signals:
            self.signals[event_name] = PrioritySignal(event_name)
        return self.signals[event_name]

    def register_to_event(self, event_name: str, func: Callable, priority: int = 50):
        """Register handler to event."""
        event = self.get_event(event_name)
        event.connect(func, priority=priority)

    def raise_event(self, event_name: str, event_args: dict, calledfrom: str = ""):
        """Raise an event."""
        event = self.get_event(event_name)
        event.send(calledfrom, **event_args)
```

---

### Strategy 3: Big Bang Rewrite

**Approach:**
Complete rewrite to use async-native event system.

**Pros:**
- Clean architecture
- Fully async
- No technical debt
- Modern design

**Cons:**
- High risk
- Long timeline
- All events must migrate at once
- Significant testing required

**Timeline:** 16-24 weeks

**Not Recommended** due to risk and effort.

---

## Testing Strategy

### Unit Tests

**Critical Test Cases:**

```python
import pytest
from plugins.core.events.libs._event import Event
from plugins.core.events.libs.data._event import EventDataRecord

class TestEventSystem:

    def test_event_creation(self):
        """Test basic event creation."""
        event = Event("test_event", created_by="test")
        assert event.name == "test_event"
        assert event.created_by == "test"

    def test_callback_registration(self):
        """Test callback registration."""
        event = Event("test_event")

        def callback():
            pass

        assert event.register(callback, "test_owner", priority=50)
        assert event.count() == 1
        assert event.isregistered(callback)

    def test_priority_ordering(self):
        """Test callbacks execute in priority order."""
        event = Event("test_event")
        execution_order = []

        def low_priority():
            execution_order.append("low")

        def high_priority():
            execution_order.append("high")

        event.register(low_priority, "test", priority=100)
        event.register(high_priority, "test", priority=1)

        event.raise_event({}, "test")

        assert execution_order == ["high", "low"]

    def test_event_history_limit(self):
        """Test event history doesn't grow unbounded."""
        event = Event("test_event", max_history=10)

        # Raise 100 events
        for i in range(100):
            event.raise_event({"count": i}, "test")

        # Should only keep last 10
        assert len(event.raised_events) <= 10

    def test_exception_in_callback(self):
        """Test exception in callback doesn't crash system."""
        event = Event("test_event")
        execution_order = []

        def failing_callback():
            execution_order.append("fail")
            raise ValueError("Test error")

        def succeeding_callback():
            execution_order.append("success")

        event.register(failing_callback, "test", priority=1)
        event.register(succeeding_callback, "test", priority=2)

        event.raise_event({}, "test")

        # Both should execute despite exception
        assert "fail" in execution_order
        assert "success" in execution_order

    def test_dynamic_registration(self):
        """Test callback registered during event execution."""
        event = Event("test_event")
        execution_order = []

        def late_callback():
            execution_order.append("late")

        def early_callback():
            execution_order.append("early")
            # Register new callback during execution
            event.register(late_callback, "test", priority=50)

        event.register(early_callback, "test", priority=50)
        event.raise_event({}, "test")

        # Late callback should execute
        assert "late" in execution_order

    @pytest.mark.asyncio
    async def test_async_callback(self):
        """Test async callback support."""
        event = Event("test_event", async_enabled=True)
        execution_order = []

        async def async_callback():
            execution_order.append("async")
            await asyncio.sleep(0.01)

        event.register(async_callback, "test", priority=50)
        await event.raise_event_async({}, "test")

        assert "async" in execution_order
```

### Integration Tests

```python
class TestEventIntegration:

    def test_full_event_flow(self, event_plugin):
        """Test complete event flow through system."""
        # Register event
        event_plugin.api("plugins.core.events:add.event")(
            "ev_test_event",
            "test_plugin",
            description=["Test event"],
            arg_descriptions={"data": "Test data"}
        )

        # Register callback
        received_data = []

        def callback():
            record = event_plugin.api("plugins.core.events:get.current.event.record")()
            received_data.append(record["data"])

        event_plugin.api("plugins.core.events:register.to.event")(
            "ev_test_event",
            callback,
            priority=50
        )

        # Raise event
        event_plugin.api("plugins.core.events:raise.event")(
            "ev_test_event",
            event_args={"data": "test_value"}
        )

        # Verify
        assert len(received_data) == 1
        assert received_data[0] == "test_value"
```

---

## Conclusion

The BastProxy event system requires immediate attention to address critical bugs, particularly the naming inconsistency and memory leak. Short-term fixes will stabilize the system, while medium-term enhancements (async support, monitoring) will improve performance and observability.

For long-term sustainability, consider migrating to a battle-tested library like `blinker` with a custom priority wrapper. This hybrid approach balances the benefits of proven code with BastProxy's specific requirements.

### Immediate Actions

1. Fix EventArgsRecord/EventDataRecord naming bug
2. Implement event history size limit
3. Remove duplicate ProcessRaisedEvent class
4. Improve exception handling

### Success Metrics

- Zero memory growth over 24-hour stress test
- All type checks pass with mypy
- Event execution time < 1ms for simple events
- Zero crashes due to event system bugs
- 100% test coverage for event core

---

**Document Version:** 1.0
**Last Updated:** 2025-12-09
**Next Review:** After Phase 1 completion
