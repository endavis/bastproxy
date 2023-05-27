# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/commands/_plugin.py
#
# File Description: a plugin that is the command interpreter for clients
#
# By: Bast

# Standard Library
from __future__ import print_function
import shlex
import typing

# 3rd Party

# Project
from libs.api import API
from libs.records import LogRecord, CmdArgsRecord
import libs.argp as argp

class Command:
    def __init__(self, plugin_id: str, name: str, function: typing.Callable,
                 arg_parser: argp.ArgumentParser, format: bool = True,
                 group: str | None = None, preamble: bool = True,
                 show_in_history: bool = True, shelp: str = ''):
        self.name = name
        self.function = function
        self.plugin_id = plugin_id
        self.api = API(owner_id=f"{self.plugin_id}:{self.name}")
        self.arg_parser = arg_parser
        self.format = format
        self.group = group or ''
        self.preamble = preamble
        self.show_in_history = show_in_history
        self.full_cmd = self.api('plugins.core.commands:get.command.format')(self.plugin_id, name)
        self.short_help = shelp
        self.count = 0
        self.current_args: CmdArgsRecord | dict = {}

    def run(self, arg_string: str = '') -> tuple[bool | None, list[str], str]:
        """
        run the command
        """
        message: list[str] = []
        command_ran = f"{self.full_cmd} {arg_string}"
        LogRecord(f"running {command_ran}",
                  level='debug', sources=[self.plugin_id])(actor = f"{self.plugin_id}:run_command:command_ran")

        success, parsed_args, fail_message = self.parse_args(arg_string)

        if not success:
            message.extend(fail_message)
            return False, message, 'could not parse args'

        args = CmdArgsRecord(f"{self.plugin_id}:{self.name}", vars(parsed_args), arg_string=arg_string)

        if args['help']:
            message.extend(self.arg_parser.format_help().split('\n'))
            return True, message, 'help'

        self.current_args = args
        self.api("plugins.core.commands:set.current.command")(self)

        # run the command
        try:
            return_value = self()
        except Exception:
            actor = f"{self.plugin_id}:run_command:command_exception"
            message.extend([f"Error running command: {command_ran}"])
            LogRecord(f"Error running command: {command_ran}",
                        level='error', sources=[self.plugin_id, 'plugins.core.commands'], exc_info=True)(actor)
            return self.run_finish(False, message, 'function returned False')

        if isinstance(return_value, tuple):
            retval = return_value[0]
            message = return_value[1]
        else:
            retval = return_value
            message = []

        # did not succeed
        if retval is False:
            actor = f"{self.plugin_id}:run_command:returned_False"
            message.append('')
            message.extend(self.arg_parser.format_help().split('\n'))
            return self.run_finish(False, message, 'function returned False')

        return self.run_finish(True, message, 'command ran successfully')

    def run_finish(self, success: bool, message: list[str], return_value: str) -> tuple[bool, list[str], str]:
        """
        run the command finisher
        """
        self.current_args = {}
        self.api("plugins.core.commands:set.current.command")(None)
        return success, message, return_value

    def parse_args(self, arg_string):
        """
        parse an argument string for this command
        """
        # split it with shlex
        split_args_list = []
        args = {}
        fail_message = []
        if arg_string:
            try:
                split_args_list = shlex.split(arg_string)
            except ValueError as exc:
                actor = f"{self.plugin_id}:run_command:shell_parse_error"
                fail_message = [f"@RError: Could not parse arguments: {exc.args[0]}@w", '']
                fail_message.extend(self.arg_parser.format_help().split('\n'))
                LogRecord(f"Error parsing args for command {self.plugin_id}.{self.name} {arg_string} - {exc.args[0]}",
                        level='info', sources=[self.plugin_id, 'plugins.core.commands'])(actor)
                return False, args, fail_message

        # parse the arguments and deal with errors
        try:
            args, _ = self.arg_parser.parse_known_args(split_args_list)
        except argp.ArgumentError as exc:
            actor = f"{self.plugin_id}:{self.name}:run_command:argparse_error"
            fail_message = [f"@RError: {exc.message}@w", '']
            fail_message.extend(self.arg_parser.format_help().split('\n'))
            LogRecord(f"Error parsing args for command {self.plugin_id}.{self.name} {arg_string} - {exc.message}",
                    level='info', sources=[self.plugin_id, 'plugins.core.commands'])()
            return False, args, fail_message

        return True, args, ''

    def format_return_message(self, message):
        """
        format a return message

        arguments:
          required:
            message     - the message
            plugin_id   - the id of the plugin
            command     - the command from the plugin

        returns:
          the updated message
        """
        #line_length = self.api('net.proxy:setting.get')('linelen')
        line_length = 80

        message.insert(0, '')
        message.insert(1, self.api('plugins.core.commands:get.command.format')(self.plugin_id, self.name))
        message.insert(2, '@G' + '-' * line_length + '@w')
        message.append('@G' + '-' * line_length + '@w')
        message.append('')
        return message

    def __call__(self, *args, **kwargs):
        self.count += 1
        return self.function(*args, **kwargs)

    def __repr__(self) -> str:
        return f"Command({self.name}, {self.plugin_id}, {self.function})"
    __str__ = __repr__
