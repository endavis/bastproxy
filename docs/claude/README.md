# bastproxy System Documentation

## Overview

bastproxy is a MUD (Multi-User Dungeon) proxy written in Python that sits between MUD clients and MUD servers. It provides a plugin-based architecture for intercepting, processing, and modifying data flowing in both directions.

## Architecture

bastproxy is built on several core systems that work together:

```
┌─────────────────────────────────────────────────┐
│                   CLIENTS                        │
│         (Telnet, MushClient, etc.)              │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│              BASTPROXY CORE                      │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │   Events   │  │    API     │  │  Records  │ │
│  │   System   │  │   System   │  │  System   │ │
│  └────────────┘  └────────────┘  └───────────┘ │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │  Plugins   │  │ Data Flow  │  │  Logging  │ │
│  │   System   │  │            │  │           │ │
│  └────────────┘  └────────────┘  └───────────┘ │
│                                                  │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│                     MUD                          │
│              (Game Server)                       │
└─────────────────────────────────────────────────┘
```

## Core Systems Documentation

### 1. [Event System](event_system.md)

The event system is a priority-based event dispatch mechanism that allows plugins to register callbacks for specific events.

**Key Concepts:**
- Event registration and callbacks
- Priority-based execution (lower numbers execute first)
- Event data records
- Event stack tracking

**Primary Use Cases:**
- Plugin communication
- Data flow processing
- Lifecycle management
- State change notifications

### 2. [API System](api_system.md)

The API system provides a centralized registry for exposing and consuming functionality across plugins and modules.

**Key Concepts:**
- Hierarchical API naming (`plugin.id:function.name`)
- Class-level and instance-level APIs
- Automatic function discovery
- Usage statistics tracking

**Primary Use Cases:**
- Cross-plugin communication
- Function exposure and discovery
- Centralized service access
- Plugin capability queries

### 3. [Plugin System](plugin_system.md)

The plugin system provides a modular architecture where functionality is organized into independent, self-contained packages.

**Key Concepts:**
- Plugin lifecycle (load, initialize, save, unload)
- Plugin hooks for lifecycle events
- Dependency management
- Hot-reloading support

**Primary Use Cases:**
- Feature modularity
- Runtime extensibility
- Independent development
- Clean separation of concerns

### 4. [Record System](record_system.md)

The record system provides comprehensive tracking and auditing for all significant data and operations.

**Key Concepts:**
- Unique UUIDs for all records
- Parent-child relationships
- Update tracking and history
- Call stack and event stack capture

**Primary Use Cases:**
- Data auditing
- Debugging and troubleshooting
- Change history
- Performance tracking

### 5. [Data Flow](data_flow.md)

Data flow describes how network data moves through the proxy between MUDs and clients.

**Key Concepts:**
- NetworkDataLine records
- Bidirectional data flow
- Event-driven processing
- Line modification and filtering

**Primary Use Cases:**
- Data interception
- Content modification
- Triggers and automation
- Logging and analysis

### 6. [Command System](command_system.md)

The command system provides comprehensive command parsing and execution from clients.

**Key Concepts:**
- Automatic command registration via decorators
- Argument parsing with argparse
- Command history and rerun
- Fuzzy matching and help generation

**Primary Use Cases:**
- User command interface
- Plugin control and configuration
- Data queries and reporting
- System administration

### 7. [Settings System](settings_system.md)

The settings system provides centralized configuration management for all plugins.

**Key Concepts:**
- Plugin-level settings namespaces
- Type validation and persistence
- Change event notifications
- User interface for modifications

**Primary Use Cases:**
- Plugin configuration
- Runtime behavior changes
- User preferences
- System tuning

### 8. [Timers System](timers_system.md)

The timers system provides scheduled execution of functions at specified intervals.

**Key Concepts:**
- Interval-based and time-of-day timers
- One-time and recurring execution
- Async task management
- Plugin lifecycle integration

**Primary Use Cases:**
- Periodic data updates
- Scheduled maintenance
- Delayed actions
- Background tasks

### 9. [Triggers System](triggers_system.md)

