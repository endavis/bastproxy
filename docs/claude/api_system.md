---
title: API System
description: The central API registry plugins use to publish and call functions
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - api
---

# API System

## Overview

The API system in bastproxy is a centralized registry for exposing and consuming functionality across plugins and modules. It provides a standardized way for components to publish callable functions and for other components to discover and invoke them using a hierarchical naming scheme.

The API system is both class-based and instance-based, allowing for shared functionality (class API) and per-instance overrides (instance API). In practice every plugin API is a class API; the only instance APIs are the 14 `libs.api:` built-ins every `API` object carries.

An audit of this system, with measurements, defects and a patterns review, is in [API System Analysis and Findings](api_system_findings.md).

## Key Components

### API Class
**Location**: `src/bastproxy/libs/api/_api.py`

The `API` class is the core of the API system. It provides:
- **_class_api**: Class-level dictionary storing all shared API functions
- **_instance_api**: Instance-level dictionary for overriding specific APIs. Every `API` object registers 14 built-in `libs.api:` instance APIs here when it is constructed
- **stats**: an unused `ClassVar`. The call statistics are kept by the module-level `STATS_MANAGER` in `_apistats.py` (see API Statistics)
- **BASEPATH** and related paths: File system paths for the proxy
- **startup**, **shutdown**, **quiet_mode**, **LOG_IN_UTC_TZ**, **proxy_start_time**, **command_split_regex**: process-wide flags and settings set from `src/bastproxy/__init__.py` and the proxy plugin
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
**Location**: `src/bastproxy/libs/api/_apiitem.py`

Wraps individual API functions to provide tracking and metadata:

```python
class APIItem:
    def __init__(self, full_api_name: str, tfunction: Callable,
                 owner_id: str | None, description: list | str = ""):
        self.full_api_name = full_api_name
        self.owner_id = owner_id or "unknown"
        self.tfunction = tfunction
        self.instance = False
        self.overwritten_api = None
        # always a list of lines: split from a string, or taken from the
        # comment above the function when no description is given
        self.description = description
```

Key features:
- Wraps the actual function to be called
- Tracks call statistics automatically when invoked (`__call__` finds the caller, records the call, then calls the function)
- Exposes `count` and `stats` for the API's statistics, and `detail()` for owner, description and source
- Supports function overriding with tracking of the overwritten API

### AddAPI Decorator
**Location**: `src/bastproxy/libs/api/_addapi.py`

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

The decorator attaches metadata to functions, which is later processed during plugin initialization. The metadata dict lives on the function object, which is shared by every instance of the class; `addedin` records, per top-level API, the names registered from it. Discovery only finds methods whose name starts with `_api_`, so a decorated method with another name is silently ignored. Names and descriptions may contain `{attribute}` fields, filled from the plugin object's `__dict__`.

### API Statistics
**Location**: `src/bastproxy/libs/api/_apistats.py`

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
- Calls grouped by the part of the caller ID before the first `:` (a plugin ID for plugin-owned callers, a module name such as `bastproxy.libs.net.client` for module-owned ones)
- Detailed call tracking with the full caller ID

The one `STATS_MANAGER` instance is created when `_apistats.py` is imported. Entries are not removed when a plugin is unloaded, and a reloaded plugin keeps counting on the same entry.

## How It Works

### 1. API Naming Convention

APIs follow a hierarchical naming scheme:
```
<top_level_api>:<api_name>
```

Examples:
- `libs.plugins.loader:plugin.instance.get` - Get a plugin instance
- `plugins.core.events:event.raise` - Raise an event
- `plugins.core.commands:output.line.length.get` - Get output line length

The top-level API typically corresponds to the plugin or module that owns the functionality.

The `<api_name>` part follows `<resource>.<action>[.<qualifier>]`, defined in [ADR-0004](../decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md). New names are resource-first:

- `plugins.core.events:event.raise`
- `libs.plugins.loader:plugin.instance.get`

