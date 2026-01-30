# Settings System

## Overview

The settings system in bastproxy provides centralized configuration management for all plugins. It allows plugins to register settings with types, defaults, validation, and change notifications. Settings are persisted to disk and can be modified at runtime through commands or APIs.

The system is built on:
- **Plugin-level settings**: Each plugin has its own settings namespace
- **Type validation**: Settings have defined types that are validated on change
- **Persistence**: Settings are automatically saved to disk using PersistentDict
- **Change events**: Settings changes trigger events that plugins can listen to
- **User interface**: Commands for listing and modifying settings

## Key Components

### SettingsPlugin Class
**Location**: `plugins/core/settings/plugin/_settings.py`

The main plugin that manages all settings across the proxy:

```python
class SettingsPlugin(BasePlugin):
    def __init__(self):
        self.settings_map = {}        # Maps setting names to plugin_ids
        self.settings_info = {}       # Maps plugin_id -> settings metadata
        self.settings_values = {}     # Maps plugin_id -> PersistentDict
```

Features:
- **Centralized registry**: All settings from all plugins
- **Conflict detection**: Ensures setting names don't conflict across plugins
- **Automatic persistence**: Settings automatically save to disk
- **Event integration**: Raises events when settings change

### SettingInfo Class
**Location**: `plugins/core/settings/libs/_settinginfo.py`

Metadata for a single setting:

```python
class SettingInfo:
    def __init__(self, name, default, help, stype, **kwargs):
        self.name = name          # Setting name
        self.default = default    # Default value
        self.help = help          # Help text
        self.stype = stype        # Type (str, int, bool, color, etc.)
        self.nocolor = False      # Don't parse color codes when displaying
        self.readonly = False     # Can't be changed by user
        self.hidden = False       # Don't show in settings list
        self.aftersetmessage = "" # Message to show after setting changed
```

### Setting Types

Supported setting types:
- **str**: String values
- **int**: Integer values
- **bool**: Boolean values (True/False)
- **color**: Color codes (e.g., "@R", "@G")
- **timelength**: Time duration values
- Custom types can be added via validation functions

## How It Works

### 1. Registering Settings

Plugins register settings during initialization:

```python
class MyPlugin(BasePlugin):
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        # Register a setting
        self.api("plugins.core.settings:add")(
            self.plugin_id,           # Plugin ID
            "my_setting",             # Setting name
            "default_value",          # Default value
            "str",                    # Type
            "Help text for setting",  # Help text
            readonly=False,           # Optional: make readonly
            hidden=False             # Optional: hide from users
        )
```

### 2. Getting Setting Values

Retrieve settings anywhere in the code:

```python
# Get a setting value
value = self.api("plugins.core.settings:get")(plugin_id, "setting_name")

# Example
max_retries = self.api("plugins.core.settings:get")(
    "plugins.core.proxy",
    "max_retries"
)
```

### 3. Changing Settings

Change settings programmatically or via commands:

```python
# Change a setting
success = self.api("plugins.core.settings:change")(
    plugin_id,
    "setting_name",
    new_value
)

# Setting to "default" resets to default value
self.api("plugins.core.settings:change")(
    plugin_id,
    "setting_name",
    "default"
)
```

### 4. Listening to Changes

Plugins can react to setting changes:

```python
@RegisterToEvent(event_name="ev_myplugin_var_mysetting_modified")
def _eventcb_setting_changed(self):
    event_record = self.api("plugins.core.events:get.current.event.record")()
    var_name = event_record["var"]
    new_value = event_record["newvalue"]
    old_value = event_record["oldvalue"]

    # React to the change
    self.configure_with_new_value(new_value)
```

### 5. Persistence

Settings are automatically persisted:
- Stored in `data/plugins/<plugin_id>/settingvalues.txt`
- Format: JSON by default
- Automatically saved when changed
- Loaded on plugin startup

## Setting Events

### Per-Setting Events

Each non-hidden setting gets its own event:
- **Event name**: `ev_{plugin_id}_var_{setting_name}_modified`
- **When raised**: When the setting value changes
- **Event args**:
  - `var`: Setting name
  - `newvalue`: New value
  - `oldvalue`: Old value

### Plugin Lifecycle Events

Settings system listens to:
- `ev_plugin_loaded`: Initialize settings for new plugin
- `ev_plugin_unloaded`: Save and remove settings for unloaded plugin
- `ev_plugin_save`: Save plugin settings
- `ev_plugin_reset`: Reset plugin settings to defaults

## Important Files

### Core Settings System
- `plugins/core/settings/plugin/_settings.py` - Main settings plugin
- `plugins/core/settings/libs/_settinginfo.py` - SettingInfo class
- `plugins/core/settings/__init__.py` - Plugin metadata
- `plugins/core/settings/_patch_base.py` - BasePlugin "set" command

