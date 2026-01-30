# Plugin System

## Overview

The plugin system in bastproxy is a modular architecture that allows functionality to be organized into independent, self-contained packages. Plugins can be dynamically loaded, unloaded, and reloaded at runtime, and they communicate through the API and event systems.

Each plugin is a Python package with a specific structure, metadata, and lifecycle. The system tracks plugin states, dependencies, file changes, and provides comprehensive loading/unloading mechanics.

## Key Components

### BasePlugin Class
**Location**: `plugins/_baseplugin/_base.py`

The base class that all plugins inherit from. Provides core functionality:

```python
class Plugin:
    def __init__(self, plugin_id, plugin_info):
        self.plugin_id = plugin_id  # Unique identifier (e.g., "plugins.core.commands")
        self.plugin_info = plugin_info  # PluginInfo object
        self.api = API(owner_id=self.plugin_id)  # Plugin's API instance
        self.dependencies = []  # List of plugin IDs this plugin depends on
        self.data = {}  # Plugin-specific data storage
```

Key attributes:
- **plugin_id**: Unique identifier (e.g., `plugins.core.events`)
- **plugin_info**: Metadata and runtime information
- **api**: API instance for registering and calling functions
- **dependencies**: List of plugin IDs this plugin depends on
- **can_reload_f**: Whether the plugin can be reloaded
- **can_reset_f**: Whether the plugin can be reset
- **is_reloading_f**: Flag indicating plugin is being reloaded
- **attributes_to_save_on_reload**: List of attributes to preserve during reload

### PluginLoader Class
**Location**: `libs/plugins/loader.py`

Manages the loading, unloading, and tracking of all plugins:

```python
class PluginLoader:
    def __init__(self):
        self.api = API(owner_id=__name__)
        self.plugins_info: dict[str, PluginInfo] = {}
        self.plugin_search_paths: list[dict] = [...]
```

Responsibilities:
- Discovering plugins in search paths
- Loading and instantiating plugins
- Managing plugin lifecycle
- Tracking dependencies
- Handling reload mechanics
- Maintaining weak references to unloaded modules

### PluginInfo Class
**Location**: `libs/plugins/plugininfo.py`

Holds metadata and runtime information for a plugin:

```python
class PluginInfo:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.package = plugin_id.rsplit(".", 1)[0]
        self.short_name = plugin_id.split(".")[-1]
        self.name = ""  # Full plugin name
        self.author = ""
        self.purpose = ""
        self.version = -1
        self.is_required = False
        self.is_plugin = False
        self.is_valid_python_code = True
        self.package_path = Path()
        self.data_directory = Path()
        self.runtime_info = PluginRuntimeInfo()
        self.files = {}  # Track all Python files in the plugin
```

Tracks:
- Plugin metadata (name, author, version, purpose)
- File system paths
- Python file validity
- Changed files since loading
- Runtime state

### PluginRuntimeInfo Class
**Location**: `libs/plugins/plugininfo.py`

Tracks runtime state of a plugin:

```python
class PluginRuntimeInfo:
    def __init__(self):
        self.is_loaded = False  # Plugin is fully loaded
        self.is_imported = False  # Plugin package has been imported
        self.plugin_instance = None  # The plugin instance
        self.imported_time = datetime(1970, 1, 1)  # When it was imported
```

### RegisterPluginHook Decorator
**Location**: `plugins/_baseplugin/_pluginhooks.py`

Decorator for registering functions to plugin lifecycle hooks:

```python
class RegisterPluginHook:
    def __init__(self, hook_name, priority=50):
        self.hook_name = hook_name  # '__init__', 'initialize', 'save', 'uninitialize'
        self.priority = priority
```

## Plugin Structure

### Directory Layout

```
plugins/
└── <category>/           # e.g., 'core', 'client', 'games'
    └── <plugin_name>/    # e.g., 'events', 'commands'
        ├── __init__.py   # Plugin metadata
        ├── plugin/       # Plugin implementation directory
        │   └── __init__.py  # Main plugin class
        ├── libs/         # Plugin-specific libraries (optional)
        │   └── ...
        └── commands/     # Plugin commands (optional)
            └── ...
```

### Plugin Metadata (__init__.py)

Every plugin package must have an `__init__.py` file with metadata:

```python
# plugins/core/myplugin/__init__.py

PLUGIN_NAME = 'My Plugin'
PLUGIN_AUTHOR = 'Your Name'
PLUGIN_VERSION = 1
PLUGIN_PURPOSE = 'Description of what this plugin does'
REQUIRED = False  # Whether this plugin is required to be loaded
```