Many names on this page and in the other `docs/claude/` pages are the current names, pending rename by the ADR-0004 follow-up issues. The ADR appendix maps each old name to its new one. `tests/plugins/test_api_name_grammar.py` checks every registered name against the grammar. A new name must conform, and the names that do not conform yet are in its `LEGACY_NAMES`, which rename PRs shrink.

### 2. Registering APIs

#### Using the AddAPI Decorator

The most common way to register APIs is using the `@AddAPI` decorator:

```python
from bastproxy.libs.api import AddAPI

class MyPlugin(BasePlugin):
    @AddAPI("thing.add", description="Add a thing")
    def _api_thing_add(self, arg1: str, arg2: int) -> bool:
        """Perform an action with the given arguments."""
        # Implementation
        return True
```

The decorator marks the function with API metadata. During plugin initialization, the base plugin automatically discovers these decorated functions and registers them.

#### Manual Registration

APIs can also be registered manually:

```python
self.api("libs.api:api.add")(
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
result = self.api("plugins.core.events:event.raise")(
    "ev_my_event",
    event_args={"data": value}
)

# Get the API item (without calling)
api_item = self.api.get("plugins.core.events:event.raise")

# Check if API exists
if self.api("libs.api:api.exists")("some.plugin:some.function"):
    # API exists and its plugin is loaded
    result = self.api("some.plugin:some.function")(args)
```

The `__call__` method is aliased to `get`, so `api("name")` is equivalent to `api.get("name")`. `get` checks the instance APIs first, then the class APIs (`get_class=True` skips the instance APIs). `get` raises `APINotFoundError` (from `bastproxy.libs.exceptions`, a subclass of `APIException` and `AttributeError`) when the API does not exist.

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
- Not used by any plugin today: the only instance APIs are the 14 `libs.api:` built-ins every `API` object registers for itself, which is why `libs.api:*` names are not in `_class_api`. Unloading a plugin that declares `@AddAPI(..., instance=True)` is safe: removal skips the `addedin` bookkeeping that instance APIs never had

When looking up an API, instance APIs take precedence over class APIs.

### 5. API Discovery

Plugins automatically discover API functions during initialization. `BasePlugin` calls the same line from three hooks, in `src/bastproxy/plugins/_baseplugin/_base.py`:

```python
# _phook_base_init_add_apis (__init__ hook, priority 1)
# _phook_base_init (__init__ hook, priority 75)
# _phook_base_post_initialize_setup (initialize hook, priority 91)
self.api("libs.api:api.add.for.object")(self.plugin_id, self)
```

The later calls pick up objects created by hooks that ran in between; a name already recorded in `addedin` is skipped. This process:
1. Scans the plugin object with `dir()`, and one level into each of its attributes, for bound methods whose name starts with `_api_` and that have the `api` attribute (added by `@AddAPI`)
2. Extracts metadata (name, description, instance flag), filling `{attribute}` fields from the object's `__dict__`
3. Registers each API function with the full API name
4. For a module that passes `__name__` as the top-level API (the timing, loader and reloadutils modules), strips a leading `bastproxy.`

### 6. API Removal

When a plugin is unloaded, all its APIs are removed. `_phook_base_unitialize_hook` (the last `uninitialize` hook, priority 100) does it after the unloaded events are raised:

```python
self.api("libs.api:api.toplevel.remove")("my.plugin")
```

This removes all APIs with the top-level name `my.plugin:*`, class and instance, and takes the names out of the shared `addedin` lists so a subclass's APIs can be added again. It removes by top-level name, not by owner, so an API another owner force-overrode in a different top-level is left. It does not remove statistics. A registered function without `@AddAPI` metadata (added by hand with `api.add`) or an instance API has no `addedin` entry to clean, so removal skips that step and still deletes the key.

## Important Files

