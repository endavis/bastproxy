# Command System

## Overview

The command system in bastproxy provides a comprehensive framework for parsing and executing commands from clients. Commands follow the pattern `#bp.<plugin>.<command>` and support argument parsing, help text, command history, and automatic discovery.

The system is built on:
- **Automatic command registration**: Commands discovered via decorators
- **Argument parsing**: Built on Python's argparse for robust parsing
- **Command history**: Tracks and allows rerunning previous commands
- **Fuzzy matching**: Intelligently matches partial plugin/command names
- **Help generation**: Automatic help text from decorators and docstrings

## Key Components

### CommandsPlugin Class
**Location**: `plugins/core/commands/plugin/_commands.py`

The main plugin that manages all commands:

```python
class CommandsPlugin(BasePlugin):
    def __init__(self):
        self.commands_list = {}          # All commands by unique ID
        self.command_data = {}           # Commands organized by plugin
        self.command_history_data = []   # Command history
        self.command_prefix = "#bp"      # Default command prefix
```

Features:
- **Command registry**: Tracks all commands across all plugins
- **Fuzzy matching**: Finds commands even with partial names
- **History management**: Stores command history with size limit
- **Output formatting**: Standardizes command output

### CommandClass
**Location**: `plugins/core/commands/libs/_command.py`

Represents a single command:

```python
class CommandClass:
    def __init__(self, name, function, plugin_id, **kwargs):
        self.name = name                    # Command name
        self.function = function            # Function to execute
        self.plugin_id = plugin_id          # Owning plugin
        self.arg_parser = ArgumentParser()  # Argument parser
        self.group = kwargs.get('group', 'Base')
        self.show_in_history = True
        self.format = True
        self.preamble = True
```

### Command Decorators
**Location**: `plugins/core/commands/libs/_utils.py`

Decorators for defining commands:

```python
@AddCommand(name="mycommand", show_in_history=True)
@AddParser(description="Does something useful")
@AddArgument("arg1", help="First argument")
@AddArgument("-o", "--option", help="Optional argument")
def _command_mycommand(self):
    """Command implementation."""
    args = self.api("plugins.core.commands:get.current.command.args")()
    # Process command
    return True, ["Success message"]
```

## How It Works

### 1. Command Registration

Commands are automatically discovered via decorators:

```python
class MyPlugin(BasePlugin):
    @AddCommand(name="test", show_in_history=True)
    @AddParser(description="Test command")
    @AddArgument("value", help="A value to test")
    @AddArgument("-v", "--verbose", action="store_true", help="Verbose output")
    def _command_test(self):
        """Test command implementation.

        Returns:
            tuple: (success: bool, messages: list[str])
        """
        # Get parsed arguments
        args = self.api("plugins.core.commands:get.current.command.args")()

        value = args["value"]
        verbose = args["verbose"]

        if verbose:
            return True, [f"Processing {value} in verbose mode"]
        return True, [f"Processed {value}"]
```

Decorators must be applied in this order:
1. `@AddCommand` - Marks method as a command
2. `@AddParser` - Sets up argument parser
3. `@AddArgument` (multiple) - Adds arguments

### 2. Command Invocation

Commands are invoked from clients:

```
#bp.myplugin.test myvalue -v
#bp.myplugin test "value with spaces" --verbose
```

The system:
1. Detects command prefix (`#bp`)
2. Parses plugin and command name
3. Uses fuzzy matching to find command
4. Parses arguments using argparse
5. Executes command function
6. Formats and returns output

### 3. Command Output

Commands return a tuple:
```python
return (success: bool, messages: list[str])
```

- `success`: True if command succeeded, False otherwise
- `messages`: List of strings to display to user

Output is automatically formatted with:
- Preamble (`#BP:`) if `preamble=True`
- Color code conversion
- Line endings

### 4. Argument Parsing

Uses Python's argparse under the hood:

```python
@AddCommand(name="search")
@AddParser(description="Search for items")
@AddArgument("query", help="Search query")
@AddArgument("-c", "--count", type=int, default=10, help="Max results")
@AddArgument("-f", "--filter", choices=["all", "active", "inactive"])
@AddArgument("-v", "--verbose", action="store_true")
def _command_search(self):
    args = self.api("plugins.core.commands:get.current.command.args")()
    query = args["query"]
    count = args["count"]
    filter_type = args["filter"]
    verbose = args["verbose"]
    # ...
```

### 5. Command History

Commands are automatically tracked:
- Stored in persistent dict
- Size-limited queue
- Can be listed and rerun
- Commands with `show_in_history=False` are excluded

## Command Decorators

### @AddCommand

Marks a method as a command:

```python
@AddCommand(
    name="mycommand",           # Command name (optional, uses method name)
    show_in_history=True,       # Include in command history
    format=True,                # Format output
    preamble=True,              # Add "#BP:" preamble
    group="MyGroup",            # Command group for organization
    shelp="Short help text"     # One-line help
)
```

### @AddParser

Configures the argument parser:

```python
@AddParser(
    description="Full description of command",
    formatter_class=argparse.RawDescriptionHelpFormatter,  # Optional
    epilog="Additional help text"  # Optional
)
```

### @AddArgument

Adds an argument to the command:

```python
# Positional argument
@AddArgument("name", help="Help text")

# Optional argument
@AddArgument("-o", "--option", help="Help text", default="value")

# Flag
@AddArgument("-v", "--verbose", action="store_true", help="Enable verbose")

# Choice
@AddArgument("-t", "--type", choices=["a", "b", "c"], help="Type selection")

# Multiple values
@AddArgument("files", nargs="+", help="One or more files")

# Optional with default
@AddArgument("count", nargs="?", type=int, default=10, help="Count")
```

Arguments support all argparse features:
- `type`: Converter function (int, float, etc.)
- `default`: Default value if not provided
- `nargs`: Number of arguments ("?", "*", "+", or number)
- `choices`: List of valid values
- `action`: "store", "store_true", "store_false", "append", etc.
- `required`: For optional arguments
- `metavar`: Name in help text
- `dest`: Destination variable name

## Important Files

### Core Command System
- `plugins/core/commands/plugin/_commands.py` - Main commands plugin
- `plugins/core/commands/libs/_command.py` - CommandClass implementation
- `plugins/core/commands/libs/_utils.py` - Command decorators
- `plugins/core/commands/libs/data/cmdargs.py` - Command argument data structures
- `plugins/core/commands/__init__.py` - Exports decorators

## Common APIs

### Command Execution
- `plugins.core.commands:get.current.command.args` - Get parsed args for current command
- `plugins.core.commands:get.command.format` - Get formatted command string
- `plugins.core.commands:run` - Run a command programmatically
- `plugins.core.commands:get.output.line.length` - Get output line length for formatting

### Command Discovery
- `plugins.core.commands:get.commands.for.plugin` - Get all commands for a plugin
- `plugins.core.commands:get.commands.for.plugin.data` - Get command data for a plugin
- `plugins.core.commands:list.commands.formatted` - Get formatted command list
- `plugins.core.commands:list.plugins.formatted` - Get formatted plugin list

### Output Formatting
- `plugins.core.commands:format.output.header` - Format output header
- `plugins.core.commands:format.output.line` - Format output line

## Built-in Commands

### List Commands
```
#bp.commands.list [plugin] [command]
```
Lists available commands:
- No args: Lists all plugins
- `plugin`: Lists commands in plugin
- `plugin command`: Shows help for specific command

### Command History
```
#bp.commands.history [-c|--clear]
```
Shows command history or clears it with `-c`

### Rerun Command
```
#bp.commands.! [number]
```
Reruns a command from history:
- `!` - Reruns last command
- `! -2` - Reruns command 2 back from end
- `! 5` - Reruns command #5

## Common Patterns

### Basic Command

```python
@AddCommand(name="hello", show_in_history=True)
@AddParser(description="Say hello")
@AddArgument("name", help="Name to greet")
def _command_hello(self):
    """Say hello to someone."""
    args = self.api("plugins.core.commands:get.current.command.args")()
    return True, [f"Hello, {args['name']}!"]
```