Metadata fields:
- **PLUGIN_NAME**: Human-readable name
- **PLUGIN_AUTHOR**: Plugin author
- **PLUGIN_VERSION**: Integer version number
- **PLUGIN_PURPOSE**: Brief description
- **REQUIRED**: Boolean indicating if the plugin is required

### Plugin Class (plugin/__init__.py)

The main plugin class in `plugin/__init__.py`:

```python
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.libs.api import AddAPI
from bastproxy.libs.records import LogRecord

class Plugin(BasePlugin):
    def __init__(self, plugin_id, plugin_info):
        super().__init__(plugin_id, plugin_info)

        # Add dependencies
        self.dependencies = ['plugins.core.events']

        # Initialize plugin-specific state
        self.some_data = {}

    @AddAPI("my.function", description="Does something useful")
    def _api_my_function(self, arg):
        """Perform some action."""
        return arg
```

## Plugin Lifecycle

### 1. Discovery

The plugin loader scans configured search paths for plugin packages:

```python
# In PluginLoader
self.plugin_search_paths = [
    {"path": self.base_plugin_dir, "prefix": "plugins.", "strip": ""},
]
```

For each directory found, it creates a `PluginInfo` object and extracts metadata from `__init__.py`.

### 2. Loading

When a plugin is loaded:

1. **Import**: The plugin package is imported
   ```python
   plugin_module = importlib.import_module(plugin_info.package_import_location)
   ```

2. **Class Import**: The Plugin class is imported
   ```python
   plugin_class_module = importlib.import_module(plugin_info.plugin_class_import_location)
   ```

3. **Instantiation**: The plugin is instantiated
   ```python
   plugin_instance = plugin_class_module.Plugin(plugin_id, plugin_info)
   ```

4. **Hook Processing**: `__init__` plugin hooks are executed in priority order

5. **API Registration**: Plugin APIs are automatically discovered and registered

6. **Event Notification**: `ev_plugin_loaded` event is raised

### 3. Initialization

After loading, plugins can have custom initialization:

```python
class Plugin(BasePlugin):
    @RegisterPluginHook("initialize", priority=50)
    def _phook_initialize(self):
        """Custom initialization logic."""
        LogRecord("Initializing my plugin", sources=[self.plugin_id])()
```

The `initialize` hook is called after all plugins are loaded.

### 4. Runtime

During runtime, plugins:
- Expose functionality through APIs
- Listen to and raise events
- Interact with other plugins
- Process data flowing through the proxy
- Execute commands

### 5. Saving State

Plugins can save state when requested:

```python
class Plugin(BasePlugin):
    @RegisterPluginHook("save", priority=50)
    def _phook_save(self):
        """Save plugin state."""
        # Save data to file
        pass
```

The `ev_plugin_save` event triggers the save hook.

### 6. Unloading

When a plugin is unloaded:

1. **Uninitialize Hook**: `uninitialize` plugin hooks are executed
   ```python
   @RegisterPluginHook("uninitialize", priority=50)
   def _phook_uninitialize(self):
       """Cleanup before unload."""
       pass
   ```

2. **API Removal**: All plugin APIs are removed
   ```python
   self.api("libs.api:remove")(plugin_id)
   ```

3. **Event Unregistration**: All event registrations are removed

4. **Event Notification**: `ev_plugin_unloaded` event is raised

5. **Module Cleanup**: Weak references to modules are maintained for garbage collection

### 7. Reloading

Reloading a plugin:

1. **Save Attributes**: Specified attributes are cached
   ```python
   # In plugin
   self.attributes_to_save_on_reload = ['some_state', 'other_data']
   ```

2. **Unload**: Plugin is unloaded (see above)

3. **Module Reload**: Python modules are reloaded
   ```python
   importlib.reload(module)
   ```

4. **Load**: Plugin is loaded again (see above)

5. **Restore Attributes**: Cached attributes are restored from the reload cache

## Plugin Hooks

Plugin hooks allow plugins to register functions to be called at specific lifecycle points.

### Available Hooks

1. **`__init__`**: Called during `Plugin.__init__()`, after base initialization
   - Use for: Early API registration, basic setup
   - Priority order matters

2. **`initialize`**: Called after all plugins are loaded
   - Use for: Setup that requires other plugins to be available
   - Cross-plugin initialization

3. **`save`**: Called when plugin state should be saved
   - Use for: Persisting data to disk
   - Triggered by `ev_plugin_save` event