### Integration
- Uses `PersistentDict` for storage (libs/persistentdict.py)
- Integrates with command system for user interface
- Works with events system for change notifications

## Common APIs

### Settings Management
- `plugins.core.settings:add` - Register a new setting
- `plugins.core.settings:get` - Get a setting value
- `plugins.core.settings:change` - Change a setting value
- `plugins.core.settings:reset` - Reset all plugin settings to defaults
- `plugins.core.settings:get.setting.info` - Get metadata for a setting
- `plugins.core.settings:get.all.for.plugin` - Get all settings for a plugin
- `plugins.core.settings:format.setting` - Format a setting for display
- `plugins.core.settings:get.all.settings.formatted` - Get all settings formatted
- `plugins.core.settings:is.setting.hidden` - Check if setting is hidden
- `plugins.core.settings:save.plugin` - Save settings for a plugin
- `plugins.core.settings:remove.plugin.settings` - Remove plugin settings
- `plugins.core.settings:initialize.plugin.settings` - Initialize plugin settings
- `plugins.core.settings:raise.event.all.settings` - Raise events for all settings

## Commands

### List Settings
```
#bp.settings.list [search] [-p plugin]
```
Lists all settings, optionally filtered:
- `search`: Only show settings containing this string
- `-p plugin`: Only show settings for specified plugin

### Change Setting
```
#bp.settings.pset <name> <value> [-p plugin]
```
Change a setting value:
- `name`: Setting name
- `value`: New value (or "default" to reset)
- `-p plugin`: Plugin ID (optional, auto-detected from setting name)

### Per-Plugin Set Command
Each plugin also gets a `set` command:
```
#bp.<plugin>.set <name> <value>
```
List or set settings for that specific plugin.

## Common Patterns

### Registering Settings

```python
class MyPlugin(BasePlugin):
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        # Simple string setting
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "server_url",
            "http://localhost",
            "str",
            "The server URL to connect to"
        )

        # Integer setting
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "max_retries",
            3,
            "int",
            "Maximum number of connection retries"
        )

        # Boolean setting
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "enable_logging",
            True,
            "bool",
            "Enable detailed logging"
        )

        # Color setting
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "highlight_color",
            "@R",
            "color",
            "Color for highlighting important messages"
        )

        # Hidden setting (for internal use)
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "internal_state",
            "",
            "str",
            "Internal state variable",
            hidden=True
        )

        # Readonly setting
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "version",
            "1.0.0",
            "str",
            "Plugin version",
            readonly=True
        )
```

### Using Settings

```python
class MyPlugin(BasePlugin):
    def connect_to_server(self):
        # Get settings
        server_url = self.api("plugins.core.settings:get")(
            self.plugin_id,
            "server_url"
        )
        max_retries = self.api("plugins.core.settings:get")(
            self.plugin_id,
            "max_retries"
        )

        # Use settings
        for attempt in range(max_retries):
            if self.try_connect(server_url):
                return True
        return False
```

### Reacting to Changes

```python
class MyPlugin(BasePlugin):
    @RegisterToEvent(event_name="ev_plugins_myplugin_var_server_url_modified")
    def _eventcb_server_url_changed(self):
        event_record = self.api("plugins.core.events:get.current.event.record")()
        new_url = event_record["newvalue"]
        old_url = event_record["oldvalue"]

        LogRecord(
            f"Server URL changed from {old_url} to {new_url}",
            level="info",
            sources=[self.plugin_id]
        )()

        # Reconnect with new URL
        self.reconnect()

    @RegisterToEvent(event_name="ev_plugins_myplugin_var_enable_logging_modified")
    def _eventcb_logging_changed(self):
        event_record = self.api("plugins.core.events:get.current.event.record")()
        enabled = event_record["newvalue"]

        if enabled:
            self.setup_detailed_logging()
        else:
            self.disable_detailed_logging()
```

### Validating Custom Types

```python
# Settings system uses plugins.core.utils:verify.value for validation
# Custom types can be added by extending that plugin

# Example: Using timelength type
self.api("plugins.core.settings:add")(
    self.plugin_id,
    "timeout",
    "30s",
    "timelength",
    "Connection timeout"
)

# When retrieved, it's automatically validated
timeout_seconds = self.api("plugins.core.settings:get")(
    self.plugin_id,
    "timeout"
)  # Returns integer seconds
```

## Integration Points

### Command System
- Settings provides commands for listing and modifying settings
- Each plugin gets a `set` command automatically
- Settings can be changed via commands with validation

### Event System
- Each setting change raises an event
- Plugins can register callbacks for setting changes
- Settings system listens to plugin lifecycle events

