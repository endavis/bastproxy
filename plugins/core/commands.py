# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/commands.py
#
# File Description: a plugin that is the command interpreter for clients
#
# By: Bast
"""
This module handles commands and parsing input

All commands are #bp.[package].[plugin].[command] or #bp.[plugin].[command]

Commands are stored in a dictionary in the source plugin, use #bp.<plugin>.inspect -o data:commands -s
    to find what's in the dictionary
$cmd{'#bp.client.actions.inspect -o data.commands -s'}
"""

# Standard Library
from __future__ import print_function
import contextlib
import shlex
import typing
import textwrap as _textwrap
from functools import lru_cache

# 3rd Party

# Project
from libs.api import API
from plugins._baseplugin import BasePlugin
from libs.persistentdict import PersistentDict
from libs.records import ToClientRecord, LogRecord, ToMudRecord
import libs.argp as argp
from libs.records import EventArgsRecord

NAME = 'Commands'
SNAME = 'commands'
PURPOSE = 'Parse and handle commands'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

@lru_cache(maxsize=10)
def get_plugin_permutations(plugin_list):
    # create a list of all possible combinations of the plugin name
    package_list : list[str] = []
    new_plugin_list: list[str] = []
    for plugin in plugin_list:
        # a plugin is of the form 'plugins'.package.name
        new_plugin_list.append(plugin)
        parts_list = plugin.split('.')
        # add the 'plugins' + package
        package_list.append('.'.join([parts_list[0], parts_list[1]]))
    # remove duplicates
    new_plugin_list = list(set(new_plugin_list))
    package_list = list(set(package_list))

    return new_plugin_list, package_list