4. **`uninitialize`**: Called before plugin is unloaded
   - Use for: Cleanup, closing connections, saving state
   - Graceful shutdown

### Using Plugin Hooks

```python
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook

class Plugin(BasePlugin):
    @RegisterPluginHook("__init__", priority=10)
    def _phook_early_init(self):
        """Early initialization."""
        self.early_data = {}

    @RegisterPluginHook("__init__", priority=90)
    def _phook_late_init(self):
        """Late initialization."""
        self.late_data = {}

    @RegisterPluginHook("initialize", priority=50)
    def _phook_initialize(self):
        """Main initialization after all plugins loaded."""
        # Can now safely call APIs from other plugins
        pass

    @RegisterPluginHook("save", priority=50)
    def _phook_save(self):
        """Save plugin state."""
        # Write data to files
        pass

    @RegisterPluginHook("uninitialize", priority=50)
    def _phook_uninitialize(self):
        """Cleanup before unload."""
        # Close connections, clean up resources
        pass
```

### Hook Execution Order

- Hooks are executed in priority order (lower numbers first)
- Multiple hooks at the same priority are executed in the order they're discovered
- Hook functions must start with `_phook_` to be discovered

## Dependencies

### Declaring Dependencies

Plugins declare dependencies in their `__init__` method:

```python
class Plugin(BasePlugin):
    def __init__(self, plugin_id, plugin_info):
        super().__init__(plugin_id, plugin_info)

        # Add explicit dependencies
        self.dependencies = [
            'plugins.core.events',
            'plugins.core.commands',
        ]
```

Or dynamically via API:

```python
self.api(f"{self.plugin_id}:dependency.add")('plugins.core.settings')
```

### Automatic Dependencies

Some dependencies are automatic:
- Plugins in `plugins.core` are automatically available
- Plugins in `plugins.client` are automatically available

### Dependency Resolution

When loading plugins:
1. Dependencies are checked
2. Missing dependencies are loaded first
3. Circular dependencies are detected and reported
4. Load order respects dependency graph

### Reload with Dependents

Plugins can specify whether dependent plugins should be reloaded:

```python
self.reload_dependents_f = True  # Reload plugins that depend on this one
```

## Plugin Data

### Data Storage

Plugins have a built-in `data` dictionary:

```python
class Plugin(BasePlugin):
    def __init__(self, plugin_id, plugin_info):
        super().__init__(plugin_id, plugin_info)
        self.data['users'] = {}
        self.data['settings'] = {}
```

### Data APIs

Access plugin data via APIs:

```python
# Get data
users = self.api("plugins.core.myplugin:data.get")('users')

# Update data
self.api("plugins.core.myplugin:data.update")('users', new_users)

# Get data from another plugin
other_data = self.api(f"{self.plugin_id}:data.get")(
    'some_type',
    plugin_id='plugins.core.otherplugin'
)
```

### Data Directory

Each plugin has a data directory for persistent storage:

```python
# Get the data directory
data_dir = self.api(f"{self.plugin_id}:get.data.directory")()
# Returns: Path to data/<plugin_id>/
```

## Common Plugin Patterns

### Exposing APIs

```python
from bastproxy.libs.api import AddAPI

class Plugin(BasePlugin):
    @AddAPI("process.data", description="Process some data")
    def _api_process_data(self, data):
        """Process the given data.

        Args:
            data: The data to process

        Returns:
            Processed data
        """
        return self.do_processing(data)
```

### Listening to Events

```python
from bastproxy.libs.events import RegisterToEvent

class Plugin(BasePlugin):
    @RegisterToEvent(event_name="ev_to_mud_data_modify", priority=50)
    def _eventcb_handle_mud_data(self):
        """Handle data being sent to mud."""
        event_record = self.api("plugins.core.events:get.current.event.record")()
        # Modify data
        event_record['line'] = "modified: " + event_record['line']
```

### Creating Events

```python
class Plugin(BasePlugin):
    @RegisterPluginHook("__init__", priority=50)
    def _phook_create_events(self):
        """Create plugin-specific events."""
        self.api("plugins.core.events:add.event")(
            "ev_myplugin_something_happened",
            self.plugin_id,
            description=["Event when something happens"],
            arg_descriptions={
                "data": "The data associated with the event"
            }
        )
```

### Logging

```python
from bastproxy.libs.records import LogRecord

class Plugin(BasePlugin):
    def some_method(self):
        LogRecord(
            "Something happened",
            level="info",  # debug, info, warning, error, critical
            sources=[self.plugin_id]
        )()
```

