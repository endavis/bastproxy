# Project: bastproxy
# Filename: plugins/core/commands/_plugin.py
#
# File Description: a plugin that is the command interpreter for clients
#
# By: Bast

# Standard Library

import datetime
import shlex
from collections.abc import Callable

from libs import argp

# 3rd Party
# Project
from libs.api import API
from libs.records import LogRecord

from .data.cmdargs import CmdArgsRecord


class CommandClass:
    def __init__(
        self,
        plugin_id: str,
        name: str,
        function: Callable,
        arg_parser: argp.ArgumentParser,
        format: bool = True,
        group: str | None = None,
        preamble: bool = True,
        show_in_history: bool = True,
        shelp: str = "",
    ):
        self.name = name
        self.function = function
        self.plugin_id = plugin_id
        self.api = API(owner_id=f"{self.plugin_id}:{self.name}")
        self.arg_parser = arg_parser
        self.format = format
        self.group = group or ""
        self.preamble = preamble
        self.show_in_history = show_in_history
        self.full_cmd = self.api("plugins.core.commands:get.command.format")(
            self.plugin_id, name
        )
        self.short_help = shelp
        self.count = 0
        self.current_args: CmdArgsRecord | dict = {}
        self.current_arg_string = ""
        self.last_run_start_time: datetime.datetime | None = None
        self.last_run_end_time: datetime.datetime | None = None

    def run(
        self, arg_string: str = "", format=False
    ) -> tuple[bool | None, list[str], str]:
        """Run the command."""
        self.last_run_start_time = datetime.datetime.now(datetime.UTC)
        self.current_arg_string = arg_string
        message: list[str] = []
        command_ran = f"{self.full_cmd} {arg_string}"
        LogRecord(f"running {command_ran}", level="debug", sources=[self.plugin_id])(
            actor=f"{self.plugin_id}:run_command:command_ran"
        )

        success, parsed_args, fail_message = self.parse_args(arg_string)

        if not success:
            message.extend(fail_message)
            return self.run_finish(
                False, message, "could not parse args", format=format
            )

        args = CmdArgsRecord(
            f"{self.plugin_id}:{self.name}",
            vars(parsed_args),
            arg_string=arg_string,
            command=self.full_cmd,
        )

        if args["help"]:
            message.extend(self.arg_parser.format_help().splitlines())
            return self.run_finish(True, message, "help", format=format)

        self.current_args = args
        self.api("plugins.core.commands:set.current.command")(self)

        # run the command
        try:
            return_value = self()
        except Exception:
            actor = f"{self.plugin_id}:run_command:command_exception"
            message.extend([f"Error running command: {command_ran}"])
            LogRecord(
                f"Error running command: {command_ran}",
                level="error",
                sources=[self.plugin_id, "plugins.core.commands"],
                exc_info=True,
            )(actor)
            return self.run_finish(
                False, message, "function returned False", format=format
            )

        if isinstance(return_value, tuple):
            retval = return_value[0]
            message = return_value[1]
        else:
            retval = return_value
            message = []

        # did not succeed
        if retval is False:
            actor = f"{self.plugin_id}:run_command:returned_False"
            message.append("")
            message.extend(self.arg_parser.format_help().splitlines())
            return self.run_finish(
                False, message, "function returned False", format=format
            )

        return self.run_finish(True, message, "command ran successfully", format=format)

    def run_finish(
        self, success: bool, message: list[str], return_value: str, format=False
    ) -> tuple[bool, list[str], str]:
        """Run the command finisher."""
        oldmessage = message[:]
        self.last_run_end_time = datetime.datetime.now(datetime.UTC)
        if format:
            message = self.format_return_message(oldmessage)
        self.current_args = {}
        self.current_arg_string = ""
        self.api("plugins.core.commands:set.current.command")(None)
        return success, message, return_value

    def parse_args(self, arg_string):
        """Parse an argument string for this command."""
        # split it with shlex
        split_args_list = []
        args = {}
        fail_message = []
        if arg_string:
            try:
                split_args_list = shlex.split(arg_string)
            except ValueError as exc:
                actor = f"{self.plugin_id}:run_command:shell_parse_error"
                fail_message = [
                    f"@RError: Could not parse arguments: {exc.args[0]}@w",
                    "",
                ]
                fail_message.extend(self.arg_parser.format_help().splitlines())
                LogRecord(
                    f"Error parsing args for command {self.plugin_id}.{self.name} {arg_string} - {exc.args[0]}",
                    level="info",
                    sources=[self.plugin_id, "plugins.core.commands"],
                )(actor)
                return False, args, fail_message

        # parse the arguments and deal with errors
        try:
            args, _ = self.arg_parser.parse_known_args(split_args_list)
        except argp.ArgumentError as exc:
            actor = f"{self.plugin_id}:{self.name}:run_command:argparse_error"
            fail_message = [f"@RError: {exc.message}@w", ""]
            fail_message.extend(self.arg_parser.format_help().splitlines())
            LogRecord(
                f"Error parsing args for command {self.plugin_id}.{self.name} {arg_string} - {exc.message}",
                level="info",
                sources=[self.plugin_id, "plugins.core.commands"],
            )()
            return False, args, fail_message

        return True, args, ""

    def format_return_message(self, message):
        """Format a return message.

        Args:
            message: The message to format with plugin ID and command info.

        Returns:
            The formatted message with appropriate colors and formatting.

        """
        simple = self.api("plugins.core.settings:get")(
            "plugins.core.commands", "simple_output"
        )
        include_date = self.api("plugins.core.settings:get")(
            "plugins.core.commands", "include_date"
        )
        line_length = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "linelen"
        )
        preamble_color = self.api("plugins.core.proxy:preamble.color.get")()
        header_color = self.api("plugins.core.settings:get")(
            "plugins.core.commands", "header_color"
        )
        command_indent = self.api("plugins.core.commands:get.command.indent")()
        command_indent_string = " " * command_indent
        command_line_length = self.api(
            "plugins.core.commands:get.command.line.length"
        )()
        output_indent = self.api("plugins.core.commands:get.output.indent")()
        output_indent_string = " " * output_indent

        command = self.api("plugins.core.commands:get.command.format")(
            self.plugin_id, self.name
        )

        newmessage = [
            "",
            self.api("plugins.core.utils:center.colored.string")(
                f"Begin Command: {command}",
                "-",
                line_length,
                filler_color=preamble_color,
            ),
        ]
        if include_date:
            newmessage.append(
                self.api("plugins.core.utils:center.colored.string")(
                    f'Start: {self.last_run_start_time.strftime(self.api.time_format) if self.last_run_start_time else "Unknown"}',
                    "-",
                    line_length,
                    filler_color=preamble_color,
                )
            )

        if not simple:
            newmessage.extend(
                (
                    command_indent_string
                    + self.api("plugins.core.utils:center.colored.string")(
                        "Full Command Line",
                        "-",
                        command_line_length,
                        filler_color=header_color,
                    ),
                    f"{command_indent_string}{self.full_cmd} {self.current_arg_string}",
                )
            )
            if arg_message := [
                f"@G{item}@w: {'Not Specified' if self.current_args[item] is None else self.current_args[item]}"
                for item in self.current_args
                if item not in ["help"]
            ]:
                newmessage.append(
                    command_indent_string
                    + self.api("plugins.core.utils:center.colored.string")(
                        "Arguments", "-", command_line_length, filler_color=header_color
                    )
                )
                newmessage.extend(
                    [command_indent_string + line for line in arg_message]
                )

            newmessage.append(
                command_indent_string
                + self.api("plugins.core.utils:center.colored.string")(
                    "Output", "-", command_line_length, filler_color=header_color
                )
            )

        newmessage.extend(["", *[output_indent_string + line for line in message], ""])

        if not simple:
            newmessage.append(
                command_indent_string
                + self.api("plugins.core.utils:center.colored.string")(
                    "End Output",
                    "-",
                    command_line_length,
                    filler_color=header_color,
                )
            )

        if include_date:
            newmessage.append(
                self.api("plugins.core.utils:center.colored.string")(
                    f'Finish: {self.last_run_end_time.strftime(self.api.time_format) if self.last_run_end_time else "Unknown"}',
                    "-",
                    line_length,
                    filler_color=preamble_color,
                )
            )

        newmessage.extend(
            [
                self.api("plugins.core.utils:center.colored.string")(
                    f"End Command: {command}",
                    "-",
                    line_length,
                    filler_color=preamble_color,
                ),
                "",
            ]
        )

        return newmessage

    def __call__(self, *args, **kwargs):
        self.count += 1
        return self.function(*args, **kwargs)

    def __repr__(self) -> str:
        return f"Command({self.name}, {self.plugin_id}, {self.function})"

    __str__ = __repr__