# this class creates a custom formatter for help text to wrap at 73 characters
# and it adds what the default value for an argument is if set
class CustomFormatter(argp.HelpFormatter):
    """
    custom formatter for argparser for commands
    """
    # override _fill_text
    def _fill_text(self, text, width, indent):
        """
        change the help text wrap at 73 characters

        arguments:
          required:
            text   - a string of items, newlines can be included
            width  - the width of the text to wrap, not used
            indent - the indent for each line after first, not used

        returns:
          returns a string of lines separated by newlines
        """
        text = _textwrap.dedent(text)
        lines = text.split('\n')
        multiline_text = ''
        for line in lines:
            wrapped_line = _textwrap.fill(line, 73)
            multiline_text = multiline_text + '\n' + wrapped_line
        return multiline_text

    # override _get_help_string
    def _get_help_string(self, action):
        """
        get the help string for an action, which maps to an argument for a command

        arguments:
          required:
            action  - the action to get the help for

        returns:
          returns a formatted help string
        """
        temp_help: str | None = action.help
        # add the default value to the argument help
        if (
            action.help
            and temp_help
            and '%(default)' not in action.help
            and action.default is not argp.SUPPRESS
        ):
            defaulting_nargs = [argp.OPTIONAL, argp.ZERO_OR_MORE]
            if (
                action.option_strings or action.nargs in defaulting_nargs
            ) and action.default != '':
                temp_help += ' (default: %(default)s)'

        return temp_help

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
        self.full_cmd = f"{plugin_id.replace('.plugins', '')}.{name}"
        self.short_help = shelp
        self.count = 0

    def run(self, arg_string: str = '', toclient=True) -> tuple[bool | None, list[str], str]:
        """
        run the command
        """
        cmd_prefix = self.api(f"{__name__}:setting:get")('cmdprefix')
        command_ran = f"{cmd_prefix}.{self.plugin_id}.{self.name} {arg_string}"
        LogRecord(f"running {command_ran}",
                  level='debug', sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:run_command:command_ran")

        success, args, fail_message = self.parse_args(arg_string)

        if not success and toclient:
            ToClientRecord(self.format_return_message(fail_message)).send(actor = f"{self.plugin_id}:run:parse_args")

        args = vars(args)
        if args['help']:
            actor = f"{self.plugin_id}:run_command:help"
            message = self.arg_parser.format_help().split('\n')
            if toclient:
                ToClientRecord(self.format_return_message(message)).send(actor)
            return True, message, 'help'

        # run the command
        try:
            return_value = self(args)
        except Exception as exc:
            actor = f"{self.plugin_id}:run_command:command_exception"
            message = [f"Error running command: {command_ran}"]
            if toclient:
                ToClientRecord(self.format_return_message(message)).send(actor)
            LogRecord(f"Error running command: {command_ran}",
                        level='error', sources=[self.plugin_id, __name__], exc_info=True).send(actor)
            return False, message, 'Command exception'

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
            if toclient:
                ToClientRecord(self.format_return_message(message)).send(actor)

            return False, message, 'function returned False'

        if (not self.format) and message:
            actor = f"{self.plugin_id}:run_command:success_format_False"
            ToClientRecord(message, preamble=self.preamble).send(actor)
        # if the format flag is set, then format the data to the client
        elif message:
            actor = f"{self.plugin_id}:run_command:success_format_True"
            if toclient:
                ToClientRecord(self.format_return_message(message)).send(actor)

        return True, message, 'command ran successfully'

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
                fail_message = ['Error: Could not parse arguments', exc.args[0]]
                LogRecord(f"Error parsing args for command {self.plugin_id}.{self.name} {arg_string} - {exc.args[0]}",
                        level='error', sources=[self.plugin_id, __name__]).send(actor)
                return False, args, fail_message

        # parse the arguments and deal with errors
        try:
            args, _ = self.arg_parser.parse_known_args(split_args_list)
        except argp.ArgumentError as exc:
            actor = f"{self.plugin_id}:{self.name}:run_command:argparse_error"
            fail_message = [f"Error: {exc.message}"]
            fail_message.extend(self.arg_parser.format_help().split('\n'))
            LogRecord(f"Error parsing args for command {self.plugin_id}.{self.name} {arg_string} - {exc.message}",
                    level='error', sources=[self.plugin_id, __name__]).send()
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
        #line_length = self.api('net.proxy:setting:get')('linelen')
        line_length = 80

        cmdprefix = self.api(f"{__name__}:setting:get")('cmdprefix')

        message.insert(0, '')
        message.insert(1, f"{cmdprefix}.{self.plugin_id}.{self.name}")
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

class Plugin(BasePlugin):
    """
    a class to manage internal commands
    """
    def __init__(self, *args, **kwargs):
        """
        init the class
        """
        super().__init__(*args, **kwargs)

        # a list of commands, such as 'core.msg.set' or 'clients.ssub.list'
        self.commands_list: list[str] = []

        # a list of commands that should not be run again if already in the queue
        self.no_multiple_commands = {}

        # the default command to run if no command is specified
        self.default_help_command = {'plugin_id': 'plugins.core.pluginm',
                                     'command': 'list'}

        # load the history
        self.history_save_file = self.save_directory / 'history.txt'
        self.command_history_dict = PersistentDict(self.plugin_id, self.history_save_file, 'c')
        if 'history' not in self.command_history_dict:
            self.command_history_dict['history'] = []
        self.command_history_data = self.command_history_dict['history']

        # add apis
        #self.api('libs.api:add')('default', self.api_setdefault)
        self.api('libs.api:add')('command:add', self._api_add_command)
        self.api('libs.api:add')('command:run', self._api_run)
        self.api('libs.api:add')('command:help:format', self._api_get_plugin_command_help)
        self.api('libs.api:add')('get:command:prefix', self._api_get_prefix)
        self.api('libs.api:add')('remove:data:for:plugin', self._api_remove_plugin_data)
        self.api('libs.api:add')('get:commands:for:plugin:formatted', self._api_get_plugin_command_format)
        self.api('libs.api:add')('get:commands:for:plugin:data', self._api_get_plugin_command_data)

        # initialize settings
        self.api('setting:add')('cmdprefix', '#bp', str,
                                'the prefix to signify the input is a command')
        self.api('setting:add')('spamcount', 20, int,
                                'the # of times a command can ' \
                                 'be run before an antispam command')
        self.api('setting:add')('antispamcommand', 'look', str,
                                'the antispam command to send')
        self.api('setting:add')('cmdcount', 0, int,
                                'the # of times the current command has been run',
                                readonly=True)
        self.api('setting:add')('lastcmd', '', str,
                                'the last command that was sent to the mud',
                                readonly=True)
        self.api('setting:add')('historysize', 50, int,
                                'the size of the history to keep')

        self.dependencies = ['core.events', 'core.msg', 'core.errors', 'core.fuzzy']

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        # add commands
        parser = argp.ArgumentParser(add_help=False,
                                     description='list commands in a plugin')
        parser.add_argument('plugin',
                            help='the plugin to see help for',
                            default='',
                            nargs='?')
        parser.add_argument('command',
                            help='the command in the plugin (can be left out)',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('list',
                                              self.command_list,
                                              shelp='list commands',
                                              parser=parser,
                                              show_in_history=False)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list the command history')
        parser.add_argument('-c',
                            '--clear',
                            help="clear the history",
                            action='store_true')
        self.api('plugins.core.commands:command:add')('history',
                                              self.command_history,
                                              shelp='list or run a command in history',
                                              parser=parser,
                                              show_in_history=False)

        parser = argp.ArgumentParser(add_help=False,
                                     description='run a command in history')
        parser.add_argument('number',
                            help='the history # to run',
                            default=-1,
                            nargs='?',
                            type=int)
        self.api('plugins.core.commands:command:add')('!',
                                              self.command_runhistory,
                                              shelp='run a command in history',
                                              parser=parser,
                                              preamble=False,
                                              format=False,
                                              show_in_history=False)

        # register events
        self.api('plugins.core.events:register:to:event')('ev_to_mud_data_modify', self._event_to_mud_data_modify_check_command, prio=5)
        self.api('plugins.core.events:register:to:event')('ev_plugins.core.pluginm_plugin_uninitialized', self._event_plugin_uninitialized)
        self.api('plugins.core.events:register:to:event')(f"ev_{self.plugin_id}_savestate", self._savestate)

    def _event_plugin_uninitialized(self, args):
        """
        a plugin was uninitialized

        registered to the plugin_uninitialized event
        """
        LogRecord(f"removing commands for plugin {args['plugin_id']}",
                  level='debug', sources=[self.plugin_id, args['plugin_id']])
        self.api(f"{self.plugin_id}:remove:data:for:plugin")(args['plugin_id'])

    # remove all commands for a plugin
    def _api_remove_plugin_data(self, plugin_id):
        """  remove all command data for a plugin
        @Yplugin@w    = the plugin to remove commands for

        this function returns no values"""

        if self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            # remove commands from command_list that start with plugin_instance.plugin_id
            new_commands = [command for command in self.commands_list if not command.startswith(plugin_id)]
            self.commands_list = new_commands

    # return the command prefix setting
    def _api_get_prefix(self):
        """  get the current command prefix

        returns the current command prefix as a string"""
        return self.api('setting:get')('cmdprefix')

    # return the help for a command
    def _api_get_plugin_command_help(self, plugin_id, command_name):
        """  get the help for a command
        @Yplugin@w        = the plugin the command is in
        @Ycommand_name@w  = the command name

        returns the help message as a string"""
        # get the command data for the plugin

        if self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            if command_data := self.get_command_data_from_plugin(
                plugin_id, command_name
            ):
                return command_data.arg_parser.format_help()

        return ''

    # return a formatted list of commands for a plugin
    def _api_get_plugin_command_format(self, plugin_id):
        """  get a list of commands for the specified plugin
        @Yplugin@w   = the plugin the command is in

        returns a list of strings formatted for the commands in the plugin
        """
        if self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            return self.list_commands(plugin_id)

        return None

    # return the raw command data for a plugin
    def _api_get_plugin_command_data(self, plugin_id):
        """  get the data for commands for the specified plugin
        @Yplugin@w   = the plugin the command is in

        returns a dictionary of commands
        """
        if self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            return self.api(f"{plugin_id}:data:get")('commands')

        return {}

    # run a command and return the output
    def _api_run(self, plugin_id: str, command_name: str, argument_string: str = '') -> tuple[bool | None, list[str]]:
        """  run a command and return the output
        @Yplugin_id@w          = the plugin_id the command is in
        @Ycommand_name@w    = the command name
        @Yargument_string@w = the string of parameters for the command

        returns a tuple
          first item:
            True if the command was successful
            False if the command was not successful
            None if the command was not found
          second item:
            a list of strings for the output of the command
        """
        LogRecord(f"running command {command_name} from plugin {plugin_id} with arguments {argument_string}",
                  level='debug', sources=[self.plugin_id, plugin_id]).send(actor = f"{self.plugin_id}:run_command:command_ran")
        if command := self.get_command_data_from_plugin(plugin_id, command_name):
            success, message, _ = command.run(argument_string, toclient=False)
            return success, message

        return None, []

    def add_command_to_history(self, event_data):
        """
        add to the command history

        arguments:
          required:
            data      - the stack data

          optional:
            command   - the data in the input stack

        returns:
          True if succcessful, False if not successful
        """

        tdat = event_data['line']

        # remove existing
        if tdat in self.command_history_data:
            self.command_history_data.remove(tdat)

        # append the command
        self.command_history_data.append(tdat)

        # if the size is greater than historysize, pop the first item
        if len(self.command_history_data) >= self.api('setting:get')('historysize'):
            self.command_history_data.pop(0)

        # sync command history
        self.command_history_dict.sync()

    # return a list of all commands known
    def api_get_all_commands_list(self):
        """
        return a list of all commands

        returns a list of commands
        """
        return self.commands_list

    # retrieve a command from a plugin
    def get_command_data_from_plugin(self, plugin_id, command) -> Command | None:
        """
        get the command from the plugin data

        arguments:
          required:
            plugin_id  - the plugin_id
            command    - the command to retrieve

        returns:
          None if not found, the command data dict if found
        """
        # find the instance
        if self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            if data := self.api(f"{plugin_id}:data:get")('commands'):
                # return the command
                return data[command] if command in data else None

        return None

    # update a command
    def update_command(self, plugin_id, command_name, command: Command):
        """
        update a command

        arguments:
          required:
            plugin         - the plugin that the command is in
            command_name   - the command name
            data           - the new command data dict

        returns:
          True if succcessful, False if not successful
        """
        if not self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            LogRecord(f"commands - update_command: plugin {plugin_id} does not exist",
                      level='debug', sources=[plugin_id, self.plugin_id]).send(f"{self.plugin_id}:update_command")
            return False

        all_command_data = self.api(f"{plugin_id}:data:get")('commands')

        if not all_command_data:
            all_command_data = {}

        if command_name not in all_command_data and not self.api.startup:
            LogRecord(f"commands - update_command: plugin {plugin_id} does not have command {command_name}",
                      level='debug', sources=[plugin_id, self.plugin_id]).send()

        all_command_data[command_name] = command

        return self.api(f"{plugin_id}:data:update")('commands', all_command_data)

    def pass_through_command(self, event_data) -> EventArgsRecord:
        """
        pass through data to the mud

        this assumes the command is not a #bp command

        arguments:
          required:
            event_data - the data from the to_mud event

        returns the updated event
        """
        original_command = event_data['line']

        # if the command is the same as the last command, do antispam checks
        if original_command == self.api('setting:get')('lastcmd'):
            self.api('setting:change')('cmdcount',
                                       self.api('setting:get')('cmdcount') + 1)

            # if the command has been sent spamcount times, then we send an antispam
            # command in between
            if self.api('setting:get')('cmdcount') == \
                                  self.api('setting:get')('spamcount'):

                event_data.addupdate('Modify', "Antispam Command sent",
                                        f"{self.plugin_id}:pass_through_command", saveargs = False)
                LogRecord(f"sending antspam command: {self.api('setting:get')('antispamcommand')}", level='debug', sources=[self.plugin_id]).send()
                ToMudRecord(self.api('setting:get')('antispamcommand'), show_in_history=False).send(f"{self.plugin_id}:pass_through_command")

                self.api('setting:change')('cmdcount', 0)
                return event_data

            # if the command is seen multiple times in a row and it has been flagged to only be sent once,
            # swallow it
            if original_command in self.no_multiple_commands:
                event_data.addupdate('Modify', 'this command has been flagged to only be sent once, sendtomud set to False',
                                        f"{self.plugin_id}:pass_through_command", saveargs = False)

                event_data['sendtomud'] = False
                return event_data
        else:
            # the command does not match the last command
            self.api('setting:change')('cmdcount', 0)
            LogRecord(f"resetting command to {original_command}", level='debug', sources=[self.plugin_id]).send()
            self.api('setting:change')('lastcmd', original_command)

        return event_data

    def proxy_help(self, header, header2, data):
        """
        print the proxy help

        arguments:
          required:
            header  - the header to print
            data    - the data to print

        returns the data
        """
        newoutput = [
            f"{header}",
            "".join(["@B", '-' * 79]),
            "To send a command to the proxy, prefix it with a #bp",
            "commands are not required to start with 'plugins'",
            "however, they must include the package",
            "The proxy will do its best to find the correct command",
            "Valid:     #bp.core.proxy.info -h",
            "           #bp.core.proxy",
            "           #bp.core",
            "Not Valid: #bp.proxy.info -h",
            "           #bp.proxy",
            "".join(["@B", '-' * 79]),
        ]
        if header2:
            newoutput.extend(("".join(["@B", f"{header2}"]), "".join(["@B", '-' * 79])))
        newoutput.extend(data)

        ToClientRecord(newoutput).send()

    def match_item(self, item: str, item_list: list[str]) -> str:
        """
        match an item to a list of items
        """
        # see if the item explicity matches an item in the list
        if f"{item}" in item_list:
            # found the item
            LogRecord(f"match_item: found {item}",
                  level='debug',
                  sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:run_command:command_ran")
            return item

        # see if the item fuzzy matches an item in the list
        return self.api('plugins.core.fuzzy:get:best:match')(item, item_list,
                                                                scorer='token_set_ratio')

    def find_command(self, event_data: EventArgsRecord) -> tuple[Command | None, str, bool, str]:
        """
        find a command from the client
        """
        LogRecord(f"find_command: {event_data['line']}",
                  level='debug',
                  sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:find_command")

        # don't send it to the mud
        event_data['sendtomud'] = False

        # copy the command
        command = event_data['line']

        commandprefix = self.api('setting:get')('cmdprefix')
        command_str = command

        if command_str in [commandprefix, f"{commandprefix}.",
                            f"{commandprefix}.plugins", f"{commandprefix}.plugins."]:

            # found just the command prefix
            # get the list of plugins
            packages_list = [package.replace('plugins.', '')
                             for package in self.api('plugins.core.pluginm:get:packages:list')()]

            self.proxy_help("Proxy Help", "Available Packages:", packages_list)

            return None, '', False, 'Proxy Help'

        else:
            # split the string into the command and the command_args
            cmd_args_split = command_str.rsplit(' ', 1)
            command_str = cmd_args_split[0]
            command_args = ''
            if len(cmd_args_split) > 1:
                command_args = cmd_args_split[1]


            LogRecord(f"looking for {command}, {command_str}, {command_args}",
                  level='debug',
                  sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:find_command")

            # split the command by the '.'
            command_split = command_str.split('.')
            LogRecord(f"{command_split=}",
                  level='debug',
                  sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:find_command")

            # remove the command prefix
            if commandprefix in command_split:
                del command_split[command_split.index(commandprefix)]

            # remove the literal 'plugins' string
            if 'plugins' in command_split:
                del command_split[command_split.index('plugins')]

            # get all the pieces of the command
            temp_package = command_split[0]
            LogRecord(f"{temp_package=}",
                  level='debug', sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:find_command")
            temp_plugin = ''
            temp_command = ''

            if len(command_split) > 1:
                temp_plugin = command_split[1]
            if len(command_split) > 2:
                temp_command = command_split[2]

            plugins_list = self.api('plugins.core.pluginm:get:loaded:plugins:list')()

            # the tuple is so that the function works with the lru_cache decorator
            all_plugin_list, package_list = get_plugin_permutations(tuple(plugins_list))

            # try and find the package
            new_package = self.match_item(f"plugins.{temp_package}", package_list)
            if not new_package:
                # did not get a package, so output the list of packages
                output = [
                            "Could not find a matching package",
                            "".join(["@B", '-' * 79]),
                            "Available Packages",
                            "".join(["@B", '-' * 79])
                        ]
                for match in package_list:
                    output.append(match.replace('plugins.', ''))
                output.append("".join(["@B", '-' * 79]))

                self.proxy_help("Proxy Help", f"Unknown command: {command_str}", output)

                return None, '', False, 'Could not find package'

            # try and find the plugin
            new_plugin = self.match_item(f"{new_package}.{temp_plugin}", all_plugin_list)
            LogRecord(f"{new_plugin=}",
                  level='debug', sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:find_command")

            if not new_plugin:
                # did not get a plugin, so output the list of plugins in the package
                success, cmd_output = self.api(f"{self.plugin_id}:command:run")('plugins.core.commands',
                                                                            'list', new_package)

                output = [
                            "Could not find a matching plugin",
                            "".join(["@B", '-' * 79]),
                            f"Available Plugins in {new_package}",
                            "".join(["@B", '-' * 79])
                        ]
                if success:
                    for match in cmd_output:
                        output.append(match.replace('plugins.', ''))
                output.append("".join(["@B", '-' * 79]))

                self.proxy_help("Proxy Help", f"Unknown command: {command_str}", output)

                return None, '', False, 'Could not find plugin'


            # try and find the command
            command_data = self._api_get_plugin_command_data(new_plugin)
            command_list = list(command_data.keys())
            LogRecord(f"{command_list=}",
                  level='debug', sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:find_command")
            LogRecord(f"{temp_command=}",
                  level='debug', sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:find_command")

            new_command = self.match_item(temp_command, command_list)

            if not new_command:
                # did not get a command, so output the list of commands in the plugin
                success, cmd_output = self.api(f"{self.plugin_id}:command:run")('plugins.core.commands',
                                                                            'list', new_plugin)

                output = [
                            "Could not find a matching command",
                            "".join(["@B", '-' * 79]),
                            f"Available Commands in {new_plugin}",
                            "".join(["@B", '-' * 79])
                        ]
                if success:
                    for match in cmd_output:
                        output.append(match.replace('plugins.', ''))
                output.append("".join(["@B", '-' * 79]))

                self.proxy_help("Proxy Help", f"Unknown command: {command_str}", output)

                return None, '', False, 'Could not find command'

            # got it all
            command_item = command_data[new_command]

            return command_item, command_args, True, f'found {new_command}'

    def _event_to_mud_data_modify_check_command(self, event_data: EventArgsRecord) -> EventArgsRecord:
        """
        Check if the line is a command from the client
        if it is, the command is parsed and executed
        and the output sent to the client
        """
        commandprefix = self.api('setting:get')('cmdprefix')

        if event_data['line'].startswith(commandprefix):

                command_item, command_args, show_in_history, notes = self.find_command(event_data)

                if event_data['showinhistory'] != show_in_history:
                    event_data['showinhistory'] = show_in_history
                    event_data.addupdate('Modify', "show_in_history set to {show_in_history}",
                                        f"{self.plugin_id}:_event_mud_data_modify_check_command:find_command", saveargs = False)

                event_data.addupdate('Info', f"find_command returned {notes}",
                                     f"{self.plugin_id}:_event_mud_data_modify_check_command:find_command",
                                     saveargs = False)

                if command_item:
                    LogRecord(f"found command {command_item.plugin_id}.{command_item.name}",
                            level='debug', sources=[self.plugin_id]).send(actor = f"{self.plugin_id}:_event_to_mud_data_modify_check_command")
                    ToClientRecord(f"Running command {command_item.plugin_id}.{command_item.name}").send()

                    success, _, error = command_item.run(command_args)

                    if not success:
                        ToClientRecord(f"Error running command: {error}").send()

        else:
            self.pass_through_command(event_data)

        if event_data['showinhistory'] and not event_data['internal']:
            self.add_command_to_history(event_data)

        return event_data

    # add a command
    def _api_add_command(self, command_name, func, **kwargs):
        """  add a command
        @Ycommand_name@w  = the base that the api should be under
        @Yfunc@w   = the function that should be run when this command is executed
        @Ykeyword arguments@w
          @Yshelp@w        = the short help, a brief description of what the
                                  command does
          @Ylhelp@w        = a longer description of what the command does
          @Ypreamble@w     = show the preamble for this command (default: True)
          @Yformat@w       = format this command (default: True)
          @Ygroup@w        = the group this command is in
          @Yparser@w       = the parser for the argument
          @Yplugin_id@w    = the plugin_id of the plugin that this command will be
                                  added under

        The command will be added and can be called as package.plugin_id.command
            Example: core.clients.list

        plugin_id is retrieved from the class the function belongs to or the
            plugin_id key in the keyword args

        this function returns no values"""

        args = kwargs.copy()

        called_from = self.api('libs.api:get:caller:owner')()

        # passed an empty function
        if not func:
            LogRecord(f"_api_add_command: add command for command {command_name} was passed a null function from {called_from}, not adding",
                      level='error', sources=[self.plugin_id, called_from]).send()
            return

        # find the plugin_id
        if 'plugin_id' in args:
            plugin_id = args['plugin_id']
            del args['plugin_id']
        else:
            plugin_id = self.api('libs.api:get:function:owner:plugin')(func)


        if not self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            plugin_id = called_from

        if not self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            LogRecord(f"Function is not part of a plugin class: command {command_name} from plugin {called_from}",
                        level='error', sources=[self.plugin_id, called_from], stack_info=True).send()
            return

        # add custom formatter to the parser passed in
        if 'parser' in args:
            new_parser = args['parser']
            new_parser.formatter_class = CustomFormatter

        # use default parser if none passed in
        else:
            LogRecord(f"adding default parser to command {plugin_id}.{command_name}",
                      level='debug', sources=[self.plugin_id, plugin_id]).send()
            if 'shelp' not in args:
                args['shelp'] = 'there is no help for this command'
            new_parser = argp.ArgumentParser(add_help=False,
                                             description=args['shelp'])
            args['parser'] = new_parser

        with contextlib.suppress(argp.ArgumentError):
            new_parser.add_argument('-h', '--help', help='show help',
                                    action='store_true')
        new_parser.prog = f"@B{self.api('setting:get')('cmdprefix')}.{plugin_id}.{command_name}@w"

        # if no group, add the group as the plugin_name
        if 'group' not in args:
            args['group'] = plugin_id

        # build the command dict
        if 'preamble' not in args:
            args['preamble'] = True
        if 'format' not in args:
            args['format'] = True
        if 'show_in_history' not in args:
            args['show_in_history'] = True

        parser = args['parser']

        del args['parser']

        command = Command(plugin_id,
                            command_name,
                            func,
                            parser,
                            **args)
        #pprint.pprint(args)
        # update the command
        self.update_command(plugin_id, command_name, command)

        self.commands_list.append(f"{plugin_id}.{command_name}")

        LogRecord(f"added command {plugin_id}.{command_name}",
                  level='debug', sources=[self.plugin_id, plugin_id]).send()

    # remove a command
    def _api_remove_command(self, plugin_id, command_name):
        """  remove a command
        @Yplugin@w        = the top level of the command
        @Ycommand_name@w  = the name of the command

        this function returns no values"""
        if not self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            LogRecord(f"remove command: plugin {plugin_id} does not exist",
                      level='warning', sources=[self.plugin_id, plugin_id]).send(f"{self.plugin_id}:_api_remove_command")
            return False

        data = self.api(f"{plugin_id}:data:get")('commands')
        if data and command_name in data:
            del data[command_name]
            self.api(f"{plugin_id}:data:update")('commands', data)
            LogRecord(f"removed command {plugin_id}.{command_name}", level='debug', sources=[self.plugin_id, plugin_id]).send()
            return True

        LogRecord(f"remove command: command {plugin_id}.{command_name} does not exist", level='error', sources=[self.plugin_id, plugin_id]).send()
        return False

    def format_command_list(self, command_list: list[Command]):
        """
        format a list of commands by a category

        arguments:
          required:
            command_list    - the list of commands to format

        returns the a list of stings for the commands
        """
        message = []
        for i in command_list:
            if i != 'default' and i.arg_parser.description:
                    tlist = i.arg_parser.description.split('\n')
                    if not tlist[0]:
                        tlist.pop(0)
                    message.append(f"  @B{i.name:<10}@w : {tlist[0]}")

        return message

    def list_commands(self, plugin_id):
        """
        build a table of commands for a plugin

        arguments:
          required:
            plugin    - the plugin to build the commands from

        returns the a list of stings for the list of commands
        """

        if not self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            return []

        commands: dict[str, Command] = self.api(f"{plugin_id}:data:get")('commands')
        message = [f"Commands in {plugin_id}:", '@G' + '-' * 60 + '@w']
        groups = {}
        for i in sorted(commands.keys()):
            if i != 'default':
                if commands[i].group not in groups:
                    groups[commands[i].group] = []

                groups[commands[i].group].append(commands[i])

        for group in sorted(groups.keys()):
            if group != 'Base':
                message.append('@M' + '-' * 5 + ' ' +  group + ' ' + '-' * 5)
                message.extend(self.format_command_list(groups[group]))
                message.append('')

        message.append('@M' + '-' * 5 + ' ' +  'Base' + ' ' + '-' * 5)
        message.extend(self.format_command_list(groups['Base']))
        #message.append('@G' + '-' * 60 + '@w')

        return message

    def command_list(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list commands

          @CUsage@w: @B%(cmdname)s@w @Yplugin@w
            @Yplugin@w    = The plugin to list commands for (optional)
        """
        message = []
        command = args['command']
        plugin_id = args['plugin']
        if not self.api('plugins.core.pluginm:is:plugin:id')(plugin_id):
            message.append('Plugins')
            plugin_id_list = self.api('plugins.core.pluginm:get:loaded:plugins:list')()
            plugin_id_list = sorted(plugin_id_list)
            message.append(self.api('plugins.core.utils:format:list:into:columns')(plugin_id_list, cols=3, columnwise=False, gap=6))
            return True, message

        if plugin_commands := self.api(f"{plugin_id}:data:get")('commands'):
            if command and command in plugin_commands:
                help_message = plugin_commands[command]['parser'].format_help().split('\n')
                message.extend(help_message)
            else:
                message.extend(self.list_commands(plugin_id))
        else:
            message.append(f'There are no commands in plugin {plugin_id}')

        return True, message

    def command_runhistory(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          act on the command history

          @CUsage@w: @B%(cmdname)s@w @Ynumber@w
            @Ynumber@w    = The number of the command to rerun
        """
        if len(self.command_history_data) < abs(args['number']):
            return True, ['# is outside of history length']

        if len(self.command_history_data) >= self.api('setting:get')('historysize'):
            command = self.command_history_data[args['number'] - 1]
        else:
            command = self.command_history_data[args['number']]

        ToClientRecord(f"Commands: rerunning command {command}").send(
            f'{self.plugin_id}:command_runhistory'
        )
        ToClientRecord(command)

        return True, []

    def command_history(self, args):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list the command history

          @CUsage@w: @B%(cmdname)s@w
        """
        message = []

        if args['clear']:
            del self.command_history_dict['history'][:]
            self.command_history_dict.sync()
            message.append('Command history cleared')
        else:
            message.extend(
                f'{self.command_history_data.index(i)} : {i}'
                for i in self.command_history_data
            )
        return True, message

    def _savestate(self, _=None):
        """
        save states
        """
        self.command_history_dict.sync()
