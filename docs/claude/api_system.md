# API System

## Overview

The API system in bastproxy is a centralized registry for exposing and consuming functionality across plugins and modules. It provides a standardized way for components to publish callable functions and for other components to discover and invoke them using a hierarchical naming scheme.

The API system is both class-based and instance-based, allowing for shared functionality (class API) and per-instance overrides (instance API).

## Key Components

### API Class
**Location**: `libs/api/_api.py`

The `API` class is the core of the API system. It provides:
- **_class_api**: Class-level dictionary storing all shared API functions
- **_instance_api**: Instance-level dictionary for overriding specific APIs
- **stats**: Global statistics tracking API usage
- **BASEPATH** and related paths: File system paths for the proxy
- **is_character_active**: Global flag indicating if the character is ready for commands

```python
class API:
    _class_api: ClassVar[dict[str, APIItem]] = {}
    stats: ClassVar[dict[str, APIStatItem]] = {}

    def __init__(self, owner_id: str | None = None):
        self._instance_api: dict[str, APIItem] = {}
        self.owner_id: str = owner_id or "unknown"
```

### APIItem Class
**Location**: `libs/api/_apiitem.py`

Wraps individual API functions to provide tracking and metadata:

```python
class APIItem:
    def __init__(self, full_api_name: str, tfunction: Callable,
                 owner_id: str | None, description: list | str = ""):
        self.full_api_name = full_api_name
        self.owner_id = owner_id
        self.tfunction = tfunction
        self.instance = False
        self.overwritten_api = None
        self.description = description
```

Key features:
- Wraps the actual function to be called
- Tracks call statistics automatically when invoked
- Provides detailed information about the API including owner, description, and source
- Supports function overriding with tracking of the overwritten API

### AddAPI Decorator
**Location**: `libs/api/_addapi.py`

Decorator for marking functions as APIs during class definition:

```python
class AddAPI:
    def __init__(self, api: str, description: str = "", instance: bool = False):
        self.api_name = api
        self.description = description
        self.instance = instance

    def __call__(self, func: Callable) -> Callable:
        func.api = {
            "name": self.api_name,
            "description": self.description,
            "instance": self.instance,
            "addedin": {},
        }
        return func
```

The decorator attaches metadata to functions, which is later processed during plugin initialization.

### API Statistics
**Location**: `libs/api/_apistats.py`

Tracks usage statistics for all API calls:

```python
class APIStatItem:
    def __init__(self, full_api_name: str):
        self.full_api_name = full_api_name
        self.calls_by_caller: dict[str, int] = {}
        self.detailed_calls: dict[str, int] = {}
        self.count = 0

class StatsManager:
    def __init__(self):
        self.stats: dict[str, APIStatItem] = {}
```

Statistics include:
- Total call count per API
- Calls grouped by calling plugin
- Detailed call tracking with full caller information

## How It Works

### 1. API Naming Convention

APIs follow a hierarchical naming scheme:
```
<top_level_api>:<api_name>
```

Examples:
- `libs.plugins.loader:get.plugin.instance` - Get a plugin instance
- `plugins.core.events:raise.event` - Raise an event
- `plugins.core.commands:get.output.line.length` - Get output line length

The top-level API typically corresponds to the plugin or module that owns the functionality.

### 2. Registering APIs

#### Using the AddAPI Decorator

The most common way to register APIs is using the `@AddAPI` decorator:

```python
from bastproxy.libs.api import AddAPI

class MyPlugin(BasePlugin):
    @AddAPI("do.something", description="Does something useful")
    def _api_do_something(self, arg1: str, arg2: int) -> bool:
        """Perform an action with the given arguments."""
        # Implementation
        return True
```

The decorator marks the function with API metadata. During plugin initialization, the base plugin automatically discovers these decorated functions and registers them.

#### Manual Registration

APIs can also be registered manually:

```python
self.api("libs.api:add")(
    "my.plugin",           # top-level API
    "function.name",       # API name
    my_function,           # callable
    description="Description of the API",
    instance=False         # False for class API, True for instance API
)
```

Full API name becomes: `my.plugin:function.name`

### 3. Calling APIs

The API class is callable, allowing natural function-like syntax:

```python
# Basic call
result = self.api("plugins.core.events:raise.event")(
    "ev_my_event",
    event_args={"data": value}
)

# Get the API item (without calling)
api_item = self.api.get("plugins.core.events:raise.event")

# Check if API exists
if self.api("libs.api:has")("some.plugin:some.function"):
    # API exists and its plugin is loaded
    result = self.api("some.plugin:some.function")(args)
```