The triggers system provides pattern matching on MUD output using regular expressions.

**Key Concepts:**
- Regex-based pattern matching
- Named capture groups
- Priority ordering and line omission
- Efficient regex compilation

**Primary Use Cases:**
- MUD output automation
- Data extraction and parsing
- Event-driven responses
- Content filtering

## System Integration

### How the Systems Work Together

1. **Data Arrives** (from MUD or client)
   - Wrapped in a **Record** (Record System)
   - **Event** raised (Event System)
   - **Plugins** notified (Plugin System)

2. **Plugin Processing**
   - Plugin receives event callback (Event System)
   - Accesses data via **Event Record** (Record System)
   - Calls other plugin **APIs** if needed (API System)
   - Modifies **Data** as appropriate (Data Flow)
   - Logs activity via **LogRecord** (Record System)

3. **Data Continues**
   - Modified data flows to next priority (Event System)
   - All changes tracked in **Updates** (Record System)
   - Eventually sent to destination (Data Flow)

### Example: Processing MUD Data

```python
# Plugin intercepts data from MUD
@RegisterToEvent(event_name="ev_to_client_data_modify", priority=50)
def _eventcb_process_mud_data(self):
    # Get event record (Record System)
    event_record = self.api("plugins.core.events:get.current.event.record")()

    # Access data (Data Flow)
    data = event_record["data"]

    # Process each line
    for line in data:
        # Check content
        if "important" in line.noansi:
            # Modify line (tracked automatically by Record System)
            line.line = f"@R{line.noansi}@w"

            # Call another plugin's API (API System)
            self.api("plugins.my.logger:log.important")(line.noansi)

            # Create log record
            LogRecord(
                f"Highlighted important line",
                sources=[self.plugin_id]
            )()
```

## Directory Structure

```
bastproxy/
├── src/bastproxy/
│   ├── libs/               # Core libraries
│   │   ├── api/            # API system
│   │   ├── records/        # Record system
│   │   ├── plugins/        # Plugin loader
│   │   └── net/            # Network handling
│   │
│   └── plugins/            # Plugin packages
│       ├── _baseplugin/    # Base plugin class
│       └── core/           # Core plugins
│           ├── events/     # Event system plugin
│           ├── commands/   # Command system
│           ├── clients/    # Client management
│           ├── proxy/      # Proxy management
│           └── ...
│
├── docs/                   # Documentation
│   └── claude/             # System documentation
│       ├── README.md       # This file
│       ├── event_system.md
│       ├── api_system.md
│       ├── plugin_system.md
│       ├── record_system.md
│       ├── data_flow.md
│       ├── command_system.md
│       ├── settings_system.md
│       ├── timers_system.md
│       └── triggers_system.md
│
└── data/                   # Runtime data
    ├── plugins/            # Plugin data
    └── logs/              # Log files
```

## Getting Started

### For Plugin Developers

1. **Understand the Core Systems**
   - Read the [Plugin System](plugin_system.md) documentation
   - Review the [API System](api_system.md) for cross-plugin communication
   - Study the [Event System](event_system.md) for data processing

2. **Create Your Plugin**
   ```python
   from bastproxy.plugins._baseplugin import BasePlugin
   from bastproxy.libs.api import AddAPI
   from bastproxy.plugins.core.events import RegisterToEvent

   class Plugin(BasePlugin):
       def __init__(self, plugin_id, plugin_info):
           super().__init__(plugin_id, plugin_info)

       @AddAPI("my.function", description="My function")
       def _api_my_function(self):
           return "Hello"

       @RegisterToEvent(event_name="ev_to_client_data_modify")
       def _eventcb_process_data(self):
           # Process data here
           pass
   ```

3. **Test and Debug**
   - Use the [Record System](record_system.md) for debugging
   - Review the [Data Flow](data_flow.md) for data processing

### For System Developers

1. **Architecture Overview**
   - Study all system documentation files
   - Understand system integration patterns
   - Review the codebase structure