### Command with Options

```python
@AddCommand(name="fetch", group="Data")
@AddParser(description="Fetch data from source")
@AddArgument("source", help="Data source name")
@AddArgument("-f", "--format", choices=["json", "xml", "csv"],
             default="json", help="Output format")
@AddArgument("-l", "--limit", type=int, default=100, help="Max records")
@AddArgument("-v", "--verbose", action="store_true", help="Verbose output")
def _command_fetch(self):
    """Fetch data with various options."""
    args = self.api("plugins.core.commands:get.current.command.args")()

    source = args["source"]
    format_type = args["format"]
    limit = args["limit"]
    verbose = args["verbose"]

    # Fetch data
    data = self.fetch_from_source(source, limit)

    # Format output
    if format_type == "json":
        output = self.format_as_json(data)
    elif format_type == "xml":
        output = self.format_as_xml(data)
    else:
        output = self.format_as_csv(data)

    messages = [f"Fetched {len(data)} records from {source}"]
    if verbose:
        messages.extend(output)

    return True, messages
```

### Command with Subcommands

```python
@AddCommand(name="db", group="Database")
@AddParser(description="Database operations")
@AddArgument("operation", choices=["backup", "restore", "optimize"])
@AddArgument("-t", "--table", help="Specific table (optional)")
def _command_db(self):
    """Database management command."""
    args = self.api("plugins.core.commands:get.current.command.args")()

    operation = args["operation"]
    table = args["table"]

    if operation == "backup":
        return self.backup_database(table)
    elif operation == "restore":
        return self.restore_database(table)
    elif operation == "optimize":
        return self.optimize_database(table)
```

### Command with Formatted Output

```python
@AddCommand(name="status", group="Info")
@AddParser(description="Show system status")
def _command_status(self):
    """Show formatted system status."""
    # Get line length for formatting
    line_length = self.api("plugins.core.commands:get.output.line.length")()

    # Get header color from settings
    header_color = self.api("plugins.core.settings:get")(
        "plugins.core.commands",
        "output_header_color"
    )

    # Build formatted output
    messages = [
        self.api("plugins.core.commands:format.output.header")("System Status"),
        f"{'Service':<20} {'Status':<10} {'Uptime':<15}",
        header_color + "-" * line_length + "@w",
        f"{'Database':<20} {'Running':<10} {'2d 5h 30m':<15}",
        f"{'API Server':<20} {'Running':<10} {'2d 5h 30m':<15}",
        f"{'Worker Pool':<20} {'Running':<10} {'2d 5h 30m':<15}",
    ]

    return True, messages
```

### Error Handling

```python
@AddCommand(name="process")
@AddParser(description="Process data")
@AddArgument("file", help="File to process")
def _command_process(self):
    """Process a file with error handling."""
    args = self.api("plugins.core.commands:get.current.command.args")()
    filename = args["file"]

    try:
        # Process file
        result = self.process_file(filename)
        return True, [f"Successfully processed {filename}", f"Result: {result}"]

    except FileNotFoundError:
        return False, [f"@RError:@w File not found: {filename}"]

    except PermissionError:
        return False, [f"@RError:@w Permission denied: {filename}"]

    except Exception as e:
        LogRecord(
            f"Error processing {filename}",
            level="error",
            sources=[self.plugin_id],
            exc_info=True
        )()
        return False, [f"@RError:@w Failed to process {filename}: {str(e)}"]
```

## Integration Points

### Event System
- Commands execute within event context
- Can raise events during execution
- Access event data via APIs

### Settings System
- Commands can modify settings
- Built-in `set` command for each plugin
- Settings control command behavior

### Plugin System
- Commands automatically discovered from plugins
- Commands removed when plugin unloads
- Plugin dependencies affect command availability

### Output System
- Commands integrate with color system
- Output formatted for clients
- Preambles and line endings added automatically

## Best Practices

### Command Design
1. **Clear Names**: Use descriptive command names (e.g., `fetch` not `f`)
2. **Good Help**: Write clear descriptions and argument help
3. **Consistent Returns**: Always return `(bool, list[str])`
4. **Error Handling**: Handle errors gracefully, return False on failure
5. **Formatting**: Use formatting helpers for consistent output

