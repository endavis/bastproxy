# Project: bastproxy
# Filename: plugins/core/commands/plugin/_commands.py
#
# File Description: a plugin that is the command interpreter for clients
#
# By: Bast

# Standard Library
import copy
import dataclasses
import logging
import types
from typing import Any

from bastproxy.libs import argp

# 3rd Party
# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.context import get_command_args
from bastproxy.libs.logger import get_logger, log_to
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records import (
    NetworkData,
    SendDataDirectlyToClient,
    SendDataDirectlyToMud,
    UpdateFlag,
)
from bastproxy.libs.scan import find_methods
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddCommand, AddParser
from bastproxy.plugins.core.commands.libs._command import CommandClass, CommandStats
from bastproxy.plugins.core.events import RegisterToEvent


class CommandsPlugin(BasePlugin):
    """a class to manage internal commands."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self):
        """Init the class."""
        # a list of commands, such as 'core.msg.set' or 'clients.ssub.list'
        self.commands_list: list[str] = []

        # a dict of commands by plugin
        self.command_data: dict[str, dict[str, CommandClass]] = {}

        # command counts saved when a plugin unloads, restored when it re-adds commands
        self.saved_command_counts: dict[str, dict[str, int]] = {}

        # command error stats (as primitive dicts) saved the same way
        self.saved_command_stats: dict[str, dict[str, dict[str, Any]]] = {}

        # a list of commands that should not be run again if already in the queue
        self.no_multiple_commands = {}

        # the default command to run if no command is specified
        self.default_help_command = {
            "plugin_id": "plugins.core.pluginm",
            "command": "list",
        }

        # load the history
        self.history_save_file = self.plugin_info.data_directory / "history.txt"
        self.command_history_dict = PersistentDict(self.plugin_id, self.history_save_file, "c")
        if "history" not in self.command_history_dict:
            self.command_history_dict["history"] = []
        self.command_history_data = self.command_history_dict["history"]

        self.current_command: CommandClass | None = None
        self.current_input_event: None = None

        self.attributes_to_save_on_reload = [
            "current_input_event",
            "saved_command_counts",
            "saved_command_stats",
        ]

    @RegisterPluginHook("initialize")
    def _phook_initialize(self):
        """Initialize the instance."""
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "cmdprefix",
            "#bp",
            str,
            "the prefix to signify the input is a command",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "spamcount",
            20,
            int,
            "the # of times a command can be run before an antispam command",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "antispamcommand",
            "look",
            str,
            "the antispam command to send",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "cmdcount",
            0,
            int,
            "the # of times the current command has been run",
            readonly=True,
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "lastcmd",
            "",
            str,
            "the last command that was sent to the mud",
            readonly=True,
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "historysize", 50, int, "the size of the history to keep"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "header_color",
            "@M",
            "color",
            "the color to use for the command headers",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "output_header_color",
            "@B",
            "color",
            "the color to use for the header in the output of a command",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "output_subheader_color",
            "@G",
            "color",
            "the color to use for a subheader in the output of a command",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "command_indent", 0, int, "the indent for a command"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "simple_output",
            True,
            bool,
            "show simple output for commands",
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id, "multiline_headers", True, bool, "headers are multiline"
        )
        self.api("plugins.core.settings:setting.add")(
            self.plugin_id,
            "include_date",
            True,
            bool,
            "include the date in the output of a command",
        )

    @AddAPI("command.indent.get", description="indent for commands")
    def _api_command_indent_get(self):
        """Return the command indent."""
        return self.api("plugins.core.settings:setting.get")(self.plugin_id, "command_indent")

    @AddAPI("command.count", description="get a command count for a specific plugin")
    def _api_command_count(self, plugin_id):
        """Get the command count for a specific plugin."""
        return len(self.command_data[plugin_id]) if plugin_id in self.command_data else 0

    @AddAPI("output.indent.get", description="indent for command output")
    def _api_output_indent_get(self):
        """Return the output indent."""
        if self.api("plugins.core.settings:setting.get")(self.plugin_id, "simple_output"):
            return self.api("plugins.core.settings:setting.get")(self.plugin_id, "command_indent")

        return self.api("plugins.core.settings:setting.get")(self.plugin_id, "command_indent") * 2

    @AddAPI("output.header.format", description="format a header with the header color")
    def _api_output_header_format(self, header_text, line_length=None):
        """Format an output header."""
        if line_length is None:
            line_length = self.api("plugins.core.settings:setting.get")(
                "plugins.core.proxy", "linelen"
            )
        color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )

        return self._format_output_header(header_text, color, line_length)

    @AddAPI(
        "output.subheader.format",
        description="format a header with the subheader color",
    )
    def _api_output_subheader_format(self, header_text, line_length=None):
        """Format an output header."""
        if line_length is None:
            line_length = self.api("plugins.core.settings:setting.get")(
                "plugins.core.proxy", "linelen"
            )
        color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_subheader_color"
        )

        return self._format_output_header(header_text, color, line_length)

    @AddAPI("header.format", description="format a header with the specified color")
    def _api_header_format(self, header_text, color, line_length=None):
        """Format an output header."""
        if line_length is None:
            line_length = self.api("plugins.core.settings:setting.get")(
                "plugins.core.proxy", "linelen"
            )

        return self._format_output_header(header_text, color, line_length)

    def _format_output_header(self, header_text, color, line_length=None):
        """Format an output header."""
        if not line_length:
            line_length = self.api("plugins.core.settings:setting.get")(
                "plugins.core.proxy", "linelen"
            )

        if not color:
            color = self.api("plugins.core.settings:setting.get")(
                "plugins.core.commands", "output_header_color"
            )

        if _ := self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "multiline_headers"
        ):
            return [
                self.api("plugins.core.utils:line.cap")(
                    f"{'-' * (line_length - 2)}",
                    "+",
                    color=color,
                    line_length=line_length,
                    space=False,
                    fullcolor=True,
                ),
                self.api("plugins.core.utils:string.center.colored")(
                    header_text, " ", line_length, filler_color=color, endcaps=True
                ),
                self.api("plugins.core.utils:line.cap")(
                    f"{'-' * (line_length - 2)}",
                    "+",
                    color=color,
                    line_length=line_length,
                    space=False,
                    fullcolor=True,
                ),
            ]
        return [
            *self.api("plugins.core.utils:string.center.colored")(
                header_text, "-", line_length, filler_color=color
            ),
        ]

    @AddAPI("command.line.length.get", description="get line length for command")
    def _api_command_line_length_get(self):
        """Return the line length for output."""
        line_length = self.api("plugins.core.settings:setting.get")("plugins.core.proxy", "linelen")
        command_indent = self.api(f"{self.plugin_id}:command.indent.get")()
        return line_length - 2 * command_indent

    @AddAPI("output.line.length.get", description="get line length for command output")
    def _api_output_line_length_get(self):
        """Return the line length for output."""
        line_length = self.api("plugins.core.settings:setting.get")("plugins.core.proxy", "linelen")
        output_indent = self.api(f"{self.plugin_id}:output.indent.get")()
        return line_length - 2 * output_indent

    def _add_commands_for_all_plugins(self):
        """Add commands for all loaded plugins."""
        get_logger(self.plugin_id).debug("_eventcb_add_commands_on_startup: reload")
        for plugin_id in self.api("libs.plugins.loader:plugin.list.loaded")():
            get_logger(self.plugin_id).debug(
                "_eventdb_add_commands_on_startup: loading commands for %s", plugin_id
            )
            try:
                self.update_commands_for_plugin(plugin_id)
            except Exception:
                get_logger(self.plugin_id).error(
                    "Could not update commands for %s", plugin_id, exc_info=True
                )
        get_logger(self.plugin_id).debug("_eventcb_add_commands_on_reload: Finish")

    @RegisterToEvent(event_name="ev_plugin_loaded")
    def _eventcb_plugin_loaded(self):
        """Handle the plugin loaded event."""
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return

        if not self.api.startup and event_record["plugin_id"] == self.plugin_id:
            self._add_commands_for_all_plugins()
        else:
            get_logger(self.plugin_id).debug(
                "_eventcb_plugin_loaded: loading commands for %s", event_record["plugin_id"]
            )
            self.update_commands_for_plugin(event_record["plugin_id"])

    def update_commands_for_plugin(self, plugin_id):
        """Update all commands for a plugin."""
        plugin_instance = self.api("libs.plugins.loader:plugin.instance.get")(plugin_id)
        command_functions = self.get_command_functions_in_object(plugin_instance)
        get_logger(self.plugin_id).debug(
            "update_commands_for_plugin: %s has %s commands", plugin_id, len(command_functions)
        )
        if command_functions:
            command_names = [command.__name__ for command in command_functions]
            get_logger(self.plugin_id).debug("command_names = %r", command_names)
            for command in command_functions:
                try:
                    self.api(f"{self.plugin_id}:command.add.by.func")(command)
                except Exception:
                    get_logger(self.plugin_id).error(
                        "Could not add command %s for %s",
                        command.__name__,
                        plugin_id,
                        exc_info=True,
                    )

    def get_command_functions_in_object(self, base, recurse=True):
        """Recursively search for functions that are commands in a plugin instance.

        and it's attributes.
        """
        decorated = find_methods(base, lambda m: hasattr(m, "command_data"), recurse=recurse)
        commands = []
        warned: set[tuple[int, str]] = set()
        for method in decorated:
            if method.__name__.startswith("_command_"):
                commands.append(method)
                continue
            key = (id(method.__self__), method.__name__)
            if key in warned:
                continue
            warned.add(key)
            owner = getattr(method.__self__, "plugin_id", type(method.__self__).__name__)
            get_logger(self.plugin_id).warning(
                "Method %s in %s has command_data but its name does not start with "
                "'_command_', so it is not registered as a command",
                method.__name__,
                owner,
            )
        return commands

    @AddAPI("command.add.by.func", description="add a command based on a decorated function")
    def _api_command_add_by_func(self, func, force=False):
        """Add a command based on the new decorator stuff."""
        get_logger(self.plugin_id).debug("adding command from func %s", func.__name__)
        if hasattr(func, "__self__"):
            if hasattr(func.__self__, "name"):
                msg = (
                    f"func is from plugin {func.__self__.plugin_id} with name {func.__self__.name}"
                )
            else:
                msg = f"func is from plugin {func.__self__.plugin_id}"
            get_logger(self.plugin_id).debug("%s", msg)
        plugin_id = None

        if not (
            isinstance(func, types.MethodType)
            and func.__name__.startswith("_command_")
            and hasattr(func, "command_data")
        ):
            get_logger(self.plugin_id).warning("Function is not a command: %s", func.__name__)
            return

        if hasattr(func, "__self__") and hasattr(func.__self__, "plugin_id"):
            plugin_id = func.__self__.plugin_id  # pyright: ignore reportGeneralTypeIssues
        else:
            get_logger(self.plugin_id).warning("Function does not have a plugin: %s", func.__name__)
            return

        command_data = copy.deepcopy(func.command_data)  # pyright: ignore reportGeneralTypeIssues
        if not command_data.command["autoadd"] and not force:
            get_logger(self.plugin_id).debug(
                "Command %s in %s will not be added, autoadd set to False", func.__name__, plugin_id
            )
            return

        # Placeholders in the name, description and argument help are filled from the
        # plugin's attributes; a stray brace must skip only this command.
        current_string = ""
        try:
            if "name" in command_data.command:
                current_string = command_data.command["name"]
                command_name = current_string.format(**func.__self__.__dict__)
            else:
                command_name = func.__name__.replace("_command_", "")

            command_name = command_name.strip()

            if "name" in command_data.command["kwargs"]:
                del command_data.command["kwargs"]["name"]

            if "description" in command_data.argparse["kwargs"]:
                current_string = command_data.argparse["kwargs"]["description"]
                command_data.argparse["kwargs"]["description"] = current_string.format(
                    **func.__self__.__dict__
                )

            parser = argp.ArgumentParser(**command_data.argparse["kwargs"])
            for arg in command_data.arguments:
                current_string = arg["kwargs"]["help"]
                arg["kwargs"]["help"] = current_string.format(**func.__self__.__dict__)
                parser.add_argument(*arg["args"], **arg["kwargs"])
        except Exception:
            get_logger(self.plugin_id).error(
                "Command %s in %s skipped: could not build it from %r",
                func.__name__,
                plugin_id,
                current_string,
                exc_info=True,
            )
            return

        parser.add_argument("-h", "--help", help="show help", action="store_true")
        parser.formatter_class = argp.CustomFormatter

        parser.prog = self.api("plugins.core.commands:command.format")(self.plugin_id, command_name)

        command_kwargs = copy.deepcopy(command_data.command["kwargs"])

        # if no group, add the group as the plugin_name
        if "group" not in command_kwargs:
            command_kwargs["group"] = plugin_id

        # build the command dict
        if "preamble" not in command_kwargs:
            command_kwargs["preamble"] = True
        if "format" not in command_kwargs:
            command_kwargs["format"] = True
        if "show_in_history" not in command_kwargs:
            command_kwargs["show_in_history"] = True

        try:
            command = CommandClass(plugin_id, command_name, func, parser, **command_kwargs)
        except Exception:
            get_logger(self.plugin_id).error(
                "Error creating command %s: %s", func.__name__, command_kwargs, exc_info=True
            )
            return

        self.update_command(plugin_id, command_name, command)

        command_entry = f"{plugin_id}.{command_name}"
        if command_entry not in self.commands_list:
            self.commands_list.append(command_entry)

        log_to(
            [self.plugin_id, plugin_id],
            logging.DEBUG,
            "added command %s.%s",
            plugin_id,
            command_name,
        )

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self):
        """A plugin was unloaded.

        registered to the plugin_unloaded event
        """
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            if event_record["plugin_id"] != self.plugin_id:
                self.api(f"{self.plugin_id}:command.remove.for.plugin")(event_record["plugin_id"])
            else:
                get_logger(self.plugin_id).debug(
                    "%s_plugin_unloaded: %s is me!", self.plugin_id, self.plugin_id
                )

    @AddAPI("command.format", description="get a command string formatted for a plugin")
    def _api_command_format(self, plugin_id, command):
        """Return a command string formatted for the plugin.

        EX: plugin_id: plugins.core.proxy
            command: info
            returns:
               #bp.core.proxy.info
        """
        return f"{self.api('plugins.core.commands:command.prefix.get')()}.{plugin_id.replace('plugins.', '')}.{command}"

    @AddAPI(
        "command.current.args.get",
        description="get the currently executing command args",
    )
    def _api_command_current_args_get(self):
        """Get the current command args."""
        return get_command_args()

    @AddAPI("command.current.set", description="set the currently executing command")
    def _api_command_current_set(self, command):
        """Set the current command."""
        self.current_command = command

    @AddAPI("command.remove.for.plugin", description="remove all command data for a plugin")
    def _api_command_remove_for_plugin(self, plugin_id):
        """Remove all command data for a plugin.

        @Yplugin@w    = the plugin to remove commands for.

        this function returns no values
        """
        log_to(
            [self.plugin_id, plugin_id], logging.DEBUG, "removing commands for plugin %s", plugin_id
        )
        if self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id):
            # remove commands from _command_list that belong to plugin_id
            prefix = f"{plugin_id}."
            self.commands_list = [
                command for command in self.commands_list if not command.startswith(prefix)
            ]
            # drop the command data, keeping the counts for a reload
            removed = self.command_data.pop(plugin_id, {})
            CommandsPlugin._save_command_data(self, plugin_id, removed)

    def _save_command_data(self, plugin_id: str, commands: dict[str, CommandClass]) -> None:
        """Save the counts and error stats of a plugin's commands for a later re-add."""
        if not commands:
            return
        self.saved_command_counts[plugin_id] = {name: cmd.count for name, cmd in commands.items()}
        stats = {
            name: dataclasses.asdict(cmd.stats)
            for name, cmd in commands.items()
            if hasattr(cmd, "stats")
        }
        if stats:
            self.saved_command_stats[plugin_id] = stats

    @AddAPI("command.prefix.get", description="get the current command prefix")
    def _api_command_prefix_get(self):
        """Get the current command prefix.

        returns the current command prefix as a string
        """
        return self.api("plugins.core.settings:setting.get")(self.plugin_id, "cmdprefix")

    @AddAPI("command.help.format", description="format a help string for a command")
    def _api_command_help_format(self, plugin_id, command_name):
        """Get the help for a command.

        @Yplugin@w        = the plugin the command is in
        @Ycommand_name@w  = the command name.

        returns the help message as a string
        """
        # get the command data for the plugin

        if self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id) and (
            command_data := self.get_command_data_from_plugin(plugin_id, command_name)
        ):
            return command_data.arg_parser.format_help()

        return ""

    @AddAPI("command.data.get", description="get the command data for a plugin")
    def _api_command_data_get(self, plugin_id):
        """Get the data for commands for the specified plugin.

        @Yplugin@w   = the plugin the command is in.

        returns a dictionary of commands
        """
        if self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id):
            return self.command_data.get(plugin_id, {})
        return {}

    @AddAPI("command.run", description="run a command and return the output")
    def _api_command_run(
        self, plugin_id: str, command_name: str, argument_string: str = "", format=False
    ) -> tuple[bool | None, list[str]]:
        """Run a command and return the output.

        @Yplugin_id@w          = the plugin_id the command is in
        @Ycommand_name@w    = the command name
        @Yargument_string@w = the string of parameters for the command.

        returns a tuple
          first item:
            True if the command was successful
            False if the command was not successful
            None if the command was not found
          second item:
            a list of strings for the output of the command
        """
        log_to(
            [self.plugin_id, plugin_id],
            logging.DEBUG,
            "running command %s from plugin %s with arguments %s",
            command_name,
            plugin_id,
            argument_string,
        )
        if command := self.get_command_data_from_plugin(plugin_id, command_name):
            success, message, _ = command.run(argument_string, format)
            if not success:
                log_to(
                    [self.plugin_id, plugin_id],
                    logging.DEBUG,
                    "command %s from plugin %s failed with message %s",
                    command_name,
                    plugin_id,
                    message,
                    stack_info=True,
                )
            return success, message

        log_to(
            [self.plugin_id, plugin_id],
            logging.WARNING,
            "command %s from plugin %s not found",
            command_name,
            plugin_id,
            stack_info=True,
        )
        return None, []

    def add_command_to_history(self, command: str):
        """Add to the command history.

        Args:
            command: The command string to add to history.

        Returns:
            True if successful, False if not successful.

        """
        # remove existing
        if command in self.command_history_data:
            self.command_history_data.remove(command)

        # append the command
        self.command_history_data.append(command)

        # if the size is greater than historysize, pop the first item
        if len(self.command_history_data) > self.api("plugins.core.settings:setting.get")(
            self.plugin_id, "historysize"
        ):
            self.command_history_data.pop(0)

        # sync command history
        self.command_history_dict.sync()

    # return a list of all commands known
    def api_get_all_commands_list(self):
        """Return a list of all commands.

        returns a list of commands
        """
        return self.commands_list

    # retrieve a command from a plugin
    def get_command_data_from_plugin(self, plugin_id, command) -> CommandClass | None:
        """Get the command from the plugin data.

        Args:
            plugin_id: The ID of the plugin.
            command: The command to retrieve.

        Returns:
            None if not found, the CommandClass if found.

        """
        # find the instance
        if self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id) and (
            data := self.command_data.get(plugin_id, {})
        ):
            # return the command
            return data.get(command, None)

        return None

    # update a command
    def update_command(self, plugin_id, command_name, command: CommandClass):
        """Update a command.

        Args:
            plugin_id: The ID of the plugin that owns the command.
            command_name: The name of the command to update.
            command: The new CommandClass instance with updated data.

        Returns:
            True if successful, False if not successful.

        """
        if not self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id):
            log_to(
                [plugin_id, self.plugin_id],
                logging.DEBUG,
                "commands - update_command: plugin %s does not exist",
                plugin_id,
            )
            return False

        if plugin_id not in self.command_data:
            self.command_data[plugin_id] = {}

        plugin_command_data = self.command_data[plugin_id]

        if command_name not in plugin_command_data and not self.api.startup:
            log_to(
                [plugin_id, self.plugin_id],
                logging.DEBUG,
                "commands - update_command: plugin %s does not have command %s",
                plugin_id,
                command_name,
            )

        # update any items from the old command to the new command
        if command_name in plugin_command_data:
            old = plugin_command_data[command_name]
            command.count = old.count
            if (old_stats := getattr(old, "stats", None)) is not None:
                command.stats = old_stats
        elif command_name in (saved := self.saved_command_counts.get(plugin_id, {})):
            command.count = saved.pop(command_name)
            if not saved:
                self.saved_command_counts.pop(plugin_id, None)

        if command_name not in plugin_command_data and command_name in (
            saved_stats := self.saved_command_stats.get(plugin_id, {})
        ):
            command.stats = CommandStats(**saved_stats.pop(command_name))
            if not saved_stats:
                self.saved_command_stats.pop(plugin_id, None)

        plugin_command_data[command_name] = command

        return True

    def pass_through_command_from_event(self) -> None:
        """Pass through data to the mud.

        this assumes the command is not a #bp command

        Arguments:
          required:
            event_data - the data from the to_mud event

        returns the updated event
        """
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return

        original_command = event_record["line"].line

        # if the command is the same as the last command, do antispam checks
        if original_command == self.api("plugins.core.settings:setting.get")(
            self.plugin_id, "lastcmd"
        ):
            self.api("plugins.core.settings:setting.set")(
                self.plugin_id,
                "cmdcount",
                self.api("plugins.core.settings:setting.get")(self.plugin_id, "cmdcount") + 1,
            )

            # if the command has been sent spamcount times, then we send an antispam
            # command in between
            if self.api("plugins.core.settings:setting.get")(
                self.plugin_id, "cmdcount"
            ) == self.api("plugins.core.settings:setting.get")(self.plugin_id, "spamcount"):
                event_record.addupdate(UpdateFlag.MODIFY, "Antispam Command sent", savedata=False)
                get_logger(self.plugin_id).debug(
                    "sending antspam command: %s",
                    self.api("plugins.core.settings:setting.get")(
                        "plugins.core.commands", "antispamcommand"
                    ),
                )
                SendDataDirectlyToMud(
                    NetworkData(
                        self.api("plugins.core.settings:setting.get")(
                            self.plugin_id, "antispamcommand"
                        )
                    ),
                    show_in_history=False,
                )()

                self.api("plugins.core.settings:setting.set")(self.plugin_id, "cmdcount", 0)
                return

            # if the command is seen multiple times in a row and it has been flagged to only be sent once,
            # swallow it
            if original_command in self.no_multiple_commands:
                event_record.addupdate(
                    UpdateFlag.MODIFY,
                    "this command has been flagged to only be sent once, sendtomud set to False",
                    savedata=False,
                )

                event_record["line"].send = False
                return
        else:
            # the command does not match the last command
            self.api("plugins.core.settings:setting.set")(self.plugin_id, "cmdcount", 0)
            get_logger(self.plugin_id).debug("resetting command to %s", original_command)
            self.api("plugins.core.settings:setting.set")(
                self.plugin_id, "lastcmd", original_command
            )

    def proxy_help(self, header, header2, data):
        """Print the proxy help.

        Args:
            header: The main header to print.
            header2: The secondary header to print.
            data: The help data to display.

        Returns:
            The formatted help data as a list of strings.

        """
        newoutput = [
            "",
            *self.api(f"{self.plugin_id}:output.header.format")(header),
            "To send a command to the proxy, prefix it with a #bp",
            "Commands are not required to start with 'plugins'",
            "However, they must include the package",
            "The proxy will do its best to find the correct command",
            "Valid:     #bp.core.proxy.info -h",
            "           #bp.c.proxy",
            "           #bp.co.prox",
            "Not Valid: #bp.proxy.info -h",
            "           #bp.proxy",
            #            "".join(["@B", '-' * 80]),
        ]
        if header2:
            newoutput.extend(("".join(["@B", f"{header2}"]), "".join(["@B", "-" * 80])))
        newoutput.extend(data)
        newoutput.append("")

        return newoutput

    def error_command_not_found_in_plugin(self, plugin_id, command=None):
        """Command not found in plugin."""
        message = []
        if command:
            message = [
                self.api("plugins.core.utils:line.cap")(
                    f"{'-' * (80 - 2)}",
                    "+",
                    color="@B",
                    line_length=80,
                    space=False,
                    fullcolor=True,
                ),
                self.api("plugins.core.utils:string.center.colored")(
                    f"@RError - Plugin {plugin_id.replace('plugins.', '')} has no command{f' : {command}' if command else ''}@w",
                    filler_character="-",
                    length=80,
                    filler_color="@B",
                    endcaps=True,
                ),
            ]

        message.extend(
            [
                *[
                    line.replace("plugins.", "")
                    for line in self.api(f"{self.plugin_id}:command.list.formatted")(plugin_id)
                ],
            ]
        )

        return self.proxy_help("Proxy Help", "", message)

    def error_plugin_not_found(self, plugin_id=None, package=None):
        """Plugin not found."""
        message = []
        if plugin_id:
            message = [
                self.api("plugins.core.utils:line.cap")(
                    f"{'-' * (80 - 2)}",
                    "+",
                    color="@B",
                    line_length=80,
                    space=False,
                    fullcolor=True,
                ),
                self.api("plugins.core.utils:string.center.colored")(
                    f"@RError - Unknown plugin{f' : {plugin_id}' if plugin_id else ''}@w",
                    filler_character="-",
                    length=80,
                    filler_color="@B",
                    endcaps=True,
                ),
            ]

        plugins = [
            line.replace("plugins.", "")
            for line in self.api("libs.plugins.loader:plugin.list.in.package")(package)
        ]

        message.extend(
            [
                *self.api(f"{self.plugin_id}:output.header.format")(
                    f"Available Plugins in {package}"
                ),
                *self.api("plugins.core.utils:column.format")(
                    plugins, cols=3, columnwise=False, gap=6
                ),
            ]
        )
        return self.proxy_help("Proxy Help", "", message)

    def error_package_not_found(self, package=None):
        """Package not found."""
        message = [
            self.api("plugins.core.utils:line.cap")(
                f"{'-' * (80 - 2)}",
                "+",
                color="@B",
                line_length=80,
                space=False,
                fullcolor=True,
            ),
            self.api("plugins.core.utils:string.center.colored")(
                f"@RError - Unknown package{f' : {package}' if package else ''}@w",
                filler_character="-",
                length=80,
                filler_color="@B",
                endcaps=True,
            ),
            *self.api(f"{self.plugin_id}:output.header.format")("Available Packages"),
            *[
                line.replace("plugins.", "")
                for line in self.api("libs.plugins.loader:package.list")(active_only=True)
            ],
        ]
        return self.proxy_help("Proxy Help", "", message)

    def find_command_only_prefix(self):
        """Found only the command_prefix."""
        # found just the command prefix
        # get the list of packages
        message = [
            *self.api(f"{self.plugin_id}:output.header.format")("Available Packages"),
            *[
                line.replace("plugins.", "")
                for line in self.api("libs.plugins.loader:package.list")(active_only=True)
            ],
        ]
        return self.proxy_help("Proxy Help", "", message)

    def find_command(
        self, command_line: str
    ) -> tuple[CommandClass | None, str, bool, str, list[str]]:
        """Find a command from the client."""
        message: list[str] = []
        get_logger(self.plugin_id).debug("find_command: %s", command_line)

        # copy the command
        command = command_line

        commandprefix = self.api("plugins.core.settings:setting.get")(self.plugin_id, "cmdprefix")
        command_str = command

        if command_str in [
            commandprefix,
            f"{commandprefix}.",
            f"{commandprefix}.plugins",
            f"{commandprefix}.plugins.",
        ]:
            return None, "", False, "Proxy Help", self.find_command_only_prefix()

        # split the string into the command and the command_args
        found, new_package, new_plugin, tmessage, command_split, command_args = (
            self.find_command_split_command_string(command_str)
        )

        if not found:
            if tmessage == "Bad Package":
                # did not get a package, so output the list of packages
                output = self.error_package_not_found(command_split[0])
                return None, "", False, command_str, output
            if tmessage == "Bad Plugin":
                # did not get a plugin, so output the list of plugins in the package
                output = self.error_plugin_not_found(command_split[1], new_package)
                return None, "", False, command_str, output

        get_logger(self.plugin_id).debug("%s %s %s %s", found, new_package, new_plugin, tmessage)

        # get all the pieces of the command
        temp_package = command_split[0]
        get_logger(self.plugin_id).debug("temp_package=%r", temp_package)
        temp_command = command_split[2] if len(command_split) > 2 else ""
        # try and find the command
        command_data = self.api(f"{self.plugin_id}:command.data.get")(new_plugin)
        command_list = list(command_data.keys())
        get_logger(self.plugin_id).debug("command_list=%r", command_list)
        get_logger(self.plugin_id).debug("temp_command=%r", temp_command)

        new_command = self.api("plugins.core.fuzzy:string.match.best")(
            temp_command, tuple(command_list), scorer="token_set_ratio"
        )

        if not new_command:
            # did not get a command, so output the list of commands in the plugin
            output = self.error_command_not_found_in_plugin(new_plugin, temp_command)
            return None, "", False, command_str, output

        # got it all
        command_item = command_data[new_command]

        return (
            command_item,
            command_args,
            command_item.show_in_history,
            f"found {command_item.full_cmd}",
            message,
        )

    def find_command_split_command_string(
        self, command_str: str
    ) -> tuple[bool, str, str, str, list, str]:
        """Split a command string into its parts."""
        commandprefix = self.api("plugins.core.settings:setting.get")(self.plugin_id, "cmdprefix")

        cmd_args_split = command_str.split(" ", 1)
        command_str = cmd_args_split[0]
        command_args = cmd_args_split[1] if len(cmd_args_split) > 1 else ""
        get_logger(self.plugin_id).debug(
            "looking for %s, %s, %s", command_str, command_str, command_args
        )

        # split the command by the '.'
        command_split = command_str.split(".")
        get_logger(self.plugin_id).debug("command_split=%r", command_split)

        # remove the command prefix
        if commandprefix in command_split:
            del command_split[command_split.index(commandprefix)]

        # remove the literal 'plugins' string
        if command_split[0] == "plugins":
            del command_split[0]

        get_logger(self.plugin_id).debug("2: command_split=%r", command_split)

        # make sure there are two items in the list
        if len(command_split) == 1:
            command_split.append("")

        plugin_id_temp_str = f"{command_split[0]}.{command_split[1]}"

        new_package, new_plugin = self.api("libs.plugins.loader:plugin.id.match")(
            plugin_id_temp_str, active_only=True
        )

        found = False
        tmessage = ""
        if new_package and new_plugin:
            found = True
        elif new_package:
            tmessage = "Bad Plugin"
            found = False
        else:
            tmessage = "Bad Package"
            found = False

        return found, new_package, new_plugin, tmessage, command_split, command_args

    def run_internal_command_from_event(self):
        """Run the internal command from the client event.

        Any failure on the path (finding the command, formatting or sending the
        output) is logged and reported to the client as `Error running command`
        rather than being left to the event system, which would drop the line
        without a reply (#397).
        """
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        clients = [event_record["client_id"]] if event_record["client_id"] else None

        event_record["line"].send = False

        try:
            # leading whitespace is kept on the line for the MUD (#52), but a proxy
            # command is parsed from the left-stripped text
            command_item, command_args, show_in_history, notes, message = self.find_command(
                event_record["line"].line.lstrip()
            )

            if message:
                if isinstance(message, str):
                    message = [message]
                if isinstance(message, list):
                    message = NetworkData(message, owner_id="run_internal_command_from_event")
                SendDataDirectlyToClient(message, clients=clients)()

            if event_record["showinhistory"] != show_in_history:
                event_record["showinhistory"] = show_in_history
                event_record.addupdate(
                    UpdateFlag.MODIFY, f"show_in_history set to {show_in_history}", savedata=False
                )

            event_record.addupdate(
                UpdateFlag.INFO,
                f"find_command returned {notes}, arg string: '{command_args}'",
                savedata=False,
            )

            if command_item:
                get_logger(self.plugin_id).debug(
                    "found command %s.%s", command_item.plugin_id, command_item.name
                )

                success, message, error = command_item.run(command_args, format=command_item.format)

                if success:
                    event_record.addupdate(
                        UpdateFlag.INFO,
                        "run_command returned success",
                        savedata=False,
                    )
                else:
                    event_record.addupdate(
                        UpdateFlag.INFO, f"run_command returned error: {error}", savedata=False
                    )

                if message:
                    if isinstance(message, str):
                        message = [message]
                    if isinstance(message, list):
                        message = NetworkData(message, owner_id="run_internal_command_from_event")
                    SendDataDirectlyToClient(message, clients=clients)()
        except Exception:
            log_to(
                [self.plugin_id],
                logging.ERROR,
                "Error running command for line: %r",
                event_record["line"].line,
                exc_info=True,
            )
            try:
                SendDataDirectlyToClient(
                    NetworkData(
                        ["Error running command"], owner_id="run_internal_command_from_event"
                    ),
                    clients=clients,
                )()
            except Exception:
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "Could not tell the client about the command error",
                    exc_info=True,
                )

    @AddAPI("summary.get.for.plugin", description="get summary data for a plugin")
    def _api_summary_get_for_plugin(self, plugin_id):
        """Return stats for the plugin."""
        msg = []

        if plugin_id == self.plugin_id:
            msg.extend(
                (
                    self.api("plugins.core.utils:string.center.colored")(
                        "Overall Command Data", "=", 80, filler_color="@G"
                    ),
                    f"Total Commands for all plugins : {len(self.commands_list)}",
                    "",
                    self.api("plugins.core.utils:string.center.colored")(
                        f"{self.plugin_id} specific data", "=", 80, filler_color="@G"
                    ),
                )
            )

        command_data = self.api(f"{self.plugin_id}:command.data.get")(plugin_id)

        commands = [command.name for command in command_data.values()]

        command_str = "".join(f"{'':<26}{item}\n" for item in commands)

        count = len(commands)

        msg.extend(
            [
                f"{f'{count} Commands':<23} : {command_str.strip()}",
            ]
        )

        return msg

    @AddAPI("detail.get.for.plugin", description="get detailed data for a plugin")
    def _api_detail_get_for_plugin(self, plugin_id):
        """Get detailed data for a plugin."""
        command_data = self.api(f"{self.plugin_id}:command.data.get")(plugin_id)

        if not command_data:
            return ["None"]

        columns = [
            {"name": "Command Name", "key": "name", "width": 20},
            {"name": "Function", "key": "function_name", "width": 20},
        ]

        sorted_keys = sorted(command_data.keys())
        data = [
            {
                "name": command_data[command].name,
                "function_name": command_data[command].function.__name__,
            }
            for command in sorted_keys
        ]

        count = len(data)

        return [
            *self.api("plugins.core.utils:table.format")(
                f"{count} Commands for plugin: {plugin_id}", data, columns
            )
        ]

    @RegisterToEvent(event_name="ev_to_mud_data_modify")
    def _eventcb_check_for_command(self) -> None:
        """Check if the line is a command from the client.

        if it is, the command is parsed and executed
        and the output sent to the client.
        """
        commandprefix = self.api("plugins.core.settings:setting.get")(self.plugin_id, "cmdprefix")

        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return

        if self.current_input_event == event_record:
            get_logger(self.plugin_id).debug(
                "current_input_event: %s is being processed, skipping", self.current_input_event
            )
            self.current_input_event = None
            return

        self.current_input_event = event_record

        # the flag is shared by every line of the input, so a line's own result must not
        # reach the next line (#390): read this line's value, then put the input's back
        input_show_in_history = event_record["showinhistory"]

        if event_record["line"].line.lstrip().startswith(commandprefix):
            self.run_internal_command_from_event()

        else:
            self.pass_through_command_from_event()

        line_show_in_history = event_record["showinhistory"]
        event_record["showinhistory"] = input_show_in_history

        if line_show_in_history and not event_record["line"].internal:
            self.add_command_to_history(event_record["line"].line)

        self.current_input_event = None

    # remove a command
    def _api_remove_command(self, plugin_id, command_name):
        """Remove a command.

        @Yplugin@w        = the top level of the command
        @Ycommand_name@w  = the name of the command.

        this function returns no values
        """
        if not self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id):
            log_to(
                [self.plugin_id, plugin_id],
                logging.WARNING,
                "remove command: plugin %s does not exist",
                plugin_id,
            )
            return False

        data = self.command_data[plugin_id]
        if data and command_name in data:
            del data[command_name]
            self.api(f"{plugin_id}:data.update")("commands", data)
            log_to(
                [self.plugin_id, plugin_id],
                logging.DEBUG,
                "removed command %s.%s",
                plugin_id,
                command_name,
            )
            return True

        log_to(
            [self.plugin_id, plugin_id],
            logging.ERROR,
            "remove command: command %s.%s does not exist",
            plugin_id,
            command_name,
        )
        return False

    def format_command_list(self, command_list: list[CommandClass]):
        """Format a list of commands by a category.

        Args:
            command_list: The list of CommandClass instances to format.

        Returns:
            A list of strings for the formatted commands.

        """
        message = []
        output_header_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )
        for i in command_list:
            if i != "default" and i.arg_parser.description:
                tlist = i.arg_parser.description.splitlines()
                if not tlist[0]:
                    tlist.pop(0)
                message.append(
                    f"  {output_header_color}{i.name.replace('plugins.', ''):<10}@w : {tlist[0]}"
                )

        return message

    @AddAPI(
        "command.list.formatted",
        description="return a formatted list of commands for a plugin",
    )
    def _api_command_list_formatted(self, plugin_id):
        """Build a table of commands for a plugin.

        Args:
            plugin_id: The ID of the plugin to build commands from.

        Returns:
            A list of strings for the list of commands.

        """
        if not self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id):
            return []

        output_subheader_color = self.api("plugins.core.settings:setting.get")(
            self.plugin_id, "output_subheader_color"
        )

        commands: dict[str, CommandClass] = self.command_data.get(plugin_id, {})

        message = self.api(f"{self.plugin_id}:output.header.format")(
            f"Available Commands in {plugin_id.replace('plugins.', '')}"
        )

        groups = {}
        for i in sorted(commands.keys()):
            if i != "default":
                if commands[i].group not in groups:
                    groups[commands[i].group] = []

                groups[commands[i].group].append(commands[i])

        if plugin_id in groups:
            message.append(
                output_subheader_color
                + "-" * 5
                + " "
                + plugin_id.replace("plugins.", "")
                + " "
                + "-" * 5
                + "@w"
            )
            message.extend(self.format_command_list(groups[plugin_id]))
            message.append("")

        for group in sorted(groups.keys()):
            if group not in ["Base", "Debug/Info", plugin_id]:
                message.append(
                    output_subheader_color
                    + "-" * 5
                    + " "
                    + group.replace("plugins.", "")
                    + " "
                    + "-" * 5
                    + "@w"
                )
                message.extend(self.format_command_list(groups[group]))
                message.append("")

        message.append(output_subheader_color + "-" * 5 + " " + "Base" + " " + "-" * 5 + "@w")
        message.extend(self.format_command_list(groups.get("Base", [])))
        message.append("")

        return message

    @AddAPI("plugin.list.formatted", description="return a formatted list of all plugins")
    def _api_plugin_list_formatted(self, package=None):
        """List all plugins."""
        if package:
            plugin_id_list = [
                item.replace("plugins.", "")
                for item in self.api("libs.plugins.loader:plugin.list.in.package")(package)
            ]
        else:
            plugin_id_list = [
                item.replace("plugins.", "")
                for item in self.api("libs.plugins.loader:plugin.list.loaded")()
            ]

        if plugin_id_list := sorted(plugin_id_list):
            return self.api("plugins.core.utils:column.format")(
                plugin_id_list, cols=3, columnwise=False, gap=6
            )
        return ["No plugins found"]

    @AddCommand(shelp="list commands", show_in_history=False)
    @AddParser(description="list commands in a plugin")
    @AddArgument("plugin", help="the plugin to see help for", default="", nargs="?")
    @AddArgument(
        "command",
        help="the command in the plugin (not required)",
        default="",
        nargs="?",
    )
    def _command_list(self, _=None):
        """@G%(name)s@w - @B%(cmdname)s@w.

        list commands.

        @CUsage@w: @B%(cmdname)s@w @Yplugin@w
          @Yplugin@w    = The plugin to list commands for (optional)
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        message = []
        command = args["command"]
        plugin_id = args["plugin"]

        if not self.api("libs.plugins.loader:plugin.id.is.valid")(plugin_id):
            return True, self.api(f"{self.plugin_id}:plugin.list.formatted")(package=plugin_id)

        if plugin_commands := self.command_data.get(plugin_id, {}):
            if command and command in plugin_commands:
                help_message = plugin_commands[command].arg_parser.format_help().splitlines()
                message.extend(help_message)
            else:
                message.extend(self.api(f"{self.plugin_id}:command.list.formatted")(plugin_id))
        else:
            message.append(f"There are no commands in plugin {plugin_id}")

        return True, message

    def command_detail_data(self, command: CommandClass) -> list[dict[str, str]]:
        """Build the rows shown by the detail command."""

        def fmt(value: Any) -> str:
            if value is None:
                return "Never"
            return str(value.strftime(self.api.time_format))

        return [
            {"item": "Plugin", "value": command.plugin_id},
            {"item": "Group", "value": command.group},
            {"item": "Function", "value": command.function.__name__},
            {"item": "Calls (lifetime)", "value": str(command.count)},
            {"item": "Calls since reload", "value": str(command.count_since_reload)},
            {"item": "Errors", "value": str(command.stats.error_count)},
            {"item": "Last error", "value": command.stats.last_error or "None"},
            {"item": "Last error time", "value": fmt(command.stats.last_error_time)},
            {"item": "Last run start", "value": fmt(command.last_run_start_time)},
            {"item": "Last run end", "value": fmt(command.last_run_end_time)},
        ]

    @AddCommand(shelp="show details for a command", show_in_history=False)
    @AddParser(description="show the usage and error details for a command")
    @AddArgument("command", help="the command, e.g. core.commands.list", default="", nargs="?")
    def _command_detail(self, _=None):
        """@G%(name)s@w - @B%(cmdname)s@w.

        show details for a command: call counts, errors and last run times.

        @CUsage@w: @B%(cmdname)s@w @Ycommand@w
          @Ycommand@w    = The command, such as core.commands.list
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        if not args["command"]:
            return False, []

        command_item, _, _, _, message = self.find_command(args["command"])
        if command_item is None:
            return True, message

        columns = [
            {"name": "Item", "key": "item", "width": 20},
            {"name": "Value", "key": "value", "width": 40},
        ]
        return True, self.api("plugins.core.utils:table.format")(
            f"Command: {command_item.full_cmd}", self.command_detail_data(command_item), columns
        )

    @AddCommand(
        shelp="run a command in history",
        show_in_history=False,
        preamble=False,
        format=False,
        name="!",
    )
    @AddParser(description="run a command in history")
    @AddArgument("number", help="the history # to run", default=-1, nargs="?", type=int)
    def _command_run_history(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        act on the command history.

        @CUsage@w: @B%(cmdname)s@w @Ynumber@w
          @Ynumber@w    = The number of the command to rerun
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        number = args["number"]
        history_length = len(self.command_history_data)
        if not -history_length <= number < history_length:
            return True, ["# is outside of history length"]

        command = self.command_history_data[number]

        clients = None
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            client_id = event_record["client_id"]
            clients = [client_id] if client_id else None

        SendDataDirectlyToClient(
            NetworkData([f"Commands: rerunning command {command}"], owner_id="run_history"),
            clients=clients,
        )(f"{self.plugin_id}:_command_run_history")
        SendDataDirectlyToClient(
            NetworkData([f"{command}"], owner_id="run_history"), clients=clients
        )()

        return True, []

    @AddCommand(shelp="list or run a command in history", show_in_history=False)
    @AddParser(description="list the command history")
    @AddArgument("-c", "--clear", help="clear the history", action="store_true")
    def _command_history(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        list the command history.

        @CUsage@w: @B%(cmdname)s@w
        """
        args = self.api("plugins.core.commands:command.current.args.get")()

        message = []
        if args["clear"]:
            del self.command_history_dict["history"][:]
            self.command_history_dict.sync()
            message.append("Command history cleared")
        else:
            message.extend(
                f"{self.command_history_data.index(i)} : {i}" for i in self.command_history_data
            )
        return True, message

    @RegisterPluginHook("uninitialize")
    def _phook_commands_save_on_reload(self):
        """Keep every command's counts and stats when this plugin itself reloads."""
        if self.is_reloading_f:
            for pid, cmds in list(self.command_data.items()):
                CommandsPlugin._save_command_data(self, pid, cmds)

    @RegisterPluginHook("save")
    def _phook_commands_save(self):
        """Save states."""
        self.command_history_dict.sync()