2. **Core Concepts**
   - Everything is a record (Record System)
   - Events drive processing (Event System)
   - APIs enable communication (API System)
   - Plugins provide functionality (Plugin System)

3. **Development Workflow**
   - Changes to core systems affect all plugins
   - Maintain backward compatibility when possible
   - Document API changes
   - Test with multiple plugins

## Key Design Patterns

### 1. Record-Based Tracking

Every significant piece of data or operation is a record:
- Automatic UUID generation
- Parent-child relationships
- Complete audit trail
- Stack capture for debugging

### 2. Event-Driven Architecture

Processing happens through events:
- Loose coupling between components
- Priority-based execution
- Easy extensibility
- Clear data flow

### 3. API-Based Communication

Plugins expose and consume through APIs:
- Centralized registration
- Automatic discovery
- Usage tracking
- Version management

### 4. Plugin Modularity

Functionality is organized into plugins:
- Independent development
- Hot-reloading support
- Dependency management
- Clean interfaces

## Common Operations

### Accessing Current Event Data

```python
event_record = self.api("plugins.core.events:get.current.event.record")()
data = event_record["data"]
```

### Calling Another Plugin's API

```python
result = self.api("plugins.core.commands:run")("plugin.id", "command", "args")
```

### Logging

```python
from bastproxy.libs.records import LogRecord

LogRecord("Message", level="info", sources=[self.plugin_id])()
```

### Sending Data to Clients

```python
from bastproxy.libs.records import SendDataDirectlyToClient, NetworkData

msg = NetworkData("Message to client")
SendDataDirectlyToClient(msg)()
```

### Modifying Data Flow

```python
@RegisterToEvent(event_name="ev_to_client_data_modify", priority=50)
def _eventcb_modify_data(self):
    event_record = self.api("plugins.core.events:get.current.event.record")()
    data = event_record["data"]

    for line in data:
        if "pattern" in line.noansi:
            line.send = False  # Gag this line
```

## Best Practices

### Plugin Development

1. **Use Appropriate Priorities**: 1-25 for inspection, 26-75 for modification, 76-99 for cleanup
2. **Declare Dependencies**: Explicitly list required plugins
3. **Clean Up Resources**: Implement uninitialize hook
4. **Handle Errors**: Don't crash the proxy
5. **Document APIs**: Provide clear descriptions

### Performance

1. **Minimize Event Callbacks**: Only register for needed events
2. **Use Efficient Algorithms**: Keep callbacks fast
3. **Cache Lookups**: Don't repeatedly call APIs
4. **Batch Operations**: Process multiple items together
5. **Disable Tracking**: Use `track_record=False` for high-frequency records

### Debugging

1. **Use Record Details**: `record.get_formatted_details()`
2. **Check Event Stack**: See which events led to current state
3. **Review Updates**: Examine modification history
4. **Follow Parent Chain**: Trace data origins
5. **Enable Debug Logging**: Set appropriate log levels

## Additional Resources

### Code Locations

- **Event System**: `plugins/core/events/`
- **API System**: `libs/api/`
- **Plugin System**: `libs/plugins/` and `plugins/_baseplugin/`
- **Record System**: `libs/records/`
- **Network Data**: `libs/records/rtypes/networkdata.py`

### Example Plugins

- **plugins/core/commands/**: Command processing
- **plugins/core/settings/**: Settings management
- **plugins/core/timers/**: Timer management
- **plugins/core/triggers/**: Trigger processing
- **plugins/core/proxy/**: Proxy management
- **plugins/core/clients/**: Client management
- **plugins/core/colors/**: Color code handling

## Contributing

When contributing to bastproxy:

1. **Understand the Architecture**: Review all system documentation
2. **Follow Patterns**: Use established patterns and practices
3. **Maintain Compatibility**: Don't break existing plugins
4. **Document Changes**: Update documentation for API changes
5. **Test Thoroughly**: Verify with multiple plugins

## Version Information

This documentation describes the current bastproxy architecture as of the pyproject migration (2024-2025).

For questions or clarifications, refer to:
- The source code in `src/bastproxy/`
- Example plugins in `plugins/`
- This documentation directory
