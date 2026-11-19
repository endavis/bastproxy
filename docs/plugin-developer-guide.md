---
title: Plugin Developer Guide
description: A task-oriented path for plugin authors, covering communication, plugin structure and reloading, hooks and events, commands and triggers
audience:
  - contributors
tags:
  - plugins
  - guide
---

# Plugin Developer Guide

This page is the path through writing a plugin. Each section gives a short how-to with excerpts
from code that ships with bastproxy, then links to the architecture page that holds the detail.
The pages under `docs/claude/` are organised by system; this one is organised by what a plugin
author does.

Every excerpt names its source file. The API names in this page are checked against the source by
`tests/test_plugin_developer_guide.py`.

- [Communicating with the client and the MUD](#communicating-with-the-client-and-the-mud)
- [Writing a plugin](#writing-a-plugin)
- [Hooks and events](#hooks-and-events)
- [Commands](#commands)
- [Triggers](#triggers)
- [Waiting for output](#waiting-for-output)

## Communicating with the client and the MUD

Data moves as a `NetworkData` (a list of `NetworkDataLine`) wrapped in one of four records. All
four are imported from `bastproxy.libs.records`.

| Record | Sends to | Raises first |
| :--- | :--- | :--- |
| `ProcessDataToMud` | the MUD | `ev_to_mud_data_modify`, for lines from a client |
| `SendDataDirectlyToMud` | the MUD | nothing; it raises `ev_to_mud_data_read` after sending |
| `ProcessDataToClient` | clients | `ev_to_client_data_modify`, for lines from the MUD |
| `SendDataDirectlyToClient` | clients | nothing; it raises `ev_to_client_data_read` after sending |

The `Process` records raise the modify event and then hand the message to the matching `Send`
record, so plugins such as commands, watch and triggers see the data first. A `Send` record
skips the modify event. Build the record and call it.

### To the client

From `src/bastproxy/plugins/core/proxy/plugin/_proxy.py`, `_api_proxy_restart`:

```python
from bastproxy.libs.records import NetworkData, SendDataDirectlyToClient

        SendDataDirectlyToClient(
            NetworkData(
                [f"Restarting bastproxy on port: {listen_port} in {restart_in} seconds"],
                owner_id=f"{self.plugin_id}:_api_proxy_restart",
            )
        )()
```

`clients=` and `exclude_clients=` take lists of client UUIDs; with neither, the data goes to every
client. `SendDataDirectlyToClient.can_send_to_client` in
`src/bastproxy/libs/records/rtypes/clientdata.py` decides per client: an excluded client never gets
it, a view-only client does not get internal lines unless it is named in `clients`, and a client
must be logged in unless the line is `prelogin`.

A command does not need any of this. It returns a `CommandResult`, and the commands plugin sends
the output to the client that ran it (see [Commands](#commands)).

### To the MUD

From `src/bastproxy/plugins/core/proxy/plugin/_proxy.py`, the password step after connecting:

```python
from bastproxy.libs.records import NetworkData, SendDataDirectlyToMud

                SendDataDirectlyToMud(NetworkData(pasw))()
```

`SendDataDirectlyToMud` accepts a `client_id`. It is stored on the record and given to
`ev_to_mud_data_read` listeners as `event_record["client_id"]`. Command history comes only from
client input that goes through `ProcessDataToMud`, so a send through `SendDataDirectlyToMud` is never
recorded. To keep a command out of history, use `@AddCommand(show_in_history=False)`.

Details: [Data flow](claude/data_flow.md#processing-records) and
[the four data events](claude/data_flow.md#data-flow-events).

## Writing a plugin

### File structure

A plugin is a package two levels under `plugins/`, with a `plugin/` subpackage:

```text
plugins/<package>/<plugin>/
    __init__.py        # metadata
    plugin/
        __init__.py    # exports Plugin
        _<plugin>.py   # the class
    libs/              # optional helpers
```

Bundled plugins live under `src/bastproxy/plugins/`. Your own plugins go in
`$BASTPROXY_HOME/plugins/<package>/<plugin>`, or ship them as an installed package; see
[packaging plugins](#packaging-plugins), [user plugins](claude/plugin_system.md#user-plugins) and
[the directory layout](claude/plugin_system.md#directory-layout).

The metadata is in the plugin's `__init__.py`. From `src/bastproxy/plugins/core/watch/__init__.py`:

```python
# these 4 are required
PLUGIN_NAME = "Command Watch"
PLUGIN_PURPOSE = "watch for specific commands from clients"
PLUGIN_AUTHOR = "Bast"
PLUGIN_VERSION = 1

PLUGIN_REQUIRED = True
```

Keep each line to a single assignment with nothing after the value; the metadata is read line by
line (see [plugin structure](claude/plugin_system.md#plugin-structure)).

The loader instantiates `plugin_module.Plugin(plugin_id, plugin_info)`, so the `plugin/` package
must export a name `Plugin`. From `src/bastproxy/plugins/core/help/plugin/__init__.py`:

```python
__all__ = ["Plugin"]

from ._help import HelpPlugin as Plugin
```

The class itself subclasses `BasePlugin` from `bastproxy.plugins._baseplugin`.

A module can set `CANRELOAD = False` (see `src/bastproxy/plugins/core/events/libs/_utils.py`). The
loader leaves such a module in `sys.modules` when the plugin is unloaded or reloaded, so it is not
imported again.

### Loading and reloading

The `pluginm` plugin has the commands:

```text
#bp.core.pluginm.load <plugin>
#bp.core.pluginm.unload <plugin>
#bp.core.pluginm.reload <plugin>
```

`<plugin>` is the plugin id without the `plugins.` prefix, for example `core.help`. Three
attributes of the plugin instance change what a reload does; their defaults are set in
`src/bastproxy/plugins/_baseplugin/_base.py`:

| Attribute | Default | Effect |
| :--- | :--- | :--- |
| `can_reload_f` | `True` | When `False`, a reload is refused and nothing is unloaded. The watch plugin sets it in its `__init__` hook. |
| `reload_dependents_f` | `False` | When `True`, the plugins that depend on this one are reloaded with it. The mudcmds plugin sets it. |
| `attributes_to_save_on_reload` | `[]` | Names of attributes to carry over. The proxy plugin sets `["mud_connection"]`. |

From `src/bastproxy/plugins/core/proxy/plugin/_proxy.py`:

```python
        self.attributes_to_save_on_reload = ["mud_connection"]
```

When the plugin is reloading, its `uninitialize` hook stores each named attribute with
`libs.plugins.reloadutils:cache.add`, and the loader restores them on the new instance right after
it is built. `cache.get` and `cache.remove` are the other two calls in
`src/bastproxy/libs/plugins/reloadutils.py`. Set the attribute list in your `__init__` hook;
see [reloading](claude/plugin_system.md#7-reloading) for the order of steps.

Three habits keep a reload clean:

- **Look plugin instances up at runtime.** Do not keep one in an attribute or other long-lived
  storage. A reload builds a new instance, and the old one stays alive for as long as anything
  refers to it, where it can still act next to the new one. Reach another plugin through its API
  instead; see [API usage](claude/api_system.md#api-usage).
- **Keep cross-plugin imports few.** A reload does not update names another module already
  imported. A decorator defined in a reloaded module stays the old object in every module that
  imported it, and those modules keep the old module alive until they are reloaded too.
- **Keep references out of the reload cache.** Do not name an attribute in
  `attributes_to_save_on_reload` when its value refers back to anything in the plugin being
  reloaded, since that would carry the old code into the new instance.

Data that depends on another plugin's state is rebuilt when that plugin reloads. The commands
plugin does this: its `ev_plugin_loaded` callback collects the `_command_*` methods of each new
plugin again.

## Packaging plugins

A plugin package can live in its own repository and be installed next to bastproxy. The package
holds one folder per plugin, each laid out as in [Writing a plugin](#writing-a-plugin):

```text
bastproxy-aardwolf/
    pyproject.toml
    src/bastproxy_aardwolf/
        __init__.py          # optional PACKAGE_DESCRIPTION
        connect/             # a plugin: PLUGIN_NAME in __init__.py, plugin/ subpackage
```

Register the package in the `bastproxy.plugins` entry-point group:

```toml
[project.entry-points."bastproxy.plugins"]
aardwolf = "bastproxy_aardwolf"
```

The entry name sets the plugin IDs: the plugin above is `plugins.aardwolf.connect`, whatever the
module is called. The name must be a valid identifier.

- **Same environment.** bastproxy reads entry points from its own environment, so the package
  must be installed there.
- **Developing.** Make bastproxy a dependency of the plugin repo and run it from there, so one
  `.venv` holds both. In the plugin repo's `pyproject.toml`:

  ```toml
  [tool.uv.sources]
  bastproxy = { path = "../bastproxy", editable = true }
  ```

  Then `uv run bastproxy` starts bastproxy with the plugin discovered.
- **Symlinks are not the same.** A symlink from `$BASTPROXY_HOME/plugins` runs the code in
  bastproxy's environment, without the package's own dependencies.
- **Overriding.** A copy in `$BASTPROXY_HOME/plugins` with the same plugin ID wins over the
  installed one, and a warning is logged. A bundled package name is never overridden.

See [Installed Plugin Packages](claude/plugin_system.md#installed-plugin-packages).

## Hooks and events

bastproxy has two mechanisms that are both called hooks in conversation. They differ in who may
create them.

### Lifecycle hooks

`RegisterPluginHook(hook_name, priority=50)` marks a `_phook_*` method to run at a point in the
plugin's life. The set is fixed: `VALID_HOOK_NAMES` in
`src/bastproxy/plugins/_baseplugin/libs/_pluginhooks.py` is `__init__`, `after_load`,
`character_active`, `save` and `uninitialize`. Any other name raises `ValueError`, so a plugin cannot create a new lifecycle
hook. From `src/bastproxy/plugins/test/triggers/plugin/_triggerex.py`:

```python
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook

    @RegisterPluginHook("after_load")
    def _phook_triggerex_initialize(self) -> None:
```

The `__init__` hook runs at the end of the base class's constructor, which is where
`src/bastproxy/plugins/core/watch/plugin/_watch.py` sets its attributes:

```python
    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.can_reload_f = False
```

The `character_active` hook runs each time the character becomes active (`ev_libs.api_character_active`),
and at load when the MUD is connected and the character is already active. It runs again after a
disconnect and a new login, once per login. Hooks in one plugin run in priority order; the order
across plugins follows `is_character_active_priority`. Use it instead of overriding
`_eventcb_baseplugin_after_character_is_active`:

```python
    @RegisterPluginHook("character_active", priority=50)
    def _phook_request_state(self) -> None:
        """Ask the MUD for the current state."""
        self.api("plugins.core.commands:command.run")("score")
```

The base class registers its own hooks at fixed priorities, which decides the order against yours;
see [plugin hooks](claude/plugin_system.md#plugin-hooks) for the table.

### Events

Events are what a plugin can create, register to and pass data through. The calls below are all
API calls made through `self.api(...)`.

**Create** an event with `"plugins.core.events:event.add"`. From `_api_watch_add` in
`src/bastproxy/plugins/core/watch/plugin/_watch.py`:

```python
        self.api("plugins.core.events:event.add")(
            item.event_name,
            item.owner,
            description=[f"event for {watch_name} for {regex}"],
            arg_descriptions={
                "matched": "The matched arguments from the regex",
                "cmdname": "The command name that was matched",
                "data": "The data that was matched",
            },
        )
```

**Raise** it with `"plugins.core.events:event.raise"`; the keyword `event_args` is the data. From
`_eventcb_check_command` in the same file:

```python
                self.api("plugins.core.events:event.raise")(item.event_name, event_args=match_args)
```

**Register** with the `RegisterToEvent` decorator on a method whose name starts with `_eventcb_`
(other names are ignored with a warning), or at runtime with
`"plugins.core.events:event.register"`, whose `prio` keyword sets the priority. From
`src/bastproxy/plugins/core/watch/plugin/_watch.py`:

```python
from bastproxy.plugins.core.events import RegisterToEvent

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded."""
        event_record = self.api("plugins.core.events:event.current.record.get")()
```

**Unregister** at runtime with `"plugins.core.events:event.unregister"`, passing the event name
and the function (see [unregistering](claude/event_system.md#unregistering-from-an-event)). When
a plugin unloads, its registrations are removed for it.

`{attribute}` placeholders in an event name are filled from the plugin instance. From
`src/bastproxy/plugins/core/triggers/plugin/_triggers.py`:

```python
    @RegisterToEvent(event_name="ev_{plugin_id}_var_enabled_modified")
```

**How data flows.** `Event.raise_event` in `src/bastproxy/plugins/core/events/plugin/_event.py`
turns the `event_args` dict into an `EventDataRecord` and runs a `ProcessRaisedEvent` for it. The
callbacks run in priority order, lower numbers first (50 is the default). A callback gets the
record with `"plugins.core.events:event.current.record.get"` and reads or changes its keys; the
next callback sees the change. `event.raise` returns the `ProcessRaisedEvent`, whose `event_data`
is the record after the callbacks have run.

With `data_list` and `key_name`, as the data events use, the same record is reused for each item:
`event_record["line"]` is set to each item in turn, and every callback runs for each one. An
exception in a callback is logged and the remaining callbacks still run. See
[how a data event runs](claude/data_flow.md#how-a-data-event-runs).

**Events worth knowing**, all raised from the base plugin or core plugins:

- `ev_plugin_loaded` and `ev_plugin_unloaded`, with `plugin_id` in the record
  (`src/bastproxy/plugins/_baseplugin/_base.py`)
- `ev_plugin_save`, when a plugin saves
- `ev_<plugin_id>_var_<setting>_modified`, raised by the settings plugin when a setting changes
  (`src/bastproxy/plugins/core/settings/plugin/_settings.py`)
- the four data events from the table above

The full list is in [common event names](claude/event_system.md#common-event-names).

## Commands

A command is a `_command_*` method that returns a `CommandResult`. The decorators come from
`bastproxy.plugins.core.commands`. From `_command_list` in
`src/bastproxy/plugins/core/watch/plugin/_watch.py`:

```python
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult

    @AddParser(description="list watches")
    @AddArgument(
        "match",
        help="list only watches that have this argument in them",
        default="",
        nargs="?",
    )
    def _command_list(self) -> CommandResult:
        """List watches."""
        args = self.api("plugins.core.commands:command.current.args.get")()
```

and its last line:

```python
        return CommandResult(True, message)
```

The smallest example is `_command_raise` in `src/bastproxy/plugins/test/cmddec/plugin/_cmddec.py`.
`CommandResult(success, message)` is defined in `src/bastproxy/plugins/core/commands/libs/_utils.py`;
`message` is a list of lines or one string, and `success=False` makes the dispatcher append the
command's help to the output.

A command is run as `#bp.<package>.<plugin>.<command>`, for example `#bp.core.pluginm.reload`.
`#bp` is the `cmdprefix` setting.

The path from the client's input to the output uses two events, both handled by the commands
plugin (`src/bastproxy/plugins/core/commands/plugin/_commands.py`):

- `ev_plugin_loaded`: `_eventcb_plugin_loaded` collects the new plugin's `_command_*` methods
  through `update_commands_for_plugin`. `ev_plugin_unloaded` removes them again.
- `ev_to_mud_data_modify`: `_eventcb_check_for_command` looks at each client line. When the line,
  left-stripped, starts with the `cmdprefix` setting, `run_internal_command_from_event` runs the
  command, sets `line.send = False` so the line does not reach the MUD, and sends the output with
  `SendDataDirectlyToClient(..., clients=...)` to the client that typed it. Any other line passes
  through to the MUD.

Details: [command execution flow](claude/command_system.md#command-execution-flow) and
[decorators](claude/command_system.md#command-decorators).

## Triggers

A trigger matches a line from the MUD against a regex and raises an event. From
`src/bastproxy/plugins/test/triggers/plugin/_triggerex.py`:

```python
    @RegisterPluginHook("after_load")
    def _phook_triggerex_initialize(self) -> None:
        """Register a test trigger to capture say events."""
        result = self.api("plugins.core.triggers:trigger.add")(
            "test_say", r"^(?P<object>.*) says, \"(?P<message>.*)\"$"
        )
        if result.success:
            self.api("plugins.core.triggers:trigger.register")(
                result.trigger.trigger_id, self._trigger_say
            )

    def _trigger_say(self) -> None:
        """Handle the test trigger by echoing the parsed event."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            print(f"_trigger_say - {event_record}")
        else:
            print("_trigger_say - No event record")

        if event_record["matches"]["message"] == "block":
            event_record["line"].send = False
        else:
            event_record["line"].line = (
                f"{event_record['matches']['object']} said something!!!!! "
                f"({event_record['matches']['message']})"
            )
```

`trigger.add` returns a `TriggerAddResult`; check its `.success`. The callback reads the named
groups from `event_record["matches"]`, gags the line with `event_record["line"].send = False`,
or rewrites it by assigning `event_record["line"].line`.

How it works:

- `TriggersPlugin._eventcb_check_trigger` registers to `ev_to_client_data_modify`, so it sees the
  lines `ProcessDataToClient` sends. It skips internal lines and matches `line.noansi`, the text
  without colour codes.
- A line a plugin or trigger sent to the MUD is recorded, and the MUD's exact echo of it is not matched against the regexes, once ([echoed commands](claude/triggers_system.md#echoed-commands)).
- Each trigger has its own event, named `event_<trigger_id>`, where the id is
  `t_<owner_id>_<name>` (`TriggerItem.event_name` and `TriggersPlugin.create_trigger_id` in
  `src/bastproxy/plugins/core/triggers/plugin/_triggers.py`). `TriggerItem.raisetrigger` adds
  `trigger_name` and `trigger_id` to the arguments before raising it.
- `trigger.register` registers a function to that event, which is why a trigger callback reads
  its data from `event.current.record.get` like any other event callback.

Details: [triggers system](claude/triggers_system.md), including the built-in triggers and the
common APIs.

## Reacting to GMCP

Register to `ev_libs.net.mud_gmcp_<package>`, the package lower-cased, to get one package without filtering the all-packages event. Parent prefixes are raised too, most specific first: `Char.Status` raises `..._char.status` then `..._char`, so a plugin registered on both is called twice.

```python
@RegisterToEvent(event_name="ev_libs.net.mud_gmcp_char.status")
def _eventcb_status(self):
    data = self.api("plugins.core.events:event.current.record.get")()["data"]
```

`libs.net.protocols:gmcp.value.get(path, default=None)` returns a copy of one cached value, such as `gmcp.value.get("Char.Status.state", 0)`. Event names are lower-cased, but value paths are case-sensitive. Subscribe to a package with `gmcp.modules.add`.

## Sending GMCP to the MUD

`libs.net.protocols:gmcp.send(package, data=None)` sends one GMCP message to the MUD. With no data
the bare package goes out, as Aardwolf expects; with data it is sent as compact JSON after the
package. It returns `True` when sent and `False` (with a logged warning, never an exception) when
there is no MUD link or GMCP is not enabled on it. Each send is recorded as a
`TelnetProtocolMessage` with `Direction.SENT`.

```python
@RegisterToEvent(event_name="ev_libs.net.mud_mudconnect")
def _eventcb_connect(self) -> None:
    self.api("libs.net.protocols:gmcp.send")("request char")
    self.api("libs.net.protocols:gmcp.send")("Char.Test", {"a": 1})
```

## Owning a telnet option

A plugin can own a telnet option the core does not handle, such as Aardwolf's option 102. The core
negotiates it and frames the data; the plugin decides what the bytes mean. Register it in the
`after_load` hook; the proxy unregisters it when the plugin unloads.

```python
@RegisterPluginHook("after_load")
def _phook_initialize(self) -> None:
    self.api("libs.net.protocols:telopt.register")(102)

@RegisterToEvent(event_name="ev_libs.net.mud_telopt_102_enabled")
def _eventcb_enabled(self) -> None:
    # Aardwolf: option 5 (channel tags) on
    self.api("libs.net.protocols:telopt.send")(102, bytes([5, 1]))

@RegisterToEvent(event_name="ev_libs.net.mud_telopt_102")
def _eventcb_data(self) -> None:
    data = self.api("plugins.core.events:event.current.record.get")()["data"]  # bytes
    if data == bytes([100, 3]):
        ...  # the character is active
```

- `telopt.register(option, owner_id=None, *, mud=True, client=True, forward=True)` returns `False`
  for a built-in option (GMCP, MSDP, NAWS, TTYPE and the others the core handles), another
  plugin's option or a number outside 0 to 254.
- Events: `ev_libs.net.mud_telopt_<n>` (`option`, `data` as raw `bytes`), `_enabled`, `_disabled`
  and `ev_libs.net.client_telopt_<n>` (`option`, `data`, `client_id`, `view_only`). `_enabled` is
  raised once per MUD connection, after the MUD writer is registered, so its handler can call
  `telopt.send` and the frame reaches the MUD.
- `telopt.send(option, payload)` sends to the MUD and `telopt.send.client(option, payload,
  client_id=None)` to logged-in clients that agreed. Both return `False` when nothing was sent, and log the reason at debug level.
- The MUD's subnegotiations are forwarded to clients that agreed. Turn that off with
  `telopt.forward.set(option, False)`. A client's subnegotiations are never sent to the MUD.
- A reload keeps the MUD option on: unloading sends no `DONT`, and registering again raises
  `_enabled` at once. A plugin that registers in its `after_load` hook does not have its
  `@RegisterToEvent` handlers attached yet, so it misses that raise: after registering, check
  `telopt.get(option)["mud_enabled"]` and run the enabled handling itself. A plugin that turned on
  MUD-side features turns them off itself when it unloads for good.
- `telopt.unregister(option)`, `telopt.unregister.for.owner(owner_id)` and `telopt.get(option)`
  complete the set.

Details: [data flow](claude/data_flow.md#custom-telnet-options-566-adr-0012) and
[ADR-0012](decisions/0012-plugins-own-telnet-options-the-core-does-not-handle-through-a-generic-hook.md).

## Running a line as the user would

To run a `#bp` command or send a MUD command, call `command.line.run`. The line goes through the
same path as typed input: the command separator splits it, and the MUD command queue and trigger
echo handling apply.

```python
    def _on_connect(self) -> None:
        self.api("plugins.core.commands:command.line.run")("#bp.core.proxy.info")
        self.api("plugins.core.commands:command.line.run")("look")
```

- The line is owned by the calling plugin and runs for the client being handled, if any.
- It stays out of the command history. Pass `show_in_history=True` to record it.
- To send and then wait for the answer, see below.

Details: [command system](claude/command_system.md#command-execution).

## Waiting for output

To send a command and then use the MUD's answer, ask the triggers plugin to wait for it. Event
callbacks are sync, so start the coroutine with `libs.asynch:task.add`.

```python
    def _start_score(self) -> None:
        self.api("libs.asynch:task.add")(self._read_score(), f"{self.plugin_id}:score")

    async def _read_score(self) -> None:
        result = await self.api("plugins.core.triggers:line.get.after.send")(
            "score", r"^Level: (?P<level>\d+)", timeout=5
        )
        if result is None:
            return  # timed out, or an error was logged
        level = result.matches["level"]
```

For several steps (send, match, then the prompt), open a waiter. It queues lines from the moment
it is added, so a line that arrives between steps is not lost:

```python
    async def _read_score_and_prompt(self) -> None:
        with self.api("plugins.core.triggers:waiter.add")() as waiter:
            result = await waiter.send_and_wait("score", r"^Level: (?P<level>\d+)", 5)
            prompt = await waiter.wait_for_prompt(5)
```

Notes:

- The APIs are `line.get.after.send`, `line.get.next`, `prompt.get.next` and `waiter.add`.
- The pattern uses `.match()`, so it must match from the start of the line. Start with `.*` to match anywhere.
- Waiters see the MUD's echo of a command you sent, so do not match the bare command text. They also work while the triggers `enabled` setting is off.
- A prompt wait needs the MUD to end its prompt with GA or EOR.
- A wait resolves to `None` on a timeout or an error (logged); it does not raise.

Details: [triggers system](claude/triggers_system.md#waiting-for-output).