### Core API System
- `src/bastproxy/libs/api/_api.py` - Main API class
- `src/bastproxy/libs/api/_apiitem.py` - API item wrapper class
- `src/bastproxy/libs/api/_addapi.py` - AddAPI decorator
- `src/bastproxy/libs/api/_apistats.py` - Statistics tracking
- `src/bastproxy/libs/api/_functools.py` - Utility functions for caller detection
- `src/bastproxy/libs/api/__init__.py` - Module exports

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
        if self.api("libs.api:api.exists")("plugins.my.plugin:get.status"):
            status = self.api("plugins.my.plugin:get.status")()

        # Get detailed info about an API
        details = self.api("libs.api:api.detail.get")("plugins.my.plugin:process.data")
```

### Listing APIs

```python
# List all APIs
all_apis = self.api("libs.api:api.list.formatted")()

# List APIs for a specific top-level
plugin_apis = self.api("libs.api:api.list.formatted")("plugins.core.events")

# Get API data as a list of dicts
api_data = self.api("libs.api:data.list")("plugins.core.events")
# Returns: [{"toplevel": "...", "name": "...", "full_api_name": "...", ...}, ...]

# Get children of a top-level API
children = self.api("libs.api:api.list.in.toplevel")("plugins.core.events")
# Returns: ["event.add", "event.raise", "event.current.record.get", ...]
```

### Getting API Details and Statistics

```python
# Get detailed information about an API
details = self.api("libs.api:api.detail.get")(
    "plugins.core.events:event.raise",
    stats_by_plugin=True,        # Include statistics by plugin
    stats_by_caller="plugins.",  # Include stats for callers starting with "plugins."
    show_function_code=True      # Include the function's source code
)

# Get the raw APIItem
api_item = self.api("libs.api:data.get")("plugins.core.events:event.raise")
print(f"Called {api_item.count} times")
print(f"Owner: {api_item.owner_id}")
print(f"Description: {api_item.description}")
```

## Integration Points

### Plugin System
- Plugins get an `api` attribute (an `API(owner_id=<plugin id>)`) from `BasePlugin.__init__`
- All plugins share the same class-level `_class_api` registry
- Each plugin's `API` object can hold instance-specific overrides (none do today)
- APIs are automatically discovered and registered during plugin initialization
- APIs are automatically removed when plugins are unloaded

### Event System
- The API system provides APIs for the event system
- Events are raised via `plugins.core.events:event.raise` API
- Event registration uses `plugins.core.events:event.register` API

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

This walks the call stack, from the caller upward, and takes the first frame whose `self` is not an `APIItem` and has a truthy `owner_id` (or an `api` whose `owner_id` is truthy) that is not in the ignore list. That is usually a plugin ID, but any object with an `owner_id` counts, so a helper such as a `Callback` or a `Timer` is the caller with a compound ID like `plugins.example.myplugin:Timer:name`. If no frame matches, the caller is `unknown`: a warning is logged and a stack dump is logged for every such call.

`libs.api:caller.owner.get` runs the same walk and skips every frame whose `self` is an `API` or `APIItem`, so it returns the real caller without an ignore list (#197). Pass `ignore_owner_list=[<your own ID>]` when your own object also has an `owner_id` or an `api` that would otherwise match first, as plugins and `libs.timing` do.

### API Function Naming Convention

API functions in plugins follow the naming pattern `_api_<name>`:

```python
@AddAPI("thing.get")
def _api_thing_get(self):
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
- `plugins.core.events:event.current.record.get`
- `plugins.core.events:event.stack.get`

This creates a namespace without deep nesting. The segments follow the grammar in [ADR-0004](../decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md).

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
self.api("libs.api:api.add")(
    "my.plugin",
    "function",
    new_function,
    force=True  # Overwrite existing API
)
```

The original API is preserved in `api_item.overwritten_api` for reference; it is not restored when the overriding owner is unloaded. Without `force`, adding a different function under an existing name logs an error and keeps the first one: `api.add` returns `False` for both a class API and an instance API. Adding the same function again is a no-op that returns `True`. Nothing in `src` uses `force` today.

### Character Active Flag

The API system tracks whether the character is active and ready for commands:

```python
# Check if character is active
if self.api("libs.api:character.is.active")():
    # Send commands to the mud
    pass