### Plugin System
- Settings are registered during plugin initialization
- Settings are saved when plugins are unloaded
- Settings persist across plugin reloads
- BasePlugin includes settings-related hooks

### PersistentDict
- Settings values stored in PersistentDict per plugin
- Automatic JSON serialization
- Atomic writes for data safety

## Best Practices

### Setting Design
1. **Clear Names**: Use descriptive setting names (e.g., `server_url` not `srv`)
2. **Good Defaults**: Provide sensible default values
3. **Helpful Text**: Write clear help text explaining what the setting does
4. **Right Type**: Use appropriate types (int for numbers, bool for flags, etc.)
5. **Hidden Internals**: Mark internal settings as hidden

### Performance
1. **Cache Values**: Cache frequently-used setting values instead of calling API repeatedly
2. **Batch Changes**: Change multiple settings before triggering expensive operations
3. **Avoid Loops**: Don't call get() inside tight loops

### Change Handling
1. **React Appropriately**: Only register change events if you need to react
2. **Validate Changes**: Settings system validates types, but you may need domain validation
3. **Handle Errors**: Be prepared for invalid values (even with validation)
4. **Update State**: Update internal state when settings change

### Documentation
1. **Document Settings**: List all settings in plugin documentation
2. **Explain Effects**: Document what happens when settings change
3. **Show Examples**: Provide example values for complex settings
4. **Version Changes**: Note when settings are added/changed/removed

## Unique Patterns

### Aftersetmessage

Display additional information after a setting is changed:

```python
self.api("plugins.core.settings:add")(
    self.plugin_id,
    "log_level",
    "INFO",
    "str",
    "Logging level (DEBUG, INFO, WARNING, ERROR)",
    aftersetmessage="Restart required for logging changes to take full effect"
)
```

### Settings Map

The settings map prevents conflicts:
- Maps setting names (without plugin prefix) to plugin IDs
- Ensures no two plugins have the same setting name
- Used for quick lookup in commands

### Auto-initialization

Settings are automatically initialized when plugins load:
- Event `ev_plugin_loaded` triggers initialization
- All settings get their events created
- Previous values are loaded from disk

### Default Reset

Using "default" as a value resets to default:
```
#bp.settings.pset my_setting default
```

## Examples

### Complete Plugin with Settings

```python
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.libs.records import LogRecord
from bastproxy.plugins.core.events import RegisterToEvent

class Plugin(BasePlugin):
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        # Register settings
        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "api_key",
            "",
            "str",
            "API key for external service"
        )

        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "poll_interval",
            60,
            "int",
            "Seconds between polling the service"
        )

        self.api("plugins.core.settings:add")(
            self.plugin_id,
            "enabled",
            True,
            "bool",
            "Enable/disable the service"
        )

        # Initialize internal state
        self.service = None

    @RegisterPluginHook("initialize")
    def _phook_initialize(self):
        # Get settings and initialize
        if self.api("plugins.core.settings:get")(self.plugin_id, "enabled"):
            self.start_service()

    def start_service(self):
        api_key = self.api("plugins.core.settings:get")(
            self.plugin_id,
            "api_key"
        )
        poll_interval = self.api("plugins.core.settings:get")(
            self.plugin_id,
            "poll_interval"
        )

        if not api_key:
            LogRecord(
                "API key not set, service disabled",
                level="warning",
                sources=[self.plugin_id]
            )()
            return

        self.service = ExternalService(api_key, poll_interval)
        self.service.start()

    @RegisterToEvent(event_name="ev_plugins_myservice_var_enabled_modified")
    def _eventcb_enabled_changed(self):
        event_record = self.api("plugins.core.events:get.current.event.record")()
        if event_record["newvalue"]:
            self.start_service()
        else:
            if self.service:
                self.service.stop()
                self.service = None

    @RegisterToEvent(event_name="ev_plugins_myservice_var_poll_interval_modified")
    def _eventcb_interval_changed(self):
        if self.service:
            event_record = self.api("plugins.core.events:get.current.event.record")()
            self.service.set_poll_interval(event_record["newvalue"])
```

## Common Issues

### Setting Not Found

If settings aren't registered properly:
- Check that `settings:add` is called during `__init__` hook
- Verify plugin_id is correct
- Ensure settings system plugin is loaded

### Changes Not Persisting

If changes don't persist:
- Settings are automatically saved on change
- Check file permissions on data directory
- Verify PersistentDict is working

### Event Not Firing

If change events don't fire:
- Hidden settings don't fire events
- Events only fire when value actually changes
- Check event name matches pattern: `ev_{plugin_id}_var_{setting_name}_modified`

### Type Validation Failing

If type validation fails:
- Ensure `plugins.core.utils` plugin is loaded
- Check that type name is correct
- Verify value can be converted to the specified type