The `__call__` method is aliased to `get`, so `api("name")` is equivalent to `api.get("name")`.

### 4. Class vs Instance APIs

**Class APIs** (instance=False):
- Stored in `_class_api`
- Shared across all API instances
- Used for most plugin functionality
- Default mode

**Instance APIs** (instance=True):
- Stored in `_instance_api`
- Specific to one API instance
- Can override class APIs
- Used for per-instance customization

When looking up an API, instance APIs take precedence over class APIs.

### 5. API Discovery

Plugins automatically discover API functions during initialization:

```python
# In BasePlugin.__initialize__()
self.api("libs.api:add.apis.for.object")(self.plugin_id, self)
```

This process:
1. Scans the plugin object for methods with the `api` attribute (added by `@AddAPI`)
2. Extracts metadata (name, description, instance flag)
3. Registers each API function with the full API name

### 6. API Removal

When a plugin is unloaded, all its APIs are removed:

```python
self.api("libs.api:remove")("my.plugin")
```

This removes all APIs with the top-level name `my.plugin:*`.

## Important Files

### Core API System
- `libs/api/_api.py` - Main API class
- `libs/api/_apiitem.py` - API item wrapper class
- `libs/api/_addapi.py` - AddAPI decorator
- `libs/api/_apistats.py` - Statistics tracking
- `libs/api/_functools.py` - Utility functions for caller detection
- `libs/api/__init__.py` - Module exports

## Code Examples

### Creating an API

```python
from bastproxy.libs.api import AddAPI
from bastproxy.plugins._baseplugin import BasePlugin

class MyPlugin(BasePlugin):
    @AddAPI("process.data", description="Process some data and return result")
    def _api_process_data(self, data: dict) -> dict:
        """Process the given data.

        Args:
            data: The data to process

        Returns:
            The processed data
        """
        # Process data
        result = {"processed": True, "data": data}
        return result

    @AddAPI("get.status", description="Get the current status", instance=True)
    def _api_get_status(self) -> str:
        """Get the current status of the plugin."""
        return self.status
```

### Calling APIs

```python
# From within a plugin
class AnotherPlugin(BasePlugin):
    def some_method(self):
        # Call another plugin's API
        result = self.api("plugins.my.plugin:process.data")(
            {"key": "value"}
        )

        # Check if API exists before calling
        if self.api("libs.api:has")("plugins.my.plugin:get.status"):
            status = self.api("plugins.my.plugin:get.status")()

        # Get detailed info about an API
        details = self.api("libs.api:detail")("plugins.my.plugin:process.data")
```

### Listing APIs

```python
# List all APIs
all_apis = self.api("libs.api:list")()

# List APIs for a specific top-level
plugin_apis = self.api("libs.api:list")("plugins.core.events")

# Get API data as a list of dicts
api_data = self.api("libs.api:list.data")("plugins.core.events")
# Returns: [{"toplevel": "...", "name": "...", "full_api_name": "...", ...}, ...]

# Get children of a top-level API
children = self.api("libs.api:get.children")("plugins.core.events")
# Returns: ["add.event", "raise.event", "get.current.event.record", ...]
```

### Getting API Details and Statistics

```python
# Get detailed information about an API
details = self.api("libs.api:detail")(
    "plugins.core.events:raise.event",
    stats_by_plugin=True,        # Include statistics by plugin
    stats_by_caller="plugins.",  # Include stats for callers starting with "plugins."
    show_function_code=True      # Include the function's source code
)

# Get the raw APIItem
api_item = self.api("libs.api:data.get")("plugins.core.events:raise.event")
print(f"Called {api_item.count} times")
print(f"Owner: {api_item.owner_id}")
print(f"Description: {api_item.description}")
```

## Integration Points

### Plugin System
- Plugins inherit the `api` property from `BasePlugin`
- All plugins share the same class-level `_class_api` registry
- Each plugin instance can have instance-specific overrides
- APIs are automatically discovered and registered during plugin initialization
- APIs are automatically removed when plugins are unloaded

### Event System
- The API system provides APIs for the event system
- Events are raised via `plugins.core.events:raise.event` API
- Event registration uses `plugins.core.events:register.to.event` API

### Command System
- Commands use APIs to access plugin functionality
- Command handlers typically call plugin APIs to execute functionality

### Module Integration
- Modules (like the plugin loader) can also expose APIs
- Module APIs use the pattern `libs.<module>:<function>`