# Set the character as active
self.api("libs.api:character.active.set")(True)
```

Events are raised when the flag changes:
- `ev_libs.api_character_active`
- `ev_libs.api_character_inactive`

## Common APIs

### Core API Functions
- `libs.api:api.add` - Add a function to the API
- `libs.api:api.exists` - Check if an API exists
- `libs.api:api.toplevel.remove` - Remove a top-level API
- `libs.api:api.detail.get` - Get detailed information about an API
- `libs.api:api.list.formatted` - List all APIs or APIs for a top-level
- `libs.api:data.list` - Get API data as structured dictionaries
- `libs.api:api.list.in.toplevel` - Get child APIs under a top-level
- `libs.api:data.get` - Get the raw APIItem for an API
- `libs.api:api.add.for.object` - Discover and register APIs in an object
- `libs.api:function.owner.get` - Get the plugin ID that owns a function
- `libs.api:caller.owner.get` - Get the owner on top of the frame stack
- `libs.api:character.is.active` / `libs.api:character.active.set` - Read and set the character-active flag
- `libs.api:stack.dump` - Return a stack dump

### Plugin Loader APIs
A selection; `libs.api:api.list.formatted` called with `libs.plugins.loader` lists them all.
- `libs.plugins.loader:plugin.instance.get` - Get a loaded plugin instance
- `libs.plugins.loader:plugin.id.is.valid` - Check if a string is a plugin ID
- `libs.plugins.loader:plugin.is.loaded` - Check if a plugin is loaded
- `libs.plugins.loader:plugin.is.instantiated` - Check if a plugin has an instance
- `libs.plugins.loader:plugin.list` - Get all plugin information
- `libs.plugins.loader:plugin.load` - Load a list of plugins
- `libs.plugins.loader:plugin.unload` - Unload a plugin
- `libs.plugins.loader:plugin.reload` - Reload a plugin

### Event System APIs
- `plugins.core.events:event.add` - Create a new event
- `plugins.core.events:event.raise` - Raise an event
- `plugins.core.events:event.register` - Register a callback to an event
- `plugins.core.events:event.unregister` - Unregister from an event
- `plugins.core.events:event.current.record.get` - Get the current event data
- `plugins.core.events:event.stack.get` - Get the event execution stack
- `plugins.core.events:event.detail.get` - Get details about an event

## Best Practices

### API Design
1. Use clear, descriptive names: `plugin.instance.get` not `get_inst`
2. Group related functions with dot notation: `settings.get`, `settings.set`, `settings.list`
3. Include comprehensive descriptions
4. Document parameters in the function docstring

### API Usage
1. Always check if an API exists before calling (especially for optional plugins):
   ```python
   if self.api("libs.api:api.exists")("optional.plugin:function"):
       result = self.api("optional.plugin:function")()
   ```
2. Use the API for cross-plugin communication instead of direct imports
3. Do not cache API lookups for speed. A lookup is about 0.2 microseconds of a call that takes about 2 (Python 3.12, see the benchmark table in the findings page), and a cached `APIItem` goes stale when the plugin it came from is reloaded
4. A missing API raises `APINotFoundError` (from `bastproxy.libs.exceptions`, which is also an `AttributeError`). Catch `APINotFoundError` rather than `AttributeError`, so an `AttributeError` raised inside the API function itself is not mistaken for a missing API

### Statistics
- API statistics are automatically tracked
- Use them to identify heavily-used APIs
- Monitor unknown callers to identify tracking issues. Each call with an unknown caller costs about 1.3 ms (a stack dump and two log entries), against about 2 microseconds for a known one, so an unknown caller is a defect to fix, not a state to live with
- Statistics persist for the lifetime of the proxy process; unloading a plugin does not clear them