### Arguments
1. **Required First**: Put required arguments before optional ones
2. **Sensible Defaults**: Provide defaults for optional arguments
3. **Type Hints**: Use `type=` parameter for non-string arguments
4. **Validation**: Validate arguments and return errors for invalid input
5. **Help Text**: Write helpful descriptions for all arguments

### Performance
1. **Quick Commands**: Keep commands responsive
2. **Async Operations**: Use async for long-running operations
3. **Progress Updates**: Show progress for long operations
4. **Resource Cleanup**: Clean up resources in finally blocks

### Organization
1. **Group Commands**: Use `group` parameter to organize related commands
2. **Name Consistently**: Use consistent naming patterns
3. **Document**: Add docstrings to command functions
4. **Test**: Test commands with various argument combinations

## Command Execution Flow

1. **Client Input**: User types command in client
2. **Event Raised**: `ev_to_mud_data_modify` raised with input
3. **Prefix Check**: Commands plugin checks for command prefix
4. **Command Parse**: Plugin and command name extracted
5. **Fuzzy Match**: Find matching plugin and command
6. **Argument Parse**: Parse arguments using argparse
7. **Command Execute**: Call command function
8. **Format Output**: Format return messages
9. **Send to Client**: Send formatted output to client
10. **History Update**: Add to command history if enabled

## Advanced Features

### Custom Command Prefix

Change the command prefix per plugin:

```python
command_prefix = self.api("plugins.core.settings:get")(
    "plugins.core.commands",
    "cmdprefix"
)
```

### Programmatic Execution

Run commands from code:

```python
success, message, error = self.api("plugins.core.commands:run")(
    "plugins.myplugin",
    "mycommand",
    "arg1 arg2 --flag"
)
```

### Custom Argument Types

```python
def positive_int(value):
    """Custom type for positive integers."""
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
    return ivalue

@AddCommand(name="limit")
@AddParser(description="Set limit")
@AddArgument("count", type=positive_int, help="Positive integer")
def _command_limit(self):
    args = self.api("plugins.core.commands:get.current.command.args")()
    # args["count"] is guaranteed to be a positive integer
    return True, [f"Limit set to {args['count']}"]
```

### Conditional Command Registration

```python
@RegisterPluginHook("__init__")
def _phook_init_plugin(self):
    # Only add command if feature is available
    if self.has_advanced_features():
        self.register_advanced_commands()

def register_advanced_commands(self):
    @AddCommand(name="advanced")
    @AddParser(description="Advanced command")
    def _command_advanced(self):
        return True, ["Advanced feature"]
```

## Debugging Commands

### Show Command Details

```python
# Get command details
command_data = self.api("plugins.core.commands:get.commands.for.plugin.data")(
    "plugins.myplugin"
)

for cmd_name, cmd_obj in command_data.items():
    print(f"Command: {cmd_name}")
    print(f"Function: {cmd_obj.function.__name__}")
    print(f"Group: {cmd_obj.group}")
    print(f"Help: {cmd_obj.arg_parser.description}")
```

### Test Arguments

```python
# Test argument parsing
parser = command_obj.arg_parser
try:
    args = parser.parse_args(["arg1", "arg2", "--flag"])
    print(f"Parsed: {args}")
except SystemExit:
    print("Argument parsing failed")
```

## Troubleshooting

### Command Not Found
- Check decorator order: @AddCommand, @AddParser, @AddArgument
- Verify plugin is loaded
- Check method name starts with `_command_`
- Ensure `set_command_autoadd(True)` is called

### Arguments Not Parsing
- Check argument names match what you're accessing
- Verify type conversions are correct
- Test with `parser.parse_args()` directly
- Check for typos in argument names

### Output Not Formatted
- Verify `format=True` in @AddCommand
- Check return value is `(bool, list[str])`
- Ensure messages are strings, not other types

### History Not Working
- Check `show_in_history=True` in @AddCommand
- Verify command executed successfully
- Check history size setting hasn't been exceeded