## Unique Patterns

### Automatic Caller Detection

The API system automatically detects who is calling an API:

```python
# In APIItem.__call__
caller_id = get_caller_owner_id()
STATS_MANAGER.add_call(self.full_api_name, caller_id)
```

This walks the call stack to find the owner ID (typically a plugin ID), enabling detailed usage tracking.

### API Function Naming Convention

API functions in plugins follow the naming pattern `_api_<name>`:

```python
@AddAPI("my.function")
def _api_my_function(self):
    pass
```

The `_api_` prefix:
- Indicates the function is part of the public API
- Distinguishes API functions from internal methods
- Allows automatic discovery during plugin initialization

### Hierarchical API Names

The colon (`:`) separator creates a two-level hierarchy:
- **Top level** (`libs.api`): Identifies the owning plugin or module
- **API name** (`add`): Identifies the specific function

Periods (`.`) in the API name create a logical grouping:
- `plugins.core.events:get.current.event.record`
- `plugins.core.events:get.event.stack`

This creates a namespace without deep nesting.

### Template-Based API Names

API names can include templates that are filled in during registration:

```python
@AddAPI("{plugin_id}.custom", description="Custom API for {plugin_id}")
def _api_custom(self):
    pass
```

The `{plugin_id}` is replaced with the actual plugin ID during registration.

### API Overwriting

APIs can be overwritten with the `force` parameter:

```python
self.api("libs.api:add")(
    "my.plugin",
    "function",
    new_function,
    force=True  # Overwrite existing API
)
```

The original API is preserved in `api_item.overwritten_api` for reference.

### Character Active Flag

The API system tracks whether the character is active and ready for commands:

```python
# Check if character is active
if self.api("libs.api:is.character.active")():
    # Send commands to the mud
    pass

# Set the character as active
self.api("libs.api:is.character.active:set")(True)
```

Events are raised when the flag changes:
- `ev_libs.api_character_active`
- `ev_libs.api_character_inactive`

## Common APIs

### Core API Functions
- `libs.api:add` - Add a function to the API
- `libs.api:has` - Check if an API exists
- `libs.api:remove` - Remove a top-level API
- `libs.api:detail` - Get detailed information about an API
- `libs.api:list` - List all APIs or APIs for a top-level
- `libs.api:list.data` - Get API data as structured dictionaries
- `libs.api:get.children` - Get child APIs under a top-level
- `libs.api:data.get` - Get the raw APIItem for an API
- `libs.api:add.apis.for.object` - Discover and register APIs in an object

### Plugin Loader APIs
- `libs.plugins.loader:get.plugin.instance` - Get a loaded plugin instance
- `libs.plugins.loader:is.plugin.id` - Check if a string is a plugin ID
- `libs.plugins.loader:is.plugin.loaded` - Check if a plugin is loaded
- `libs.plugins.loader:is.plugin.instantiated` - Check if a plugin has an instance
- `libs.plugins.loader:get.all.plugins` - Get all plugin information
- `libs.plugins.loader:load.plugins` - Load a list of plugins
- `libs.plugins.loader:unload.plugin` - Unload a plugin
- `libs.plugins.loader:reload.plugin` - Reload a plugin

### Event System APIs
- `plugins.core.events:add.event` - Create a new event
- `plugins.core.events:raise.event` - Raise an event
- `plugins.core.events:register.to.event` - Register a callback to an event
- `plugins.core.events:unregister.from.event` - Unregister from an event
- `plugins.core.events:get.current.event.record` - Get the current event data
- `plugins.core.events:get.event.stack` - Get the event execution stack
- `plugins.core.events:get.event.detail` - Get details about an event

## Best Practices

### API Design
1. Use clear, descriptive names: `get.plugin.instance` not `get_inst`
2. Group related functions with dot notation: `settings.get`, `settings.set`, `settings.list`
3. Include comprehensive descriptions
4. Document parameters in the function docstring

### API Usage
1. Always check if an API exists before calling (especially for optional plugins):
   ```python
   if self.api("libs.api:has")("optional.plugin:function"):
       result = self.api("optional.plugin:function")()
   ```
2. Use the API for cross-plugin communication instead of direct imports
3. Cache frequently-used API lookups if performance is critical
4. Handle potential AttributeError exceptions when calling APIs

### Statistics
- API statistics are automatically tracked
- Use them to identify heavily-used APIs
- Monitor unknown callers to identify tracking issues
- Statistics persist for the lifetime of the proxy process
