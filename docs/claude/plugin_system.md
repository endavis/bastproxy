---
title: Plugin System
description: Plugin structure, metadata, loading, reloading and lifecycle
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - plugins
---

# Plugin System

## Overview

The plugin system in bastproxy is a modular architecture that allows functionality to be organized into independent, self-contained packages. Plugins can be dynamically loaded, unloaded, and reloaded at runtime, and they communicate through the API and event systems.

Each plugin is a Python package with a specific structure, metadata, and lifecycle. The system tracks plugin states, dependencies, file changes, and provides comprehensive loading/unloading mechanics.

Known defects and design notes are in [Plugin System Findings](plugin_system_findings.md).

## Key Components

### BasePlugin Class
**Location**: `src/bastproxy/plugins/_baseplugin/_base.py`

The base class that all plugins inherit from. Provides core functionality:

```python
class Plugin:
    def __init__(self, plugin_id, plugin_info):
        self.plugin_id = plugin_id  # Unique identifier (e.g., "plugins.core.commands")
        self.plugin_info = plugin_info  # PluginInfo object
        self.api = API(owner_id=self.plugin_id)  # Plugin's API instance
        self.data = {}  # Plugin-specific data storage
```

Key attributes:
- **plugin_id**: Unique identifier (e.g., `plugins.core.events`)
- **plugin_info**: Metadata and runtime information
- **api**: API instance for registering and calling functions
- **can_reload_f**: Whether the plugin can be unloaded or reloaded (checked by `plugin.unload`; a required plugin is also refused, see `PLUGIN_REQUIRED`)
- **can_reset_f**: Whether the plugin can be reset
- **reload_dependents_f**: Whether reloading the plugin also reloads the plugins that depend on it
- **is_reloading_f**: Set by the `<plugin_id>:plugin.reloading.set` API (the `reload` command calls it); only then are `attributes_to_save_on_reload` cached
- **attributes_to_save_on_reload**: List of attributes to preserve during reload (see [Reloading](#7-reloading))

### PluginLoader Class
**Location**: `src/bastproxy/libs/plugins/loader.py`

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
- Resolving declared dependencies and ordering loads
- Handling reload mechanics
- Maintaining weak references to unloaded modules

### PluginInfo Class
**Location**: `src/bastproxy/libs/plugins/plugininfo.py`

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
        self.dependencies: list[str] = []  # from PLUGIN_DEPENDENCIES
        self.is_required = False
        self.is_plugin = False
        self.is_valid_python_code = True
        self.package_path = Path()
        self.package_import_location = ""  # e.g. "bastproxy.plugins.core.events"
        self.data_directory = Path()
        self.runtime_info = PluginRuntimeInfo()
        self.import_errors = []
        self.files = {}  # Track all Python files in the plugin
```

The plugin class is imported from `plugin_class_import_location`, which is
`package_import_location + ".plugin"`.

Tracks:
- Plugin metadata (name, author, version, purpose, dependencies)
- File system paths
- Python file validity
- Changed files since loading
- Runtime state

### PluginRuntimeInfo Class
**Location**: `src/bastproxy/libs/plugins/plugininfo.py`

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
**Location**: `src/bastproxy/plugins/_baseplugin/libs/_pluginhooks.py`

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
PLUGIN_REQUIRED = False
PLUGIN_DEPENDENCIES = ['plugins.core.events']  # optional, see Dependencies
```

Metadata fields:
- **PLUGIN_NAME**: Human-readable name
- **PLUGIN_AUTHOR**: Plugin author
- **PLUGIN_VERSION**: Integer version number
- **PLUGIN_PURPOSE**: Brief description
- **PLUGIN_REQUIRED**: `True` marks the plugin as required, and all `plugins.core` plugins count
  as required. `plugin.unload` and the `unload` command refuse a required plugin. Reload is still
  allowed, subject to `can_reload_f`. Use `can_reload_f = False` to block reload as well.
- **PLUGIN_DEPENDENCIES**: Optional list of plugin IDs that must be loaded first (see [Dependencies](#dependencies))

The name, author, purpose, version and required lines are read with one regular expression per
line, so each must be a single line with nothing after the value. A trailing comment on
`PLUGIN_VERSION` raises an error during discovery, and on the others hides the value. Put
comments on their own line. See [Plugin System Findings](plugin_system_findings.md#ps-5-one-badly-formatted-metadata-line-aborts-discovery).

### Plugin Class (plugin/__init__.py)

The main plugin class in the plugin package's `plugin/` subpackage (`<plugin>/plugin/__init__.py`):

```python
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.libs.api import AddAPI
from bastproxy.libs.records import LogRecord

class Plugin(BasePlugin):
    def __init__(self, plugin_id, plugin_info):
        super().__init__(plugin_id, plugin_info)

        # Initialize plugin-specific state
        self.some_data = {}

    @AddAPI("my.function", description="Does something useful")
    def _api_my_function(self, arg):
        """Perform some action."""
        return arg
```

Attributes listed in `attributes_to_save_on_reload` are restored by the plugin loader right
after the plugin is constructed (`BasePlugin.restore_reload_cache`, called from
`_instantiate_single_plugin` before `initialize`). The restored value therefore replaces any
default, whether it is set in the subclass `__init__` after `super().__init__()` or in an
`__init__` plugin hook of any priority. The bundled plugins use a hook:

```python
class Plugin(BasePlugin):
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        self.attributes_to_save_on_reload = ["clients"]
        self.clients = {}
```

## User Plugins

User plugins load from `$BASTPROXY_HOME/plugins` (created at startup). This is
separate from `$BASTPROXY_HOME/data/plugins`, where plugin data lives.

Layout, two levels deep like every bundled plugin:

```text
$BASTPROXY_HOME/plugins/
    mine/                  # package
        __init__.py        # optional PACKAGE_DESCRIPTION
        myplugin/          # plugin (PLUGIN_NAME in __init__.py, plugin/ subpackage)
```

- **Import root vs ID:** the folder is registered as the import root
  `userplugins`, so the plugin imports as `userplugins.mine.myplugin`. Its plugin
  ID is `plugins.mine.myplugin`, the same namespace as bundled plugins, so
  commands address it as `mine.myplugin` and its data lives in
  `data/plugins/plugins.mine.myplugin`.
- **Bundled names win:** a user plugin in a package named like a bundled one
  (`core`, `debug`, `test`, ...) is skipped with an error log and the bundled
  plugin is kept. Avoid package names ending in `plugins`; the command display
  name strips `plugins.` from the whole string.
- **Imports:** plugins import framework code from `bastproxy`, for example
  `from bastproxy.plugins._baseplugin import BasePlugin`. The top-level
  `plugins` import package no longer exists.

See [ADR-0002](../decisions/0002-user-plugins-load-from-bastproxy-homeplugins-under-the-userplugins-import-root.md).

## Plugin Lifecycle

### 1. Discovery

The plugin loader scans two search paths, bundled plugins first:

```python
# In PluginLoader
self.plugin_search_paths = [
    {"path": <src/bastproxy/plugins>, "import_prefix": "bastproxy.plugins.",
     "id_prefix": "plugins.", "source": "bundled"},
    {"path": self.base_plugin_dir, "import_prefix": "userplugins.",
     "id_prefix": "plugins.", "source": "user"},
]
```

The plugin ID is `id_prefix + import_name.removeprefix(import_prefix)`, so
`bastproxy.plugins.core.x` and `userplugins.mine.x` get the IDs `plugins.core.x`
and `plugins.mine.x`. See [User Plugins](#user-plugins).

For each directory found, it creates a `PluginInfo` object and extracts metadata from `__init__.py`.

### 2. Loading

`libs.plugins.loader:plugin.load` loads a list of plugins in three passes over the whole list
(after ordering it so dependencies come first, see [Dependencies](#dependencies)):

1. **Import** (each plugin): the plugin class module is imported once
   ```python
   return_info = imputils.importmodule(plugin_info.plugin_class_import_location)
   ```
   `importmodule` returns the module if it is already in `sys.modules`. Importing the `.plugin`
   module imports the package first.

2. **Instantiation** (each plugin): the plugin is instantiated
   ```python
   plugin_module = sys.modules[plugin_info.plugin_class_import_location]
   plugin_instance = plugin_module.Plugin(plugin_id, plugin_info)
   ```
   The `__init__` plugin hooks run inside the base `__init__`, in priority order. The base
   class registers the plugin's APIs there.

3. **Initialization** (each plugin, dependencies first): `initialize()` runs the `initialize`
   hooks. Its last base hook (priority 91) flags the plugin loaded, adds the
   `ev_<plugin_id>_loaded` and `ev_<plugin_id>_unloaded` events and, unless the proxy is
   starting up, raises `ev_<plugin_id>_loaded` and `ev_plugin_loaded`.

A plugin that fails any pass is reported in `bad_plugins`, and so is everything that depends
on it. A failed load runs the same subsystem cleanup as an unload: the loader raises
`ev_plugin_unloaded` and removes the plugin's APIs (see the
[findings](plugin_system_findings.md#ps-1-a-failed-load-leaves-registrations-behind)).

### 3. Initialization

Plugins add their own initialization with an `initialize` hook:

```python
class Plugin(BasePlugin):
    @RegisterPluginHook("initialize", priority=50)
    def _phook_initialize(self):
        """Custom initialization logic."""
        LogRecord("Initializing my plugin", sources=[self.plugin_id])()
```

`initialize` runs after every plugin in the same `plugin.load` call has been imported and
instantiated, and after the plugin's declared dependencies have been initialized. Other plugins
in the batch that are not dependencies may not be initialized yet.

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

The `plugin.state.save` API (`<plugin_id>:plugin.state.save`, also the `save` command) runs the `save` hooks,
then raises `ev_<plugin_id>_save` and `ev_plugin_save`. Unloading calls it. It saves one plugin; the
pluginm API `plugin.state.save.all` (`plugins.core.pluginm:plugin.state.save.all`) saves every loaded plugin
by calling `plugin.state.save` on each.

### 6. Unloading

`libs.plugins.loader:plugin.unload` refuses a loaded plugin when `can_reload_f` is false (a plugin that failed to load is always cleaned up), or when the plugin is required and `allow_required` is not passed (reload and failed-load cleanup pass it). Otherwise:

1. **Uninitialize Hooks**: `uninitialize` plugin hooks run in priority order, but only if the
   plugin is flagged loaded. A plugin that failed to load is not uninitialized, but the loader
   raises `ev_plugin_unloaded` and calls `libs.api:api.toplevel.remove` for it, so the events, commands,
   settings, timers, triggers, watch and mudcmds cleanup handlers run.
   ```python
   @RegisterPluginHook("uninitialize", priority=50)
   def _phook_uninitialize(self):
       """Cleanup before unload."""
       pass
   ```

2. **Base uninitialize hook** (priority 100, always last):
   - calls `plugin.state.save`
   - caches `attributes_to_save_on_reload` if `is_reloading_f` is set
   - raises `ev_<plugin_id>_unloaded` and `ev_plugin_unloaded`
   - removes the plugin's APIs with `libs.api:api.toplevel.remove`

3. **`ev_plugin_unloaded` handlers** do the per-subsystem cleanup, each for the plugin ID in
   the event: the events plugin removes the plugin's event registrations, the commands plugin
   its command data, the settings plugin its settings (after saving), and the timers,
   triggers, watch and mudcmds plugins theirs. Event *definitions* the plugin added with
   `event.add` are not removed.

4. **Loader bookkeeping**: the plugin is removed from the `pluginstoload` setting, the
   instance is deleted, every module under the plugin package is deleted from `sys.modules`
   unless it sets `CANRELOAD = False`, a weak reference to each deleted module is kept (see
   `plugin.module.list.stale`) and the runtime info is reset.

### 7. Reloading

`libs.plugins.loader:plugin.reload`:

1. **Check**: if the plugin sets `reload_dependents_f`, every loaded plugin that depends on it (directly or transitively) is reloaded too. Nothing is unloaded unless all of them have `can_reload_f` set.

2. **Unload**: dependents furthest first, then the plugin (see above). The `reload` command calls `<plugin_id>:plugin.reloading.set` first, which sets `is_reloading_f`; the attributes named in `attributes_to_save_on_reload` are only cached in that case.
   ```python
   # In the plugin's __init__ or an __init__ plugin hook
   self.attributes_to_save_on_reload = ['some_state', 'other_data']
   ```

3. **Load**: one `plugin.load` call loads them all again with dependencies first. The modules
   were deleted from `sys.modules` on unload, so the edited code is imported fresh;
   `importlib.reload` is not used.

4. **Restore Attributes**: right after constructing the new instance, the loader calls
   `restore_reload_cache`, which sets the cached attributes on it and clears the cache. A failure
   there is handled like an instantiation failure.

Entries in `pluginstoload` are put back after the reload. `plugin.reload` returns `True` only if
everything unloaded and loaded again.

### Base class mixins

`BasePlugin` is `class BasePlugin(Plugin, Commands, Settings)`. The `Commands` mixin
(`src/bastproxy/plugins/_baseplugin/libs/_commands.py`) adds the `help`, `reset` and `save` commands, and the `Settings` mixin
(`src/bastproxy/plugins/_baseplugin/libs/_settings.py`) adds the `set` command and the settings `initialize` hook. Every
plugin inherits them, so they are present before any plugin initializes and survive reloads.

A `_patch_base.py` in a plugin package is no longer applied: the loader ignores it, and
`bastproxy.plugins._baseplugin.patch` no longer exists. To add behavior to every plugin, add a mixin
to `BasePlugin`; to add it to one plugin, put it on that plugin's class.

## Plugin Hooks

Plugin hooks allow plugins to register functions to be called at specific lifecycle points.

### Available Hooks

1. **`__init__`**: Called at the end of the base `Plugin.__init__()`; the base class's own `__init__` hooks (priority 1 and 75) are among them; reload attributes are restored afterwards, by the loader
   - Use for: Defaults, `attributes_to_save_on_reload`, creating objects that have APIs
   - Priority order matters

2. **`initialize`**: Called by the loader once the plugin and every plugin in the same load call has been instantiated, dependencies first
   - Use for: Setup that requires other plugins to be available
   - Cross-plugin initialization

3. **`save`**: Called by the `plugin.state.save` API
   - Use for: Persisting data to disk
   - `plugin.state.save` then raises `ev_<plugin_id>_save` and `ev_plugin_save`

4. **`uninitialize`**: Called before plugin is unloaded
   - Use for: Cleanup, closing connections, saving state
   - Graceful shutdown

The hook name is not validated: a misspelled name registers and never runs.

### Base Class Hooks

The base class registers these, which sets the order a plugin's own hooks run against:

| Hook | Priority | Method | Purpose |
| :--- | ---: | :--- | :--- |
| `__init__` | 1 | `_phook_base_init_add_apis` | Add the plugin's APIs |
| `__init__` | 75 | `_phook_base_init` | Add APIs again |
| `initialize` | 1 | `_phook_base_initialize` | `_version` setting, disconnect callback, `ev_<id>_savestate` |
| `initialize` | 50 | `_phook_base_post_initialize_add_reset_command` | Enable the `reset` command |
| `initialize` | 75 | `_phook_settings_post_initialize` (`Settings` mixin) | Initialize the plugin's settings |
| `initialize` | 90 | `_phook_base_post_initialize_update_version` | Run `version_functions` after a version bump |
| `initialize` | 91 | `_phook_base_post_initialize_setup` | Add APIs, flag the plugin loaded, raise the loaded events |
| `uninitialize` | 100 | `_phook_base_unitialize_hook` | Save, cache reload attributes, raise the unloaded events, remove APIs |

The default priority is 50. A plugin must call `plugins.core.settings:setting.add` before priority 75
and its `uninitialize` hooks run before the base hook at 100.

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
- Multiple hooks at the same priority are executed in alphabetical order of the method name
- Hook functions must start with `_phook_` to run
- A hook that raises in `__init__` fails the load; in `initialize` the loader unloads the plugin
  (clearing its loaded flag first, so it is cleaned up rather than uninitialized); in
  `uninitialize` the unload stops and returns `False`. A failed `__init__` or `initialize`
  still has its registrations removed
- `<plugin_id>:plugin.hook.list` lists the same hooks, in the same order, that the plugin runs,
  including hooks that share a priority (fixed for
  [PS-6](plugin_system_findings.md#ps-6-pluginhooklist-drops-hooks-that-share-a-priority))

## Dependencies

### Declaring Dependencies

Plugins declare dependencies as metadata in the package `__init__.py`, next to `PLUGIN_NAME`:

```python
# plugins/core/myplugin/__init__.py
PLUGIN_DEPENDENCIES = ["plugins.core.ssc"]
```

The value must be a list or tuple of full plugin IDs. The loader reads it with `ast.literal_eval` before importing the plugin, so no plugin code runs; the result is stored on `PluginInfo.dependencies`. An invalid value gives no dependencies and an entry in `import_errors`. Duplicates and self-references are dropped.

There is no runtime API for adding dependencies: the loader needs them before it instantiates the plugin.

### Dependency Resolution

When loading plugins (`libs.plugins.loader:plugin.load`):
1. Each requested plugin's `PLUGIN_DEPENDENCIES` is read.
2. Dependencies that are not loaded are pulled into the load, and the plugins are ordered so dependencies come first. Otherwise the requested order is kept.
3. Import, instantiate and initialize each run in that order, so a dependency's `initialize()` runs before its dependent's.
4. A missing, circular or failing dependency fails the dependent with a logged error. Unrelated plugins still load. With `exit_on_error` set (startup) any failure exits.

Unloading a plugin that others depend on is not blocked.

### Reload with Dependents

Plugins can specify whether dependent plugins should be reloaded:

```python
self.reload_dependents_f = True  # Reload plugins that depend on this one
```

See [Reloading](#7-reloading). `libs.plugins.loader:plugin.reload` returns `True` only when everything unloaded and loaded again.

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
data_dir = self.api(f"{self.plugin_id}:data.directory.get")()
# Returns: Path to $BASTPROXY_HOME/data/plugins/<plugin_id>
```

### Renamed plugins

The data directory is keyed by plugin ID, so renaming a plugin leaves its old directory behind
and the plugin starts fresh. `plugins.core.cmdq` became `plugins.core.mudcmds` in #172
([ADR-0004](../decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md)).
To keep the data, stop the proxy and run:

```bash
mv "$BASTPROXY_HOME/data/plugins/plugins.core.cmdq" "$BASTPROXY_HOME/data/plugins/plugins.core.mudcmds"
```

The directory only holds `settingvalues.txt` with the hidden `_version` setting, so skipping the
move loses nothing. The `fixqueue` command and the `ev_plugins.core.cmdq_*` events now live under
`plugins.core.mudcmds` (`ev_plugins.core.mudcmds_*`).

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
from bastproxy.plugins.core.events import RegisterToEvent

class Plugin(BasePlugin):
    @RegisterToEvent(event_name="ev_to_mud_data_modify", priority=50)
    def _eventcb_handle_mud_data(self):
        """Handle data being sent to mud."""
        event_record = self.api("plugins.core.events:event.current.record.get")()
        # Modify data
        event_record['line'] = "modified: " + event_record['line']
```

### Creating Events

```python
class Plugin(BasePlugin):
    @RegisterPluginHook("__init__", priority=50)
    def _phook_create_events(self):
        """Create plugin-specific events."""
        self.api("plugins.core.events:event.add")(
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
    @AddAPI("plugin.dump", description="Dump plugin state")
    def _api_plugin_dump(self, attribute_name=None, detailed=False):
        """Dump plugin state or a specific attribute."""
        return super()._api_plugin_dump(attribute_name, detailed)
```

## Important Files

### Core Plugin System
- `src/bastproxy/plugins/_baseplugin/_base.py` - BasePlugin class
- `src/bastproxy/plugins/_baseplugin/libs/_pluginhooks.py` - RegisterPluginHook decorator
- `src/bastproxy/plugins/_baseplugin/libs/_commands.py` - Command-related base functionality
- `src/bastproxy/plugins/_baseplugin/libs/_settings.py` - The `set` command and the settings `initialize` hook
- `src/bastproxy/plugins/_baseplugin/__init__.py` - Exports `BasePlugin` and `RegisterPluginHook`

### Plugin Loader
- `src/bastproxy/libs/plugins/loader.py` - PluginLoader class
- `src/bastproxy/libs/plugins/plugininfo.py` - PluginInfo and PluginRuntimeInfo classes
- `src/bastproxy/libs/plugins/dependency.py` - Dependency resolution
- `src/bastproxy/libs/plugins/imputils.py` - Import utilities
- `src/bastproxy/libs/plugins/reloadutils.py` - Reload cache utilities

## Common APIs

### Plugin Loader APIs
- `libs.plugins.loader:plugin.load` - Load a list of plugins
- `libs.plugins.loader:plugin.unload` - Unload a plugin
- `libs.plugins.loader:plugin.reload` - Reload a plugin
- `libs.plugins.loader:plugin.instance.get` - Get a plugin instance
- `libs.plugins.loader:plugin.list.loaded` - Get loaded plugins
- `libs.plugins.loader:plugin.list` - Get all discovered plugins
- `libs.plugins.loader:plugin.is.loaded` - Check if plugin is loaded
- `libs.plugins.loader:plugin.is.instantiated` - Check if plugin has instance
- `libs.plugins.loader:plugin.info.get` - Get PluginInfo for a plugin
- `libs.plugins.loader:plugin.exists` - Check if plugin exists
- `libs.plugins.loader:plugin.id.is.valid` - Check if a string is a plugin ID
- `libs.plugins.loader:plugin.list.not.loaded` - Get unloaded plugins
- `libs.plugins.loader:package.list` - Get the plugin packages
- `libs.plugins.loader:plugin.list.in.package` - Get the loaded plugins in a package
- `libs.plugins.loader:plugin.id.match` - Find a plugin ID from a partial string
- `libs.plugins.loader:plugin.file.list.changed` - Files changed since the plugin loaded
- `libs.plugins.loader:plugin.file.list.invalid` - Files with invalid Python syntax
- `libs.plugins.loader:plugin.module.list.stale` - Modules kept by weak reference after unload
- `libs.plugins.loader:plugin.loaded.set` - Flag a plugin loaded (called by the base class)
- `libs.plugins.reloadutils:cache.add`, `cache.get`, `cache.remove` - The reload cache

### Plugin Instance APIs
- `<plugin_id>:data.get` - Get plugin data
- `<plugin_id>:data.update` - Update plugin data
- `<plugin_id>:data.directory.get` - Get plugin's data directory
- `<plugin_id>:plugin.reloading.set` - Set the `is_reloading_f` flag so reload attributes are cached
- `<plugin_id>:plugin.hook.list` - Get plugin hooks
- `<plugin_id>:plugin.state.save` - Run the `save` hooks and raise the save events
- `<plugin_id>:plugin.reset` - Raise `ev_plugin_reset`
- `<plugin_id>:plugin.dump` - Dump plugin state

## Events

### Plugin Lifecycle Events
- `ev_plugin_loaded` - A plugin was loaded (raised at the end of `initialize`, not at startup)
- `ev_plugin_unloaded` - A plugin was unloaded (subsystems remove the plugin's data on this)
- `ev_plugin_save` - Plugins should save their state
- `ev_plugin_reset` - A plugin should reset to defaults
- `ev_<plugin_id>_loaded`, `ev_<plugin_id>_unloaded`, `ev_<plugin_id>_save`, `ev_<plugin_id>_savestate` - Per-plugin versions
- `ev_bastproxy.libs.plugins.loader_post_startup_plugins_loaded` - Raised once after the startup load

## Best Practices

### Plugin Design
1. **Single Responsibility**: Each plugin should have a clear, focused purpose
2. **Explicit Dependencies**: Declare all dependencies in `PLUGIN_DEPENDENCIES`
3. **Namespace APIs**: Use descriptive, namespaced API names
4. **Document APIs**: Include docstrings and descriptions
5. **Handle Errors Gracefully**: Don't crash the proxy

### Initialization
1. **Minimal `__init__`**: Keep initialization simple
2. **Use Hooks**: Use appropriate hooks for different initialization stages
3. **Rely on Dependencies**: Declared dependencies are initialized before your plugin
4. **Fail Gracefully**: Handle missing dependencies

### Reloading
1. **Save State**: Use `attributes_to_save_on_reload` for important state, set in `__init__` or an `__init__` plugin hook (the loader restores them after construction)
2. **Clean Up**: Implement `uninitialize` hook for cleanup
3. **Test Reloads**: Ensure plugin can be reloaded without issues

### Resource Management
1. **Close Resources**: Close files, connections in `uninitialize` hook
2. **Persistent Data**: Use the data directory for files
3. **Memory Awareness**: Clean up large data structures on unload

### API Design
1. **Consistent Naming**: Name APIs `<resource>.<action>[.<qualifier>]` per [ADR-0004](../decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md)
2. **Version Compatibility**: Maintain backward compatibility
3. **Error Handling**: Return sensible defaults, log errors
4. **Documentation**: Document all public APIs

### Event Usage
1. **Priority Selection**: Choose appropriate priorities (lower = earlier)
2. **Event Data**: Don't modify event data unless intended
3. **Performance**: Keep event callbacks fast
4. **Error Handling**: Don't let exceptions escape event handlers
