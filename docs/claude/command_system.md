---
title: Command System
description: How client commands are parsed, dispatched and documented
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - commands
---

# Command System

## Overview

The command system in bastproxy provides a comprehensive framework for parsing and executing commands from clients. Commands follow the pattern `#bp.<package>.<plugin>.<command>` (for example `#bp.core.commands.list`) and support argument parsing, help text, command history, and automatic discovery.

The system is built on:
- **Automatic command registration**: Commands discovered via decorators
- **Argument parsing**: Built on Python's argparse for robust parsing
- **Command history**: Tracks and allows rerunning previous commands
- **Fuzzy matching**: Matches partial package, plugin and command names (rules under [Command Invocation](#2-command-invocation))
- **Help generation**: Automatic help text from decorators and docstrings

## Key Components

### CommandsPlugin Class
**Location**: `src/bastproxy/plugins/core/commands/plugin/_commands.py`

The main plugin that manages all commands:

```python
class CommandsPlugin(BasePlugin):
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        self.commands_list: list[str] = []                    # "plugin_id.command" strings
        self.command_data: dict[str, dict[str, CommandClass]] = {}  # by plugin id, then command name
        self.command_history_data = ...                       # the saved history list (history.txt)
        self.current_command: CommandClass | None = None      # the command that is running
        self.current_input_event = None                       # guard for the event being handled
```

The prefix is not an attribute: it is the `cmdprefix` setting (default `#bp`), read with
`plugins.core.commands:command.prefix.get`.

Features:
- **Command registry**: Tracks all commands across all plugins
- **Fuzzy matching**: Finds packages, plugins and commands from partial names
- **History management**: Stores command history with size limit
- **Output formatting**: Standardizes command output

### CommandClass
**Location**: `src/bastproxy/plugins/core/commands/libs/_command.py`

Represents a single command:

```python
class CommandClass:
    def __init__(self, plugin_id, name, function, arg_parser,
                 format=True, group=None, preamble=True, show_in_history=True, shelp=""):
        self.plugin_id = plugin_id          # Owning plugin
        self.name = name                    # Command name
        self.function = function            # Bound method to execute
        self.arg_parser = arg_parser        # argp.ArgumentParser, built by the commands plugin
        self.group = group or ""            # the plugin sets the plugin id when no group is given
        self.show_in_history = show_in_history   # read by find_command: False = not recorded in the history
        self.format = format                # read when a client types the command: False = output not framed
        self.preamble = preamble            # read by format_return_message: False = no Begin/End Command lines
        self.full_cmd = "#bp.core.commands.list"  # the prefix, plugin and name, as typed
        self.count = 0                      # lifetime calls, kept across plugin reloads
        self.count_since_reload = 0         # calls since this instance was created
        self.stats = CommandStats()         # error_count, last_error, last_error_time
```

`show_in_history` decides whether the command line is recorded in the history: `find_command` returns it as its
third value. `format` and `preamble` are honoured when a command runs from client input (CM-2): `format=False`
returns the output unframed, and `preamble=False` drops the `Begin Command`, start time, finish time and
`End Command` lines.

`count` and `stats` carry over when the plugin reloads or unloads and loads again, and when the
commands plugin itself reloads. They reset when the proxy restarts. `count_since_reload` resets
whenever the command is rebuilt. Only an exception raised by the command function counts as an
error: bad arguments and a function returning `False` do not. `stats.last_error` is the string
`"<ExceptionType>: <message>"`, never the exception object.

### Command Decorators
**Location**: `src/bastproxy/plugins/core/commands/libs/_utils.py`

Decorators for defining commands. A method is registered when its name starts with `_command_` and it
carries `command_data`, which any of the three decorators creates; `AddCommand` is optional (a method with
only `@AddParser` is named after the method). A decorated method with another name is skipped without a
message.

```python
@AddCommand(name="mycommand", show_in_history=True)
@AddParser(description="Does something useful")
@AddArgument("arg1", help="First argument")
@AddArgument("-o", "--option", help="Optional argument")
def _command_mycommand(self):
    """Command implementation."""
    args = self.api("plugins.core.commands:command.current.args.get")()
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
        args = self.api("plugins.core.commands:command.current.args.get")()

        value = args["value"]
        verbose = args["verbose"]

        if verbose:
            return True, [f"Processing {value} in verbose mode"]
        return True, [f"Processed {value}"]
```

Write the decorators in this order by convention:
1. `@AddCommand` - Sets the name, group and options (optional)
2. `@AddParser` - Sets up the argument parser
3. `@AddArgument` (multiple) - Adds arguments

Only the order of several `@AddArgument` lines matters: they are added to the parser from top to bottom.
Names, descriptions and argument help are formatted with the plugin's attributes (`{plugin_id}`, for example),
so a literal `{` or `}` in them makes that one command fail to build. It is skipped with an ERROR log line
naming the plugin, the function and the string, and the plugin's other commands register.

### 2. Command Invocation

Commands are invoked from clients:

```
#bp.<package>.myplugin.test myvalue -v
#bp.<package>.myplugin.test "value with spaces" --verbose
```

The package is required (`#bp.core.proxy.info` works, `#bp.proxy.info` does not), `plugins.` is optional and
each part may be abbreviated (`#bp.c.comm.list`). A line is split on the command separator (`|` by default)
before anything else, so an argument cannot contain it.

The system:
1. Detects the command prefix (`#bp`) at the start of the line, ignoring leading whitespace, and keeps the
   line from the MUD
2. Splits the line into package, plugin and command name
3. Matches the package and the plugin (fuzzy, loaded plugins only), then the command: an exact name, else the
   only name that starts with the text, else the best `token_set_ratio` score above 80 if it is unique
4. Parses arguments with `shlex` and argparse; unknown arguments are ignored
5. Executes the command function
6. Frames the output and sends it to the client that typed the command

### 3. Command Output

Commands return a tuple:
```python
return (success: bool, messages: list[str])
```

- `success`: True if command succeeded, False otherwise
- `messages`: List of strings to display to user

Output is framed by `CommandClass.format_return_message`: a `Begin Command` line, the start time, the
messages, the finish time and an `End Command` line (more sections when the `simple_output` setting is off).
Color codes are converted when the lines are sent. With `format=False` the command's messages are sent
unframed, and with `preamble=False` the `Begin Command`, start, finish and `End Command` lines are left out
of the frame (the rest of it is unchanged).
The messages must be a list of strings; a bare string is printed one character per line, and a command that
returns `False` gets its help appended to the output. An exception in the command prints
`Error running command` and is counted in the command's stats.

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
    args = self.api("plugins.core.commands:command.current.args.get")()
    query = args["query"]
    count = args["count"]
    filter_type = args["filter"]
    verbose = args["verbose"]
    # ...
```

### 5. Command History

Commands are automatically tracked:
- Stored in a persistent dict (`history.txt` in the plugin's data directory)
- Holds at most `historysize` entries; a line already in the history moves to the end
- Can be listed and shown again with `!`
- A found command is recorded only when its `show_in_history` is true; an unknown command is not

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
    shelp="Short help text",    # One-line help
    autoadd=True,               # False: do not register at load (add with command.add.by.func, force=True)
)
```

`show_in_history` decides whether the line is recorded in the history. `format=False` sends the output unframed
and `preamble=False` drops the `Begin Command` and `End Command` lines (with the start and finish times), when the
command runs from client input. The default name is the method name
without `_command_`.

### @AddParser

Configures the argument parser:

```python
@AddParser(
    description="Full description of command",
    epilog="Additional help text"  # Optional
)
```

`formatter_class` is replaced by `argp.CustomFormatter` after the parser is built, and positional arguments
to `AddParser` are stored and never used. The `-h` and `--help` flags are added to every command.

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
- `src/bastproxy/plugins/core/commands/plugin/_commands.py` - Main commands plugin
- `src/bastproxy/plugins/core/commands/libs/_command.py` - CommandClass implementation
- `src/bastproxy/plugins/core/commands/libs/_utils.py` - Command decorators
- `src/bastproxy/plugins/core/commands/libs/data/cmdargs.py` - Command argument data structures
- `src/bastproxy/plugins/core/commands/__init__.py` - Exports decorators

## Common APIs

### Command Execution
- `plugins.core.commands:command.current.args.get` - Get parsed args for current command
- `plugins.core.commands:command.format` - Get formatted command string
- `plugins.core.commands:command.run` - Run a command programmatically; returns `(success, messages)`
- `plugins.core.commands:output.line.length.get` - Get output line length for formatting

### Command Discovery
- `plugins.core.commands:command.add.by.func` - Add a command from a decorated method
- `plugins.core.commands:command.remove.for.plugin` - Remove a plugin's commands
- `plugins.core.commands:command.data.get` - Get command data for a plugin (`{}` for a valid plugin with no commands, or an invalid one)
- `plugins.core.commands:command.list.formatted` - Get formatted command list
- `plugins.core.commands:plugin.list.formatted` - Get formatted plugin list

### Output Formatting
- `plugins.core.commands:output.header.format` - Format output header
- `plugins.core.commands:output.subheader.format` - Format an output subheader

## Built-in Commands

### List Commands
```
#bp.core.commands.list [plugin] [command]
```
Lists available commands. `plugin` is the full plugin id (`plugins.core.proxy`):
- No args: Lists all plugins
- A package such as `plugins.core`: Lists the plugins in it
- `plugin`: Lists commands in plugin
- `plugin command`: Shows help for specific command (the exact command name)

### Command Detail
```
#bp.core.commands.detail <command>
```
Shows the details of one command: plugin, group, function, lifetime calls, calls since reload,
error count, last error and its time, and the last run start and end. The command is a
`package.plugin.command` name such as `core.commands.list`; fuzzy partial names work.

### Command History
```
#bp.core.commands.history [-c|--clear]
```
Shows command history or clears it with `-c`

### Rerun Command
```
#bp.core.commands.! [number]
```
Shows a command from the history; it does not run it again. Numbers are those of `history` (0-based):
- `!` - Shows the last entry
- `! -2` - Shows the entry 2 back from the end
- `! 5` - Shows entry 5

The reply goes to the client that typed it. Numbers index the history list the same way whether or not it is
full, and a number outside `-len <= number < len` gets an "outside of history length" message (CM-8, fixed in #395).

## Common Patterns

### Basic Command

```python
@AddCommand(name="hello", show_in_history=True)
@AddParser(description="Say hello")
@AddArgument("name", help="Name to greet")
def _command_hello(self):
    """Say hello to someone."""
    args = self.api("plugins.core.commands:command.current.args.get")()
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
    args = self.api("plugins.core.commands:command.current.args.get")()

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
    args = self.api("plugins.core.commands:command.current.args.get")()

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
    line_length = self.api("plugins.core.commands:output.line.length.get")()

    # Get header color from settings
    header_color = self.api("plugins.core.settings:setting.get")(
        "plugins.core.commands",
        "output_header_color"
    )

    # Build formatted output
    messages = [
        self.api("plugins.core.commands:output.header.format")("System Status"),
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
    args = self.api("plugins.core.commands:command.current.args.get")()
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
        get_logger(self.plugin_id).error("Error processing %s", filename, exc_info=True)
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

1. **Client Input**: User types a line in the client; `ProcessDataToMud` splits it on the command separator
2. **Event Raised**: `ev_to_mud_data_modify` is raised once per resulting line
3. **Prefix Check**: The commands plugin checks whether the left-stripped line starts with the prefix; if not, the
   line goes through the antispam check and on to the MUD
4. **Command Parse**: Package, plugin and command name are extracted; the line is marked not to be sent to the MUD
5. **Fuzzy Match**: Find the matching package, plugin and command
6. **Argument Parse**: Parse arguments with `shlex` and argparse
7. **Command Execute**: Call the command function
8. **Format Output**: Frame the returned messages
9. **Send to Client**: Send the output to the client that typed the line
10. **History Update**: Add the line to the history when the event says so (a found command always does)

## Advanced Features

### Command Prefix

The prefix is one setting for the whole proxy, `cmdprefix` of `plugins.core.commands` (change it with
`#bp.core.commands.set cmdprefix <value>`). A prefix that contains a `.` never matches (CM-12). Read it with:

```python
command_prefix = self.api("plugins.core.settings:setting.get")(
    "plugins.core.commands",
    "cmdprefix"
)
```

### Programmatic Execution

Run commands from code:

```python
# plugin id (full), command name, argument string; returns (success, messages),
# or (None, []) when the command does not exist
success, messages = self.api("plugins.core.commands:command.run")(
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
    args = self.api("plugins.core.commands:command.current.args.get")()
    # args["count"] is guaranteed to be a positive integer
    return True, [f"Limit set to {args['count']}"]
```

### Conditional Command Registration

Discovery scans the attributes of the plugin instance, so a function defined inside a method is never found.
Declare the command with `autoadd=False` and add it when the feature is available:

```python
@AddCommand(name="advanced", autoadd=False)
@AddParser(description="Advanced command")
def _command_advanced(self):
    return True, ["Advanced feature"]

@RegisterPluginHook("initialize")
def _phook_initialize(self):
    if self.has_advanced_features():
        self.api("plugins.core.commands:command.add.by.func")(self._command_advanced, force=True)
```

## Debugging Commands

### Show Command Details

```python
# Get command details
command_data = self.api("plugins.core.commands:command.data.get")(
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
except argp.ArgumentError as exc:  # the parser raises; it never exits
    print(f"Argument parsing failed: {exc.message}")
```

## Troubleshooting

### Command Not Found
- Check decorator order: @AddCommand, @AddParser, @AddArgument
- Verify plugin is loaded
- Check method name starts with `_command_` (a decorated method with another name is skipped silently)
- Check that `autoadd=False` is not set on `@AddCommand`
- Look in the log for an ERROR line "Command ... skipped": a `{` or `}` in a name, description or argument
  help skips that command; the plugin's other commands still register

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
- A command is recorded only when its `show_in_history` is true, and a failing one is recorded like any other
- An unknown `#bp` command is not recorded; the lines after it in the same input are recorded as usual (each line is decided on its own result)
- The history holds `historysize - 1` entries