### Plugin Inspection

```python
class Plugin(BasePlugin):
    @AddAPI("dump", description="Dump plugin state")
    def _api_dump(self, attribute_name=None, detailed=False):
        """Dump plugin state or a specific attribute."""
        return super()._api_dump(attribute_name, detailed)
```

## Important Files

### Core Plugin System
- `plugins/_baseplugin/_base.py` - BasePlugin class
- `plugins/_baseplugin/_pluginhooks.py` - RegisterPluginHook decorator
- `plugins/_baseplugin/_commands.py` - Command-related base functionality
- `plugins/_baseplugin/_patch.py` - Plugin patching mechanics
- `plugins/_baseplugin/__init__.py` - Exports BasePlugin

### Plugin Loader
- `libs/plugins/loader.py` - PluginLoader class
- `libs/plugins/plugininfo.py` - PluginInfo and PluginRuntimeInfo classes
- `libs/plugins/dependency.py` - Dependency resolution
- `libs/plugins/imputils.py` - Import utilities
- `libs/plugins/reloadutils.py` - Reload cache utilities

## Common APIs

### Plugin Loader APIs
- `libs.plugins.loader:load.plugins` - Load a list of plugins
- `libs.plugins.loader:unload.plugin` - Unload a plugin
- `libs.plugins.loader:reload.plugin` - Reload a plugin
- `libs.plugins.loader:get.plugin.instance` - Get a plugin instance
- `libs.plugins.loader:get.loaded.plugins.list` - Get loaded plugins
- `libs.plugins.loader:get.all.plugins` - Get all discovered plugins
- `libs.plugins.loader:is.plugin.loaded` - Check if plugin is loaded
- `libs.plugins.loader:is.plugin.instantiated` - Check if plugin has instance
- `libs.plugins.loader:get.plugin.info` - Get PluginInfo for a plugin
- `libs.plugins.loader:does.plugin.exist` - Check if plugin exists
- `libs.plugins.loader:get.not.loaded.plugins` - Get unloaded plugins

### Plugin Instance APIs
- `<plugin_id>:data.get` - Get plugin data
- `<plugin_id>:data.update` - Update plugin data
- `<plugin_id>:dependency.add` - Add a dependency
- `<plugin_id>:get.data.directory` - Get plugin's data directory
- `<plugin_id>:set.reload` - Set reload flag
- `<plugin_id>:get.plugin.hooks` - Get plugin hooks
- `<plugin_id>:dump` - Dump plugin state

## Events

### Plugin Lifecycle Events
- `ev_plugin_loaded` - A plugin was loaded
- `ev_plugin_unloaded` - A plugin was unloaded
- `ev_plugin_save` - Plugins should save their state
- `ev_plugin_reset` - A plugin should reset to defaults
- `ev_baseplugin_patched` - BasePlugin class was reloaded

## Best Practices

### Plugin Design
1. **Single Responsibility**: Each plugin should have a clear, focused purpose
2. **Explicit Dependencies**: Declare all dependencies explicitly
3. **Namespace APIs**: Use descriptive, namespaced API names
4. **Document APIs**: Include docstrings and descriptions
5. **Handle Errors Gracefully**: Don't crash the proxy

### Initialization
1. **Minimal `__init__`**: Keep initialization simple
2. **Use Hooks**: Use appropriate hooks for different initialization stages
3. **Check Dependencies**: Verify required plugins are loaded
4. **Fail Gracefully**: Handle missing dependencies

### Reloading
1. **Save State**: Use `attributes_to_save_on_reload` for important state
2. **Clean Up**: Implement `uninitialize` hook for cleanup
3. **Test Reloads**: Ensure plugin can be reloaded without issues

### Resource Management
1. **Close Resources**: Close files, connections in `uninitialize` hook
2. **Persistent Data**: Use the data directory for files
3. **Memory Awareness**: Clean up large data structures on unload

### API Design
1. **Consistent Naming**: Use clear, consistent API names
2. **Version Compatibility**: Maintain backward compatibility
3. **Error Handling**: Return sensible defaults, log errors
4. **Documentation**: Document all public APIs

### Event Usage
1. **Priority Selection**: Choose appropriate priorities (lower = earlier)
2. **Event Data**: Don't modify event data unless intended
3. **Performance**: Keep event callbacks fast
4. **Error Handling**: Don't let exceptions escape event handlers
