# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/commands/plugin/_commands.py
#
# File Description: a plugin that is the command interpreter for clients
#
# By: Bast

# Standard Library
import types
import copy

# 3rd Party

# Project
from libs.api import AddAPI
from plugins._baseplugin import BasePlugin, RegisterPluginHook
from libs.persistentdict import PersistentDict
from libs.records import ToClientRecord, LogRecord, ToMudRecord
import libs.argp as argp
from plugins.core.commands import AddCommand, AddParser, AddArgument
from plugins.core.events import RegisterToEvent
from ..libs._command import CommandClass

class CommandsPlugin(BasePlugin):
    """
    a class to manage internal commands
    """
    @RegisterPluginHook('__init__')
    def _phook_init_plugin(self):
        """
        init the class
        """
        # a list of commands, such as 'core.msg.set' or 'clients.ssub.list'
        self.commands_list: list[str] = []

        # a dict of commands by plugin
        self.command_data: dict[str, dict[str, CommandClass]] = {}

        # a list of commands that should not be run again if already in the queue
        self.no_multiple_commands = {}

        # the default command to run if no command is specified
        self.default_help_command = {'plugin_id': 'plugins.core.pluginm',
                                     'command': 'list'}

        # load the history
        self.history_save_file = self.plugin_info.data_directory / 'history.txt'
        self.command_history_dict = PersistentDict(self.plugin_id, self.history_save_file, 'c')
        if 'history' not in self.command_history_dict:
            self.command_history_dict['history'] = []
        self.command_history_data = self.command_history_dict['history']

        self.current_command: CommandClass | None = None
        self.current_input_event: None = None

        self.attributes_to_save_on_reload = ['current_input_event']

    @RegisterPluginHook('initialize')
    def _phook_initialize(self):
        """
        initialize the instance
        """
        self.api('plugins.core.settings:add')(self.plugin_id, 'cmdprefix', '#bp', str,
                                'the prefix to signify the input is a command')
        self.api('plugins.core.settings:add')(self.plugin_id, 'spamcount', 20, int,
                                'the # of times a command can ' \
                                 'be run before an antispam command')
        self.api('plugins.core.settings:add')(self.plugin_id, 'antispamcommand', 'look', str,
                                'the antispam command to send')
        self.api('plugins.core.settings:add')(self.plugin_id, 'cmdcount', 0, int,
                                'the # of times the current command has been run',
                                readonly=True)
        self.api('plugins.core.settings:add')(self.plugin_id, 'lastcmd', '', str,
                                'the last command that was sent to the mud',
                                readonly=True)
        self.api('plugins.core.settings:add')(self.plugin_id, 'historysize', 50, int,
                                'the size of the history to keep')
        self.api('plugins.core.settings:add')(self.plugin_id, 'header_color', '@M', 'color',
                                'the color to use for the command headers')
        self.api('plugins.core.settings:add')(self.plugin_id, 'output_header_color', '@B', 'color',
                                'the color to use for the header in the output of a command')
        self.api('plugins.core.settings:add')(self.plugin_id, 'output_subheader_color', '@G', 'color',
                                'the color to use for a subheader in the output of a command')
        self.api('plugins.core.settings:add')(self.plugin_id, 'command_indent', 0, int,
                                'the indent for a command')
        self.api('plugins.core.settings:add')(self.plugin_id, 'simple_output', True, bool,
                                'show simple output for commands')
        self.api('plugins.core.settings:add')(self.plugin_id, 'multiline_headers', True, bool,
                                'headers are multiline')
        self.api('plugins.core.settings:add')(self.plugin_id, 'include_date', True, bool,
                                'include the date in the output of a command')

    @AddAPI('get.command.indent', description='indent for commands')
    def _api_get_command_indent(self):
        """
        return the command indent
        """
        return self.api('plugins.core.settings:get')(self.plugin_id, 'command_indent')

    @AddAPI('get.command.count', description='get a command count for a specific plugin')
    def _api_get_command_count(self, plugin_id):
        """
        get the command count for a specific plugin
        """
        return len(self.command_data[plugin_id]) if plugin_id in self.command_data else 0

    @AddAPI('get.output.indent', description='indent for command output')
    def _api_get_output_indent(self):
        """
        return the output indent
        """
        if self.api('plugins.core.settings:get')(self.plugin_id, 'simple_output'):
            return self.api('plugins.core.settings:get')(self.plugin_id, 'command_indent')

        return self.api('plugins.core.settings:get')(self.plugin_id, 'command_indent') * 2

    @AddAPI('format.output.header', description='format a header with the header color')
    def _api_format_output_header(self, header_text, line_length=None):
        """
        format an output header
        """
        if line_length is None:
            line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')
        color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')

        return self._format_output_header(header_text, color, line_length)

    @AddAPI('format.output.subheader', description='format a header with the subheader color')
    def _api_format_output_subheader(self, header_text, line_length=None):
        """
        format an output header
        """
        if line_length is None:
            line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')
        color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_subheader_color')

        return self._format_output_header(header_text, color, line_length)

    @AddAPI('format.header', description='format a header with the specified color')
    def _api_format_header(self, header_text, color, line_length=None):
        """
        format an output header
        """
        if line_length is None:
            line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')

        return self._format_output_header(header_text, color, line_length)

    def _format_output_header(self, header_text, color, line_length=None):
        """
        format an output header
        """
        if not line_length:
            line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')

        if not color:
            color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')

        if _ := self.api('plugins.core.settings:get')(
            'plugins.core.commands', 'multiline_headers'
        ):
            return [
                self.api('plugins.core.utils:cap.line')(f'{"-" * (line_length - 2)}', '+', color=color,
                                                        line_length=line_length, space=False, fullcolor=True),
                self.api('plugins.core.utils:center.colored.string')(
                    header_text, ' ', line_length, filler_color=color, endcaps=True
                ),
                self.api('plugins.core.utils:cap.line')(f'{"-" * (line_length - 2)}', '+', color=color,
                                                        line_length=line_length, space=False, fullcolor=True),
            ]
        else:
            return [
                *self.api('plugins.core.utils:center.colored.string')(
                    header_text, '-', line_length, filler_color=color
            ),
            ]

    @AddAPI('get.command.line.length', description='get line length for command')
    def _api_get_command_line_length(self):
        """
        return the line length for output
        """
        line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')
        command_indent = self.api(f"{self.plugin_id}:get.command.indent")()
        return line_length - 2 * command_indent

    @AddAPI('get.output.line.length', description='get line length for command output')
    def _api_get_output_line_length(self):
        """
        return the line length for output
        """
        line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')
        output_indent = self.api(f"{self.plugin_id}:get.output.indent")()
        return line_length - 2 * output_indent

    @RegisterToEvent(event_name='ev_baseplugin_patched')
    def _eventcb_commands_baseplugin_patched(self):
        """
        the base plugin was patched
        """
        LogRecord(
            "commands - _eventcb_commands_baseplugin_patched: baseplugin patched, adding commands",
            level='debug',
            sources=[self.plugin_id],
        )()
        self._add_commands_for_all_plugins()

    def _add_commands_for_all_plugins(self):
        """
        add commands for all loaded plugins
        """
        LogRecord('_eventcb_add_commands_on_startup: reload', level='debug',
                    sources=[self.plugin_id])()
        for plugin_id in self.api('libs.plugins.loader:get.loaded.plugins.list')():
            LogRecord(f"_eventdb_add_commands_on_startup: loading commands for {plugin_id}", level='debug',
                        sources=[self.plugin_id])()
            self.update_commands_for_plugin(plugin_id)
        LogRecord('_eventcb_add_commands_on_reload: Finish', level='debug',
                    sources=[self.plugin_id])()

    @RegisterToEvent(event_name='ev_plugin_loaded')
    def _eventcb_plugin_loaded(self):
        """
        handle the plugin loaded event
        """
        if not (event_record := self.api('plugins.core.events:get.current.event.record')()):
            return

        if not self.api.startup and event_record['plugin_id'] == self.plugin_id:
            self._add_commands_for_all_plugins()
        else:
            LogRecord(f"_eventcb_plugin_loaded: loading commands for {event_record['plugin_id']}", level='debug',
                        sources=[self.plugin_id])()
            self.update_commands_for_plugin(event_record['plugin_id'])


    def update_commands_for_plugin(self, plugin_id):
        """
        update all commands for a plugin
        """
        plugin_instance = self.api('libs.plugins.loader:get.plugin.instance')(plugin_id)
        command_functions = self.get_command_functions_in_object(plugin_instance)
        LogRecord(f"update_commands_for_plugin: {plugin_id} has {len(command_functions)} commands", level='debug',
                    sources=[self.plugin_id])()
        if command_functions:
            command_names = [command.__name__ for command in command_functions]
            LogRecord(f"{command_names = }", level='debug',
                        sources=[self.plugin_id])()
            for command in command_functions:
                self.api(f"{self.plugin_id}:add.command.by.func")(command)

    def get_command_functions_in_object(self, base, recurse=True):
        """
        recursively search for functions that are commands in a plugin instance
        and it's attributes
        """
        function_list = []
        for item in dir(base):
            if item.startswith('__'):
                continue
            try:
                item = getattr(base, item)
            except AttributeError:
                continue
            if isinstance(item, types.MethodType) and item.__name__.startswith('_command_') and hasattr(item, 'command_data'):
                function_list.append(item)
            elif recurse:
                function_list.extend(self.get_command_functions_in_object(item, recurse=False))

        return function_list

    @AddAPI('add.command.by.func', description='add a command based on a decorated function')
    def _api_add_command_by_func(self, func, force=False):
        """
        add a command based on the new decorator stuff
        """
        LogRecord(f"adding command from func {func.__name__}",
                  level='debug', sources=[self.plugin_id])()
        if hasattr(func, '__self__'):
            if hasattr(func.__self__, 'name'):
                msg = f"func is from plugin {func.__self__.plugin_id} with name {func.__self__.name}"
            else:
                msg = f"func is from plugin {func.__self__.plugin_id}"
            LogRecord(msg, level='debug', sources=[self.plugin_id])()
        plugin_id = None

        if not (isinstance(func, types.MethodType) and func.__name__.startswith('_command_') and hasattr(func, 'command_data')):
            LogRecord(f"Function is not a command: {func.__name__}",
                      level='warning', sources=[self.plugin_id])()
            return

        if hasattr(func, '__self__') and hasattr(func.__self__, 'plugin_id'):
            plugin_id = func.__self__.plugin_id # pyright: ignore reportGeneralTypeIssues
        else:
            LogRecord(f"Function does not have a plugin: {func.__name__}",
                        level='warning', sources=[self.plugin_id])()
            return

        command_data = copy.deepcopy(func.command_data) # pyright: ignore reportGeneralTypeIssues
        if not command_data.command['autoadd'] and not force:
            LogRecord(f"Command {func.__name__} in {plugin_id} will not be added, autoadd set to False",
                        level='debug', sources=[self.plugin_id])()
            return

        if 'name' in command_data.command:
            command_name = command_data.command['name'].format(**func.__self__.__dict__)
        else:
            command_name = func.__name__.replace('_command_', '')

        command_name = command_name.strip()

        if 'name' in command_data.command['kwargs']:
            del command_data.command['kwargs']['name']

        if 'description' in command_data.argparse['kwargs']:
            command_data.argparse['kwargs']['description'] = command_data.argparse['kwargs']['description'].format(**func.__self__.__dict__)

        parser = argp.ArgumentParser(**command_data.argparse['kwargs'])
        for arg in command_data.arguments:
            arg['kwargs']['help'] = arg['kwargs']['help'].format(**func.__self__.__dict__)
            parser.add_argument(*arg['args'], **arg['kwargs'])

        parser.add_argument('-h', '--help', help='show help',
                                action='store_true')
        parser.formatter_class = argp.CustomFormatter

        parser.prog = self.api('plugins.core.commands:get.command.format')(self.plugin_id, command_name)

        command_kwargs = copy.deepcopy(command_data.command['kwargs'])

        # if no group, add the group as the plugin_name
        if 'group' not in command_kwargs:
            command_kwargs['group'] = plugin_id

        # build the command dict
        if 'preamble' not in command_kwargs:
            command_kwargs['preamble'] = True
        if 'format' not in command_kwargs:
            command_kwargs['format'] = True
        if 'show_in_history' not in command_kwargs:
            command_kwargs['show_in_history'] = True

        try:
            command = CommandClass(plugin_id,
                                command_name,
                                func,
                                parser,
                                **command_kwargs)
        except Exception as e:
            LogRecord(f"Error creating command {func.__name__}: {command_kwargs}",
                        level='error', sources=[self.plugin_id], exc_info=True)()
            return

        self.update_command(plugin_id, command_name, command)

        self.commands_list.append(f"{plugin_id}.{command_name}")

        LogRecord(f"added command {plugin_id}.{command_name}",
                  level='debug', sources=[self.plugin_id, plugin_id])()

    @RegisterToEvent(event_name='ev_plugin_unloaded')
    def _eventcb_plugin_unloaded(self):
        """
        a plugin was unloaded

        registered to the plugin_unloaded event
        """
        if event_record := self.api(
            'plugins.core.events:get.current.event.record'
        )():
            if event_record['plugin_id'] != self.plugin_id:
                self.api(f"{self.plugin_id}:remove.data.for.plugin")(event_record['plugin_id'])
            else:
                LogRecord(f"{self.plugin_id}_plugin_unloaded: {self.plugin_id} is me!", level='debug',
                            sources=[self.plugin_id])()

    @AddAPI('get.command.format', description='get a command string formatted for a plugin')
    def  _api_get_command_format(self, plugin_id, command):
        """
        return a command string formatted for the plugin

        EX: plugin_id: plugins.core.proxy
            command: info
            returns:
               #bp.core.proxy.info
        """
        return f"{self.api('plugins.core.commands:get.command.prefix')()}.{plugin_id.replace('plugins.','')}.{command}"

    @AddAPI('get.current.command.args', description='get the currently executing command args')
    def _api_get_current_command_args(self):
        """
        get the current command args
        """
        return self.current_command.current_args if self.current_command else {}

    @AddAPI('set.current.command', description='set the currently executing command')
    def _api_set_current_command(self, command):
        """
        set the current command
        """
        self.current_command = command

    @AddAPI('remove.data.for.plugin', description='remove all command data for a plugin')
    def _api_remove_data_for_plugin(self, plugin_id):
        """  remove all command data for a plugin
        @Yplugin@w    = the plugin to remove commands for

        this function returns no values"""
        LogRecord(f"removing commands for plugin {plugin_id}",
                        level='debug', sources=[self.plugin_id, plugin_id])()
        if self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            # remove commands from _command_list that start with plugin_instance.plugin_id
            new_commands = [command for command in self.commands_list if not command.startswith(plugin_id)]
            self.commands_list = new_commands

    @AddAPI('get.command.prefix', description='get the current command prefix')
    def _api_get_command_prefix(self):
        """  get the current command prefix

        returns the current command prefix as a string"""
        return self.api('plugins.core.settings:get')(self.plugin_id, 'cmdprefix')

    @AddAPI('command.help.format', description='format a help string for a command')
    def _api_command_help_format(self, plugin_id, command_name):
        """  get the help for a command
        @Yplugin@w        = the plugin the command is in
        @Ycommand_name@w  = the command name

        returns the help message as a string"""
        # get the command data for the plugin

        if self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            if command_data := self.get_command_data_from_plugin(
                plugin_id, command_name
            ):
                return command_data.arg_parser.format_help()

        return ''

    @AddAPI('get.commands.for.plugin.data', description='get the command data for a plugin')
    def _api_get_commands_for_plugin_data(self, plugin_id):
        """  get the data for commands for the specified plugin
        @Yplugin@w   = the plugin the command is in

        returns a dictionary of commands
        """
        if self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            return self.command_data[plugin_id]
        return {}

    @AddAPI('run', description='run a command and return the output')
    def _api_run(self, plugin_id: str, command_name: str, argument_string: str = '', format=False) -> tuple[bool | None, list[str]]:
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
                  level='debug', sources=[self.plugin_id, plugin_id])(actor = f"{self.plugin_id}:run_command:command_ran")
        if command := self.get_command_data_from_plugin(plugin_id, command_name):
            success, message, _ = command.run(argument_string, format)
            if not success:
                LogRecord(f"command {command_name} from plugin {plugin_id} failed with message {message}",
                            level='debug', sources=[self.plugin_id, plugin_id], stack_info=True)()
            return success, message

        LogRecord(f"command {command_name} from plugin {plugin_id} not found",
                    level='warning', sources=[self.plugin_id, plugin_id], stack_info=True)()
        return None, []

    def add_command_to_history(self, command: str):
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
        # remove existing
        if command in self.command_history_data:
            self.command_history_data.remove(command)

        # append the command
        self.command_history_data.append(command)

        # if the size is greater than historysize, pop the first item
        if len(self.command_history_data) >= self.api('plugins.core.settings:get')(self.plugin_id, 'historysize'):
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
    def get_command_data_from_plugin(self, plugin_id, command) -> CommandClass | None:
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
        if self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            if data := self.command_data[plugin_id]:
                # return the command
                return data[command] if command in data else None

        return None

    # update a command
    def update_command(self, plugin_id, command_name, command: CommandClass):
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
        if not self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            LogRecord(f"commands - update_command: plugin {plugin_id} does not exist",
                      level='debug', sources=[plugin_id, self.plugin_id])(f"{self.plugin_id}:update_command")
            return False

        if plugin_id not in self.command_data:
            self.command_data[plugin_id] = {}

        plugin_command_data = self.command_data[plugin_id]

        if command_name not in plugin_command_data and not self.api.startup:
            LogRecord(f"commands - update_command: plugin {plugin_id} does not have command {command_name}",
                      level='debug', sources=[plugin_id, self.plugin_id])()

        # update any items from the old command to the new command
        if command_name in plugin_command_data:
            command.count = plugin_command_data[command_name].count

        plugin_command_data[command_name] = command

        return True

    def pass_through_command_from_event(self) -> None:
        """
        pass through data to the mud

        this assumes the command is not a #bp command

        arguments:
          required:
            event_data - the data from the to_mud event

        returns the updated event
        """
        if not (
            event_record := self.api(
                'plugins.core.events:get.current.event.record'
            )()
        ):
            return

        original_command = event_record['line']

        # if the command is the same as the last command, do antispam checks
        if original_command == self.api('plugins.core.settings:get')(self.plugin_id, 'lastcmd'):
            self.api('plugins.core.settings:change')(self.plugin_id, 'cmdcount',
                                    self.api('plugins.core.settings:get')(self.plugin_id, 'cmdcount') + 1)

            # if the command has been sent spamcount times, then we send an antispam
            # command in between
            if self.api('plugins.core.settings:get')(self.plugin_id, 'cmdcount') == \
                                    self.api('plugins.core.settings:get')(self.plugin_id, 'spamcount'):

                event_record.addupdate('Modify', "Antispam Command sent",
                                        f"{self.plugin_id}:pass_through_command_from_event", savedata = False)
                LogRecord(f"sending antspam command: {self.api('plugins.core.settings:get')('plugins.core.commands', 'antispamcommand')}",
                          level='debug', sources=[self.plugin_id])()
                ToMudRecord(self.api('plugins.core.settings:get')(self.plugin_id, 'antispamcommand'),
                            show_in_history=False)(f"{self.plugin_id}:pass_through_command_event")

                self.api('plugins.core.settings:change')(self.plugin_id, 'cmdcount', 0)
                return

            # if the command is seen multiple times in a row and it has been flagged to only be sent once,
            # swallow it
            if original_command in self.no_multiple_commands:
                event_record.addupdate('Modify', 'this command has been flagged to only be sent once, sendtomud set to False',
                                        f"{self.plugin_id}:pass_through_command_from_event", savedata = False)

                event_record['sendtomud'] = False
                return
        else:
            # the command does not match the last command
            self.api('plugins.core.settings:change')(self.plugin_id, 'cmdcount', 0)
            LogRecord(f"resetting command to {original_command}", level='debug', sources=[self.plugin_id])()
            self.api('plugins.core.settings:change')(self.plugin_id, 'lastcmd', original_command)

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
            '',
            *self.api(f'{self.plugin_id}:format.output.header')(header),
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
            newoutput.extend(("".join(["@B", f"{header2}"]), "".join(["@B", '-' * 80])))
        newoutput.extend(data)
        newoutput.append('')

        return newoutput

    def error_command_not_found_in_plugin(self, plugin_id, command=None):
        """
        command not found in plugin
        """
        message = []
        if command:
            message = [
                self.api('plugins.core.utils:cap.line')(f'{"-" * (80 - 2)}', '+', color='@B',
                                                            line_length=80, space=False, fullcolor=True),
                self.api('plugins.core.utils:center.colored.string')(f'@RError - Plugin {plugin_id.replace("plugins.", "")} has no command{f" : {command}" if command else ""}@w',
                                                                 filler_character='-',
                                                                 length=80,
                                                                 filler_color='@B',
                                                                 endcaps=True),
            ]

        message.extend([
            *[line.replace('plugins.', '') for line in self.api(f'{self.plugin_id}:list.commands.formatted')(plugin_id)],
        ])

        return self.proxy_help("Proxy Help", "", message)

    def error_plugin_not_found(self, plugin_id=None, package=None):
        """
        plugin not found
        """
        message = []
        if plugin_id:
            message = [
                self.api('plugins.core.utils:cap.line')(f'{"-" * (80 - 2)}', '+', color='@B',
                                                            line_length=80, space=False, fullcolor=True),
                self.api('plugins.core.utils:center.colored.string')(f'@RError - Unknown plugin{f" : {plugin_id}" if plugin_id else ""}@w',
                                                                    filler_character='-',
                                                                    length=80,
                                                                    filler_color='@B',
                                                                    endcaps=True),
            ]

        plugins = [line.replace('plugins.', '') for line in self.api('libs.plugins.loader:get.plugins.in.package')(package)]

        message.extend([
            *self.api(f'{self.plugin_id}:format.output.header')(f'Available Plugins in {package}'),
            self.api('plugins.core.utils:format.list.into.columns')(
                    plugins, cols=3, columnwise=False, gap=6
                ),
        ])
        return self.proxy_help("Proxy Help", "", message)

    def error_package_not_found(self, package=None):
        """
        package not found
        """
        message = [
            self.api('plugins.core.utils:cap.line')(f'{"-" * (80 - 2)}', '+', color='@B',
                                                        line_length=80, space=False, fullcolor=True),
            self.api('plugins.core.utils:center.colored.string')(f'@RError - Unknown package{f" : {package}" if package else ""}@w',
                                                                 filler_character='-',
                                                                 length=80,
                                                                 filler_color='@B',
                                                                 endcaps=True),
            *self.api(f'{self.plugin_id}:format.output.header')('Available Packages'),
            *[line.replace('plugins.', '') for line in self.api('libs.plugins.loader:get.packages.list')(active_only=True)],
        ]
        return self.proxy_help("Proxy Help", "", message)

    def find_command_only_prefix(self):
        """
        found only the command_prefix
        """
        # found just the command prefix
        # get the list of packages
        message = [
            *self.api(f'{self.plugin_id}:format.output.header')('Available Packages'),
            *[line.replace('plugins.', '') for line in self.api('libs.plugins.loader:get.packages.list')(active_only=True)],
        ]
        return self.proxy_help("Proxy Help", "", message)

    def find_command(self, command_line: str) -> tuple[CommandClass | None, str, bool, str, list[str]]:
        """
        find a command from the client
        """
        message: list[str] = []
        LogRecord(f"find_command: {command_line}",
                  level='debug',
                  sources=[self.plugin_id])(actor = f"{self.plugin_id}find_command")

        # copy the command
        command = command_line

        commandprefix = self.api('plugins.core.settings:get')(self.plugin_id, 'cmdprefix')
        command_str = command

        if command_str in [commandprefix, f"{commandprefix}.",
                            f"{commandprefix}.plugins", f"{commandprefix}.plugins."]:

            return None, '', False, 'Proxy Help', self.find_command_only_prefix()

        # split the string into the command and the command_args
        found, new_package, new_plugin, tmessage, command_split, command_args = self.find_command_split_command_string(command_str)

        if not found:
            if tmessage == 'Bad Package':
                # did not get a package, so output the list of packages
                output =  self.error_package_not_found(command_split[0])
                return None, '', False, command_str, output
            elif tmessage == 'Bad Plugin':
                # did not get a plugin, so output the list of plugins in the package
                output =  self.error_plugin_not_found(command_split[1], new_package)
                return None, '', False, command_str, output

        LogRecord(f"{found} {new_package} {new_plugin} {tmessage}",
                level='debug',
                sources=[self.plugin_id])(actor = f"{self.plugin_id}:find_command")

        # get all the pieces of the command
        temp_package = command_split[0]
        LogRecord(f"{temp_package=}",
                level='debug', sources=[self.plugin_id])(actor = f"{self.plugin_id}:find_command")
        temp_command = command_split[2] if len(command_split) > 2 else ''
        # try and find the command
        command_data = self.api(f"{self.plugin_id}:get.commands.for.plugin.data")(new_plugin)
        command_list = list(command_data.keys())
        LogRecord(f"{command_list=}",
                level='debug', sources=[self.plugin_id])(actor = f"{self.plugin_id}:find_command")
        LogRecord(f"{temp_command=}",
                level='debug', sources=[self.plugin_id])(actor = f"{self.plugin_id}:find_command")

        new_command = self.api('plugins.core.fuzzy:get.best.match')(temp_command, tuple(command_list),
                                                            scorer='token_set_ratio')

        if not new_command:
            # did not get a command, so output the list of commands in the plugin
            output =  self.error_command_not_found_in_plugin(new_plugin, temp_command)
            return None, '', False, command_str, output

        # got it all
        command_item = command_data[new_command]

        return command_item, command_args, True, f'found {command_item.full_cmd}', message

    def find_command_split_command_string(self, command_str: str) -> tuple[bool, str, str, str, list, str]:
        """
        split a command string into its parts
        """
        commandprefix = self.api('plugins.core.settings:get')(self.plugin_id, 'cmdprefix')

        cmd_args_split = command_str.split(' ', 1)
        command_str = cmd_args_split[0]
        command_args = cmd_args_split[1] if len(cmd_args_split) > 1 else ''
        LogRecord(f"looking for {command_str}, {command_str}, {command_args}",
            level='debug',
            sources=[self.plugin_id])(actor = f"{self.plugin_id}:find_command")

        # split the command by the '.'
        command_split = command_str.split('.')
        LogRecord(f"{command_split=}",
            level='debug',
            sources=[self.plugin_id])(actor = f"{self.plugin_id}:find_command")

        # remove the command prefix
        if commandprefix in command_split:
            del command_split[command_split.index(commandprefix)]

        # remove the literal 'plugins' string
        if command_split[0] == 'plugins':
            del command_split[0]

        LogRecord(f"2: {command_split=}",
            level='debug',
            sources=[self.plugin_id])(actor = f"{self.plugin_id}:find_command")

        # make sure there are two items in the list
        if len(command_split) == 1:
            command_split.append('')

        plugin_id_temp_str = f"{command_split[0]}.{command_split[1]}"

        new_package, new_plugin = self.api('libs.plugins.loader:fuzzy.match.plugin.id')(plugin_id_temp_str, active_only=True)

        found = False
        tmessage = ''
        if new_package and new_plugin:
            found = True
        elif new_package:
            tmessage = 'Bad Plugin'
            found = False
        else:
            tmessage = 'Bad Package'
            found = False

        return found, new_package, new_plugin, tmessage, command_split, command_args

    def run_internal_command_from_event(self):
        """
        run the internal command from the client event
        """
        if not (
            event_record := self.api(
                'plugins.core.events:get.current.event.record'
            )()
        ):
            return
        clients = [event_record['client_id']] if event_record['client_id'] else None

        event_record['sendtomud'] = False

        command_item, command_args, show_in_history, notes, message = self.find_command(event_record['line'])

        if message:
            ToClientRecord(message, clients=clients)()

        if event_record['showinhistory'] != show_in_history:
            event_record['showinhistory'] = show_in_history
            event_record.addupdate('Modify', "show_in_history set to {show_in_history}",
                                f"{self.plugin_id}:_event_mud_data_modify_check_command:find_command", savedata = False)

        event_record.addupdate('Info', f"find_command returned {notes}, arg string: '{command_args}'",
                            f"{self.plugin_id}:_event_mud_data_modify_check_command:find_command",
                            savedata = False)

        if command_item:
            LogRecord(f"found command {command_item.plugin_id}.{command_item.name}",
                    level='debug', sources=[self.plugin_id])(actor = f"{self.plugin_id}:run_internal_command_from_event")
            #ToClientRecord(f"Running command {command_item.plugin_id}.{command_item.name}")()

            success, message, error = command_item.run(command_args, format=True)

            if success:
                event_record.addupdate(
                    'Info',
                    "run_command returned success",
                    f"{self.plugin_id}:_event_mud_data_modify_check_command:run_command",
                    savedata=False,
                )
            else:
                event_record.addupdate('Info', f"run_command returned error: {error}",
                                    f"{self.plugin_id}:_event_mud_data_modify_check_command:run_command",
                                    savedata = False)

            if message:
                ToClientRecord(message, clients=clients)()

    @AddAPI('get.summary.data.for.plugin', description="get summary data for a plugin")
    def _api_get_summary_data_for_plugin(self, plugin_id):
        """
        return stats for the plugin
        """
        msg = []

        if plugin_id == self.plugin_id:
            msg.extend(
                (
                    self.api('plugins.core.utils:center.colored.string')(
                        "Overall Command Data", '=', 80, filler_color='@G'
                    ),
                    f'Total Commands for all plugins : {len(self.commands_list)}',
                    '',
                    self.api('plugins.core.utils:center.colored.string')(
                        f"{self.plugin_id} specific data", '=', 80, filler_color='@G'
                    ),
                )
            )

        command_data = self.api(f"{self.plugin_id}:get.commands.for.plugin.data")(plugin_id)

        commands = [command.name for command in command_data.values()]

        command_str = "".join(f"{'':<26}{item}\n" for item in commands)

        count = len(commands)

        msg.extend([
            f"{f'{count} Commands':<23} : {command_str.strip()}",
        ])

        return msg

    @AddAPI('get.detailed.data.for.plugin', description='get detailed data for a plugin')
    def _api_get_detailed_data_for_plugin(self, plugin_id):
        """
        get detailed data for a plugin
        """
        command_data = self.api(f"{self.plugin_id}:get.commands.for.plugin.data")(plugin_id)

        if not command_data:
            return ['None']

        columns = [
            {'name': 'Command Name', 'key': 'name', 'width':20},
            {'name': 'Function', 'key': 'function_name', 'width':20},
        ]

        sorted_keys = sorted(command_data.keys())
        data = [
            {'name': command_data[command].name,
                'function_name': command_data[command].function.__name__}
            for command in sorted_keys
        ]

        count = len(data)

        return [
            *self.api('plugins.core.utils:convert.data.to.output.table')(
                f"{count} Commands for plugin: {plugin_id}", data, columns
            )
        ]

    @RegisterToEvent(event_name='ev_to_mud_data_modify')
    def _eventcb_check_for_command(self) -> None:
        """
        Check if the line is a command from the client
        if it is, the command is parsed and executed
        and the output sent to the client
        """
        commandprefix = self.api('plugins.core.settings:get')(self.plugin_id, 'cmdprefix')

        if not (event_record := self.api('plugins.core.events:get.current.event.record')()):
            return

        if self.current_input_event == event_record:
            LogRecord(f"current_input_event: {self.current_input_event} is being processed, skipping",
                    level='debug', sources=[self.plugin_id])()
            self.current_input_event = None
            return

        self.current_input_event = event_record

        if event_record['line'].startswith(commandprefix):
            self.run_internal_command_from_event()

        else:
            self.pass_through_command_from_event()

        if event_record['showinhistory'] and not event_record['internal']:
            self.add_command_to_history(event_record['line'])

        self.current_input_event = None

    # remove a command
    def _api_remove_command(self, plugin_id, command_name):
        """  remove a command
        @Yplugin@w        = the top level of the command
        @Ycommand_name@w  = the name of the command

        this function returns no values"""
        if not self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            LogRecord(f"remove command: plugin {plugin_id} does not exist",
                      level='warning', sources=[self.plugin_id, plugin_id])(f"{self.plugin_id}:_api_remove_command")
            return False

        data = self.command_data[plugin_id]
        if data and command_name in data:
            del data[command_name]
            self.api(f"{plugin_id}:data.update")('commands', data)
            LogRecord(f"removed command {plugin_id}.{command_name}", level='debug', sources=[self.plugin_id, plugin_id])()
            return True

        LogRecord(f"remove command: command {plugin_id}.{command_name} does not exist", level='error', sources=[self.plugin_id, plugin_id])()
        return False

    def format_command_list(self, command_list: list[CommandClass]):
        """
        format a list of commands by a category

        arguments:
          required:
            command_list    - the list of commands to format

        returns a list of stings for the commands
        """
        message = []
        output_header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')
        for i in command_list:
            if i != 'default' and i.arg_parser.description:
                    tlist = i.arg_parser.description.splitlines()
                    if not tlist[0]:
                        tlist.pop(0)
                    message.append(f"  {output_header_color}{i.name.replace('plugins.', ''):<10}@w : {tlist[0]}")

        return message

    @AddAPI('list.commands.formatted', description='return a formatted list of commands for a plugin')
    def _api_list_commands_formatted(self, plugin_id):
        """
        build a table of commands for a plugin

        arguments:
          required:
            plugin    - the plugin to build the commands from

        returns the a list of strings for the list of commands
        """
        if not self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            return []

        output_subheader_color = self.api('plugins.core.settings:get')(self.plugin_id, 'output_subheader_color')

        commands: dict[str, CommandClass] = self.command_data[plugin_id]

        message = self.api(f'{self.plugin_id}:format.output.header')(f'Available Commands in {plugin_id.replace("plugins.", "")}')

        groups = {}
        for i in sorted(commands.keys()):
            if i != 'default':
                if commands[i].group not in groups:
                    groups[commands[i].group] = []

                groups[commands[i].group].append(commands[i])

        if plugin_id in groups:
            message.append(output_subheader_color + '-' * 5 + ' ' +  plugin_id.replace('plugins.', '') + ' ' + '-' * 5 + '@w')
            message.extend(self.format_command_list(groups[plugin_id]))
            message.append('')

        for group in sorted(groups.keys()):
            if group not in ['Base', 'Debug/Info', plugin_id]:
                message.append(output_subheader_color + '-' * 5 + ' ' +  group.replace('plugins.', '') + ' ' + '-' * 5 + '@w')
                message.extend(self.format_command_list(groups[group]))
                message.append('')

        message.append(output_subheader_color + '-' * 5 + ' ' +  'Base' + ' ' + '-' * 5 + '@w')
        message.extend(self.format_command_list(groups['Base']))
        message.append('')

        return message

    @AddAPI('list.plugins.formatted', description='return a formatted list of all plugins')
    def _api_list_plugins_formatted(self, package=None):
        """
        list all plugins
        """
        if package:
            plugin_id_list = [item.replace('plugins.', '') for item in self.api('libs.plugins.loader:get.plugins.in.package')(package)]
        else:
            plugin_id_list = [item.replace('plugins.', '') for item in self.api('libs.plugins.loader:get.loaded.plugins.list')()]

        if plugin_id_list := sorted(plugin_id_list):
            return [
                self.api('plugins.core.utils:format.list.into.columns')(
                    plugin_id_list, cols=3, columnwise=False, gap=6
                ),
            ]
        else:
            return  ['No plugins found']

    @AddCommand(shelp='list commands', show_in_history=False)
    @AddParser(description='list commands in a plugin')
    @AddArgument('plugin',
                    help='the plugin to see help for',
                    default='',
                    nargs='?')
    @AddArgument('command',
                    help='the command in the plugin (not required)',
                    default='',
                    nargs='?')
    def _command_list(self, _=None):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list commands

          @CUsage@w: @B%(cmdname)s@w @Yplugin@w
            @Yplugin@w    = The plugin to list commands for (optional)
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

        message = []
        command = args['command']
        plugin_id = args['plugin']

        if not self.api('libs.plugins.loader:is.plugin.id')(plugin_id):
            return True, self.api(f'{self.plugin_id}:list.plugins.formatted')(package=plugin_id)

        if plugin_commands := self.command_data[plugin_id]:
            if command and command in plugin_commands:
                help_message = plugin_commands[command].arg_parser.format_help().splitlines()
                message.extend(help_message)
            else:
                message.extend(self.api(f'{self.plugin_id}:list.commands.formatted')(plugin_id))
        else:
            message.append(f'There are no commands in plugin {plugin_id}')

        return True, message

    @AddCommand(shelp='run a command in history', show_in_history=False,
                preamble=False, format=False, name="!")
    @AddParser(description='run a command in history')
    @AddArgument('number',
                    help='the history # to run',
                    default=-1,
                    nargs='?',
                    type=int)
    def _command_run_history(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          act on the command history

          @CUsage@w: @B%(cmdname)s@w @Ynumber@w
            @Ynumber@w    = The number of the command to rerun
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        if len(self.command_history_data) < abs(args['number']):
            return True, ['# is outside of history length']

        if len(self.command_history_data) >= self.api('plugins.core.settings:get')(self.plugin_id, 'historysize'):
            command = self.command_history_data[args['number'] - 1]
        else:
            command = self.command_history_data[args['number']]

        ToClientRecord(f"Commands: rerunning command {command}")(
            f'{self.plugin_id}:_command_run_history'
        )
        ToClientRecord(command)()

        return True, []

    @AddCommand(shelp='list or run a command in history',
                show_in_history=False)
    @AddParser(description='list the command history')
    @AddArgument('-c',
                    '--clear',
                    help='clear the history',
                    action='store_true')
    def _command_history(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          list the command history

          @CUsage@w: @B%(cmdname)s@w
        """
        args = self.api('plugins.core.commands:get.current.command.args')()

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

    @RegisterPluginHook('save')
    def _phook_commands_save(self):
        """
        save states
        """
        self.command_history_dict.sync()
