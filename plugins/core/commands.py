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
import shlex
import sys
import copy
import textwrap as _textwrap

# 3rd Party
try:
    from deepdiff import DeepDiff
except ImportError:
    print('Please install required libraries. deepdiff is missing.')
    print('From the root of the project: pip(3) install -r requirements.txt')
    sys.exit(1)

# Project
from plugins._baseplugin import BasePlugin
from libs.persistentdict import PersistentDict
from libs.record import ToClientRecord
import libs.argp as argp

NAME = 'Commands'
SNAME = 'commands'
PURPOSE = 'Parse and handle commands'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

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
        temp_help = action.help
        # we add the default value to the argument help
        if '%(default)' not in action.help:
            if action.default is not argp.SUPPRESS:
                defaulting_nargs = [argp.OPTIONAL, argp.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    if action.default != '':
                        temp_help += ' (default: %(default)s)'
        return temp_help

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
        self.commands_list = []

        # a list of commands that should not be run again if already in the queue
        self.no_multiple_commands = {}

        # load the history
        self.history_save_file = self.save_directory / 'history.txt'
        self.command_history_dict = PersistentDict(self.history_save_file, 'c')
        if 'history' not in self.command_history_dict:
            self.command_history_dict['history'] = []
        self.command_history_data = self.command_history_dict['history']

        # add apis
        self.api('libs.api:add')('add', self._api_add_command)
        self.api('libs.api:add')('change', self._api_change_command)
        self.api('libs.api:add')('run', self._api_run)
        self.api('libs.api:add')('prefix', self._api_get_prefix)
        #self.api('libs.api:add')('default', self.api_setdefault)
        self.api('libs.api:add')('remove:plugin:data', self._api_remove_plugin_data)
        self.api('libs.api:add')('get:plugin:command:format', self._api_get_plugin_command_format)
        self.api('libs.api:add')('get:plugin:command:help', self._api_get_plugin_command_help)
        self.api('libs.api:add')('get:plugin:command:data', self._api_get_plugin_command_data)

        self.api('libs.api:add')('command:add', self._api_add_command)
        self.api('libs.api:add')('command:change', self._api_change_command)
        self.api('libs.api:add')('command:run', self._api_run)
        self.api('libs.api:add')('command:help:format', self._api_get_plugin_command_help)
        self.api('libs.api:add')('get:command:prefix', self._api_get_prefix)
        self.api('libs.api:add')('remove:data:for:plugin', self._api_remove_plugin_data)
        self.api('libs.api:add')('get:commands:for:plugin:formatted', self._api_get_plugin_command_format)
        self.api('libs.api:add')('get:commands:for:plugin:data', self._api_get_plugin_command_data)

        self.dependencies = ['core.events', 'core.msg', 'core.errors', 'core.fuzzy']
        #self.dependencies.append('core.fuzzy')

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        # add a datatype
        self.api('plugins.core.msg:add:datatype')(self.plugin_id)
        #self.api('plugins.core.msg:toggle:to:console')(self.plugin_id)

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
                                              showinhistory=False)

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
                                              showinhistory=False)

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
                                              showinhistory=False)

        # register events
        self.api('plugins.core.events:register:to:event')('ev_libs.io_execute', self._event_io_execute_check_command, prio=5)
        self.api('plugins.core.events:register:to:event')('ev_core.plugins_plugin_uninitialized', self._event_plugin_uninitialized)
        self.api('plugins.core.events:register:to:event')('ev_{0.plugin_id}_savestate'.format(self), self._savestate)

    def _event_plugin_uninitialized(self, args):
        """
        a plugin was uninitialized

        registered to the plugin_uninitialized event
        """
        self.api('libs.io:send:msg')(f"removing commands for plugin {args['plugin_id']}",
                                     secondary=args['plugin_id'])
        self.api('{0.plugin_id}:remove:data:for:plugin'.format(self))(args['plugin_id'])

    # remove all commands for a plugin
    def _api_remove_plugin_data(self, plugin_id):
        """  remove all command data for a plugin
        @Yplugin@w    = the plugin to remove commands for

        this function returns no values"""
        # get the plugin instance
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)

        if plugin_instance:
            # remove commands from command_list that start with plugin_instance.plugin_id
            new_commands = [command for command in self.commands_list if not command.startswith(plugin_instance.plugin_id)]
            self.commands_list = new_commands

    def format_return_message(self, message, plugin_id, command):
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

        message.insert(0, '')
        message.insert(1, f"{self.api('setting:get')('cmdprefix')}.{plugin_id}.{command}")
        message.insert(2, '@G' + '-' * line_length + '@w')
        message.append('@G' + '-' * line_length + '@w')
        message.append('')
        return message

    # return the command prefix setting
    def _api_get_prefix(self):
        """  get the current command prefix

        returns the current command prefix as a string"""
        return self.api('setting:get')('cmdprefix')

    # change an attribute for a command
    def _api_change_command(self, plugin_id, command_name, flag_name, flag_value):
        """  change an attribute for a command
        @Yplugin@w        = the plugin the command is in
        @Ycommand_name@w  = the command name
        @Yflag_name@w     = the flag to change
        @Yflag_value@w    = the new value of the flag

        returns True if successful, False if not"""
        # get the command data for the plugin
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)
        command_data = self.get_command(plugin_instance.plugin_id, command_name)

        # didn't find the command
        if not command_data:
            self.api('libs.io:send:error')(f"command {command_name} does not exist in plugin {plugin_id} ({plugin_instance.plugin_id})")
            return False

        # flag isn't in the command
        if flag_name not in command_data:
            self.api('libs.io:send:error')(
                f"flag {flag_name} does not exist in command {command_name} in plugin {plugin_id} ({plugin_instance.plugin_id})")
            return False

        # change the flag and update the command data for the plugin
        data = self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:get')('commands')
        if not data:
            data = {}
        data[command_name][flag_name] = flag_value

        self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:update')('commands', data)

        return True

    # return the help for a command
    def _api_get_plugin_command_help(self, plugin_id, command_name):
        """  get the help for a command
        @Yplugin@w        = the plugin the command is in
        @Ycommand_name@w  = the command name

        returns the help message as a string"""
        # get the command data for the plugin
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)
        command_data = self.get_command(plugin_instance.plugin_id, command_name)

        if command_data:
            return command_data['parser'].format_help()

        return ''

    # return a formatted list of commands for a plugin
    def _api_get_plugin_command_format(self, plugin_id):
        """  get a list of commands for the specified plugin
        @Yplugin@w   = the plugin the command is in

        returns a list of strings formatted for the commands in the plugin
        """
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)

        if plugin_instance:
            return self.list_commands(plugin_instance.plugin_id)

        return None

    # return the raw command data for a plugin
    def _api_get_plugin_command_data(self, plugin_id):
        """  get the data for commands for the specified plugin
        @Yplugin@w   = the plugin the command is in

        returns a dictionary of commands
        """
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)

        if plugin_instance:
            data = self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:get')('commands')
            return data

        return {}

    # run a command and return the output
    def _api_run(self, plugin, command_name, argument_string):
        """  run a command and return the output
        @Yplugin@w          = the plugin the command is in
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
        command = self.get_command(plugin, command_name)

        if command:
            args, dummy = command['parser'].parse_known_args(argument_string)

            args = vars(args)

            if args['help']:
                return command['parser'].format_help().split('\n')

            return command['func'](args)

        return None, []

    def run_command(self, command, targs, full_arguments, data):
        """
        run a command that has an ArgParser

        arguments:
          required:
            command         - the command data dictionary
            targs           - the argument string
            full_arguments  - the full argument string
            data            - the data in the input stack

        This function runs the command and sends the returned
          data to the client

        returns:
          True if succcessful, False if not successful
        """
        retval = False
        command_ran = f"{self.api('setting:get')('cmdprefix')}.{command['plugin_id']}.{command['commandname']} {full_arguments}"

        self.api('libs.io:trace:add:execute')(self.plugin_id, 'Running Command',
                                              info=f"Command: '{command_ran}'")

        # parse the arguments and deal with errors
        try:
            args, dummy = command['parser'].parse_known_args(targs)
        except argp.ArgumentError as exc:
            message = []
            message.append(f"Error: {exc.errormsg}") # pylint: disable=no-member
            message.extend(command['parser'].format_help().split('\n'))
            ToClientRecord(self.format_return_message(message,
                                                      command['plugin_id'],
                                                      command['commandname'])).send(__name__ + ':run_command_1')
            self.api('libs.io:trace:add:execute')(
                self.plugin_id, 'Command Error',
                info=f"{command_ran} - error parsing args",
                data=f"{exc.errormsg}")
            return retval

        args = vars(args)
        args['fullargs'] = full_arguments

        # return help if flagged
        if args['help']:
            message = command['parser'].format_help().split('\n')
            ToClientRecord(self.format_return_message(message,
                                                      command['plugin_id'],
                                                      command['commandname'])).send(__name__ + ':run_command_2')

        # deal with output and success from running the command
        else:
            args['data'] = data
            return_value = command['func'](args)
            if isinstance(return_value, tuple):
                retval = return_value[0]
                message = return_value[1]
            else:
                retval = return_value
                message = []

            # did not succeed
            if retval is False:
                message.append('')
                message.extend(command['parser'].format_help().split('\n'))
                ToClientRecord(self.format_return_message(message,
                                                          command['plugin_id'],
                                                          command['commandname'])).send(__name__ + ':run_command_3')

            # succeeded
            else:
                self.add_command_to_history(data, command)
                # if the format flag is not set then the data is returned
                if (not command['format']) and message:
                    ToClientRecord(message, preamble=command['preamble']).send(__name__ + ':run_command_4')
                # if the format flag is set, then format the data to the client
                elif message:
                    ToClientRecord(self.format_return_message(message,
                                           command['plugin_id'],
                                           command['commandname']),
                                   preamble=command['preamble']).send(__name__ + ':run_command_5')

        self.api('libs.io:trace:add:execute')(
            self.plugin_id, 'Running Command',
            info=f"Command: '{command_ran}' was {'Successful' if retval else 'Unsuccessful'}")

        return retval

    def add_command_to_history(self, data, command=None):
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
        # if showinhistory is false in either data or command, don't add
        if 'showinhistory' in data and not data['showinhistory']:
            return False
        if command and not command['showinhistory']:
            return False

        tdat = data['fromdata']
        # only add to history if it came from the client
        if data['fromclient']:
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
            return True

        return False

    # return a list of all commands known
    def api_get_all_commands_list(self):
        """
        return a list of all commands

        returns a list of commands
        """
        return self.commands_list

    # retrieve a command from a plugin
    def get_command(self, plugin_id, command):
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
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)

        # retrieve the commands data
        data = self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:get')('commands')
        if not data:
            return None

        # return the command
        if command in data:
            return data[command]

        return None

    # update a command
    def update_command(self, plugin_id, command_name, data):
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
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)

        all_command_data = self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:get')('commands')

        if not all_command_data:
            all_command_data = {}

        if command_name not in all_command_data:
            if not self.api.startup:
                self.api('libs.io:send:msg')(f"commands - update_command: plugin {plugin_id} does not have command {command_name}",
                                             secondary=plugin_instance.plugin_id)

        all_command_data[command_name] = data

        return self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:update')('commands', all_command_data)

    def pass_through_command(self, data, command_data_dict):
        """
        pass through data to the mud
        if it isn't a command we add it to history and check antispam

        arguments:
          required:
            data               - the io data stack
            command_data_dict  - the command data dict

        returns the updated data stack
        """
        # if it isn't a #bp command, we add it to history and do some checks
        # before sending it to the mud
        addedtohistory = self.add_command_to_history(data)

        # if the command is the same as the last command, do antispam checks
        if command_data_dict['orig'].strip() == self.api('setting:get')('lastcmd'):
            self.api('setting:change')('cmdcount',
                                       self.api('setting:get')('cmdcount') + 1)

            # if the command has been sent spamcount times, then we send an antispam
            # command in between
            if self.api('setting:get')('cmdcount') == \
                                  self.api('setting:get')('spamcount'):
                data['fromdata'] = self.api('setting:get')('antispamcommand') \
                                            + '|' + command_data_dict['orig']
                self.api('libs.io:trace:add:execute')(
                    self.plugin_id, 'Command Antispam',
                    info=f"command was sent {self.api('setting:get')('spamcount')} times, sending {self.api('setting:get')('antispamcommand')} for antispam")

                data['addedtohistory'] = addedtohistory

                self.api('libs.io:send:msg')('adding look for 20 commands')
                self.api('setting:change')('cmdcount', 0)
                return data

            # if the command is seen multiple times in a row and it has been flagged to only be sent once,
            # swallow it
            if command_data_dict['orig'] in self.no_multiple_commands:
                self.api('libs.io:trace:add:execute')(
                    self.plugin_id, 'Command Nomultiple',
                    data='This command has been flagged not to be sent multiple times in a row')
                data['fromdata'] = ''
                return data
        else:
            # the command does not match the last command
            self.api('setting:change')('cmdcount', 0)
            self.api('libs.io:send:msg')(f"resetting command to {command_data_dict['orig'].strip()}")
            self.api('setting:change')('lastcmd', command_data_dict['orig'].strip())

        # add a trace if it is unknown how the command was changed
        if data['fromdata'] != command_data_dict['orig']:
            self.api('libs.io:trace:add:execute')(
                self.plugin_id, 'Command Unknown',
                info='Unknown why it got here',
                data=data['fromdata'])
        return data

    def _event_io_execute_check_command(self, data):
        """
        check a line from a client for a command

        arguments:
          required:
            data               - the io data stack

        returns:
          None if no data
          Otherwise it returns the update data stack
        """
        # strip single ctrl chars that mess up unicode encoding
        # this keeps the command history data clean for encoding
        # like ctrl-c from a linux terminal client
        if len(data['fromdata']) == 1:
            try:
                temps = data['fromdata']
                temps.encode('utf-8')
            except UnicodeDecodeError:
                return None

        command_data_dict = {}
        command_data_dict['orig'] = data['fromdata']
        command_data_dict['commandran'] = data['fromdata']
        command_data_dict['flag'] = 'Unknown'
        command_data_dict['cmd'] = None
        command_data_dict['data'] = data

        # if no data, skip this
        if command_data_dict['orig'] == '':
            return None

        commandprefix = self.api('setting:get')('cmdprefix')
        # if it isn't a command, pass it through
        if command_data_dict['orig'][0:len(commandprefix)].lower() != commandprefix:
            return self.pass_through_command(data, command_data_dict)

        self.api('libs.io:send:msg')(f"got command: {command_data_dict['orig']}")

        # split it with shlex
        try:
            split_args = shlex.split(command_data_dict['orig'].strip())
        except ValueError:
            self.api('libs.io:send:traceback')('could not parse command')
            data['fromdata'] = ''
            return data

        # split out the full argument string
        try:
            first_space = command_data_dict['orig'].index(' ')
            full_args_string = command_data_dict['orig'][first_space+1:]
        except ValueError:
            full_args_string = ''

        # find which command we are
        command = split_args.pop(0)

        # split the command at .
        split_command_list = command.split('.')

        if len(split_command_list) > 4:
            command_data_dict['flag'] = 'Bad Command'
            command_data_dict['cmddata'] = f"Command name too long: {command}"
        else:
            short_names = self.api('plugins.core.plugins:get:all:short:names')()
            loaded_plugin_ids = self.api('plugins.core.plugins:get:loaded:plugins:list')()

            plugin_package = None
            plugin_name = None
            plugin_command = None

            found_short_name = None
            found_package = None
            found_command = None
            found_plugin_id = None

            # parse the command to get what to search for
            if len(split_command_list) == 1: # this would be cmdprefix by iself, ex. #bp
                # run #bp.commands.list
                pass
            elif len(split_command_list) == 2: # this would be cmdprefix + plugin_name, ex. #bp.ali
                plugin_name = split_command_list[1]
            elif len(split_command_list) == 3: # this would be cmdprefix + plugin_name + command, ex. #bp.alias.list
                                               # also could be cmdprefix + package + plugin_name
                # first check if the last part is a plugin
                shortname_check = self.api('plugins.core.fuzzy:get:best:match')(split_command_list[-1], short_names)
                if shortname_check:
                    plugin_name = split_command_list[-1]
                    plugin_package = split_command_list[1]
                # if not, then set plugin_name and plugin_command for later lookup
                else:
                    plugin_name = split_command_list[1]
                    plugin_command = split_command_list[-1]
            else: # len(split_command_list) == 4 would be cmdprefix + package + plugin_name + command,
                        # ex. #bp.client.alias.list
                plugin_package = split_command_list[1]
                plugin_name = split_command_list[2]
                plugin_command = split_command_list[-1]

            # print 'fullcommand: %s' % command
            # print 'plugin_package: %s' % plugin_package
            # print 'plugin: %s' % plugin_name
            # print 'command: %s' % plugin_command

            # find package
            if plugin_package and not found_package:
                packages = self.api('plugins.core.plugins:get:packages:list')()
                found_package = self.api('plugins.core.fuzzy:get:best:match')(plugin_package, packages)

            # find plugin_id
            if found_package and plugin_name and not found_plugin_id:
                plugin_list = [i.split('.')[-1] for i in loaded_plugin_ids if i.startswith(f"{found_package}.")]
                found_short_name = self.api('plugins.core.fuzzy:get:best:match')(plugin_name, plugin_list)
                if not found_short_name:
                    found_plugin_id = self.api('plugins.core.fuzzy:get:best:match')(found_package + '.' + plugin_name, loaded_plugin_ids)
                else:
                    found_plugin_id = found_package + '.' + found_short_name

            if not found_plugin_id and plugin_name:
                found_plugin_id = self.api('plugins.core.plugins:short:name:convert:plugin:id')(plugin_name)
                if found_plugin_id:
                    found_package = found_plugin_id.split('.')[0]

            # if a plugin was found but we don't have a package, find the package
            if found_plugin_id and plugin_name and not found_package:
                packages = []
                for plugin_name in loaded_plugin_ids:
                    if found_plugin_id in plugin_name:
                        packages.append(plugin_name.split('.')[0])
                if len(packages) == 1:
                    found_package = packages[0]

            # couldn't find a plugin
            if not found_plugin_id:

                command_data_dict['flag'] = 'Bad Command'
                command_data_dict['cmddata'] = f"could not find command {command}"

            # at least have a plugin
            else:
                if '.' not in found_plugin_id:
                    print('found_plugin_id is not a plugin_id')
                if plugin_command:
                    commands = self.api('plugins.core.commands:get:commands:for:plugin:data')(found_plugin_id).keys()
                    found_command = self.api('plugins.core.fuzzy:get:best:match')(plugin_command, commands)

                # have a plugin but no command
                if found_plugin_id and not found_command:

                    if plugin_command:
                        command_data_dict['flag'] = 'Bad Command'
                        command_data_dict['cmddata'] = f"command {plugin_command} does not exist in plugin {found_plugin_id}"
                    else:
                        command_data_dict['cmd'] = self.get_command(self.plugin_id, 'list')
                        command_data_dict['flag'] = 'Help'
                        command_data_dict['commandran'] = f"{self.api('setting:get')('cmdprefix')}.{self.plugin_id}.{'list'} {found_plugin_id}"
                        command_data_dict['targs'] = [found_plugin_id]
                        command_data_dict['fullargs'] = full_args_string

                # have a plugin and a command
                else:
                    command = self.get_command(found_plugin_id, found_command)
                    command_data_dict['cmd'] = command
                    command_data_dict['commandran'] = f"{self.api('setting:get')('cmdprefix')}.{found_plugin_id}.{command['commandname']} {' '.join(split_args)}"
                    command_data_dict['flag'] = 'Found Command'
                    command_data_dict['targs'] = split_args
                    command_data_dict['fullargs'] = full_args_string

            # print 'fullcommand: %s' % command
            # print 'found_package: %s' % found_package
            # print 'found_plugin_id: %s' % found_plugin_id
            # print 'found_command: %s' % found_command

            command_data_dict['plugin_id'] = found_plugin_id
            command_data_dict['scmd'] = found_command

            # run the command here
            if command_data_dict['flag'] == 'Bad Command':
                self.api('libs.io:trace:add:execute')(self.plugin_id, 'Bad Command',
                                                      data=copy.copy(command_data_dict))
                ToClientRecord(f"@R{command}@W is not a command").send(__name__ + ':_event_io_execute_check_command')
            else:
                command_data_dict_copy = copy.copy(command_data_dict)
                self.api('libs.io:trace:add:execute')(self.plugin_id, command_data_dict['flag'],
                                                      data=command_data_dict_copy,
                                                      info='Pre Run Command Data')

                try:
                    command_data_dict['success'] = self.run_command(command_data_dict['cmd'],
                                                                    command_data_dict['targs'],
                                                                    command_data_dict['fullargs'],
                                                                    command_data_dict['data'])
                except Exception:  # pylint: disable=broad-except
                    command_data_dict['success'] = 'Error'
                    self.api('libs.io:send:traceback')(
                        f"Error when calling command {command_data_dict['plugin_id']}.{command_data_dict['scmd']}")
                self.api('libs.io:trace:add:execute')(self.plugin_id, command_data_dict['flag'],
                                                      data=DeepDiff(command_data_dict_copy, command_data_dict,
                                                                    exclude_paths=["root['parser']"],
                                                                    verbose_level=2),
                                                      info="Post Run Command Data Difference")

                command_data_dict['cmddata'] = f"'{command_data_dict['commandran']}' - Outcome: {command_data_dict['success']}"

            return {'fromdata':''}

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

        called_from = self.api('libs.api:get:caller:plugin')()

        long_name = None

        # passed an empty function
        if not func:
            self.api('libs.io:send:error')(
                f"add command for command {command_name} was passed a null function from plugin {called_from}, not adding",
                secondary=called_from)
            return

        # find the plugin_id
        if 'plugin_id' in args:
            plugin_id = args['plugin_id']
        else:
            plugin_id = self.api('libs.api:get:function:plugin:owner')(func)
            if not plugin_id:
                call_stack = self.api('libs.api:get:call:stack')()
                self.api('libs.io:send:error')(
                    f"Function is not part of a plugin class: command {command_name} from plugin {called_from}",
                    secondary=called_from)
                self.api('libs.io:send:error')("\n".join(call_stack).strip())
                return

        # add custom formatter to the parser passed in
        if 'parser' in args:
            new_parser = args['parser']
            new_parser.formatter_class = CustomFormatter

        # use default parser if none passed in
        else:
            self.api('libs.io:send:msg')(
                f"adding default parser to command {plugin_id}.{command_name}")
            if 'shelp' not in args:
                args['shelp'] = 'there is no help for this command'
            new_parser = argp.ArgumentParser(add_help=False,
                                             description=args['shelp'])
            args['parser'] = new_parser

        try:
            new_parser.add_argument('-h', '--help', help='show help',
                                    action='store_true')
        except argp.ArgumentError:
            pass

        new_parser.prog = f"@B{self.api('setting:get')('cmdprefix')}.{plugin_id}.{command_name}@w"

        # if no group, add the group as the plugin_name
        if 'group' not in args:
            args['group'] = plugin_id

        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)
        try:
            long_name = plugin_instance.name
        except AttributeError:
            pass

        if not long_name:
            self.api('libs.io:send:msg')(f"plugin {plugin_id} has no long name, not adding command {command_name}",
                                         secondary=plugin_id)
            return

        # build the command dict
        args['func'] = func
        args['lname'] = long_name
        args['plugin_id'] = plugin_id
        args['commandname'] = command_name
        if 'preamble' not in args:
            args['preamble'] = True
        if 'format' not in args:
            args['format'] = True
        if 'showinhistory' not in args:
            args['showinhistory'] = True

        # update the command
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)
        self.update_command(plugin_instance.plugin_id, command_name, args)

        self.commands_list.append(f"{plugin_instance.plugin_id}.{command_name}")

        self.api('libs.io:send:msg')(f"added command {plugin_id}.{command_name}",
                                     level='debug', secondary=plugin_instance.plugin_id)

    # remove a command
    def _api_remove_command(self, plugin_id, command_name):
        """  remove a command
        @Yplugin@w        = the top level of the command
        @Ycommand_name@w  = the name of the command

        this function returns no values"""
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin_id)
        removed = False
        if plugin_instance:
            data = self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:get')('commands')
            if data and command_name in data:
                del data[command_name]
                self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:update')('commands', data)
                self.api('libs.io:send:msg')(f"removed command {plugin_id}.{command_name}",
                                             secondary=plugin_id)
                removed = True

        if not removed:
            self.api('libs.io:send:msg')(f"remove command: command {plugin_id}.{command_name} does not exist",
                                         secondary=plugin_id)

    def format_command_list(self, command_list):
        """
        format a list of commands by a category

        arguments:
          required:
            command_list    - the list of commands to format

        returns the a list of stings for the commands
        """
        message = []
        for i in command_list:
            if i != 'default':
                tlist = i['parser'].description.split('\n')
                if not tlist[0]:
                    tlist.pop(0)
                message.append(f"  @B{i['commandname']:<10}@w : {tlist[0]}")

        return message

    def list_commands(self, plugin):
        """
        build a table of commands for a plugin

        arguments:
          required:
            plugin    - the plugin to build the commands from

        returns the a list of stings for the list of commands
        """
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(plugin)

        message = []
        if plugin_instance:
            commands = self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:get')('commands')
            message.append('Commands in %s:' % plugin_instance.plugin_id)
            message.append('@G' + '-' * 60 + '@w')
            groups = {}
            for i in sorted(commands.keys()):
                if i != 'default':
                    if commands[i]['group'] not in groups:
                        groups[commands[i]['group']] = []

                    groups[commands[i]['group']].append(commands[i])

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
        plugin_instance = self.api('plugins.core.plugins:get:plugin:instance')(args['plugin'])
        command = args['command']
        if plugin_instance:
            plugin_commands = self.api('libs.api:run:as:plugin')(plugin_instance.plugin_id, 'data:get')('commands')
            if plugin_commands:
                if command and command in plugin_commands:
                    help_message = plugin_commands[command]['parser'].format_help().split('\n')
                    message.extend(help_message)
                else:
                    message.extend(self.list_commands(plugin_instance.plugin_id))
            else:
                message.append('There are no commands in plugin %s' % plugin_instance.plugin_id)
        else:
            message.append('Plugins')
            plugin_id_list = self.api('plugins.core.plugins:get:loaded:plugins:list')()
            plugin_id_list = sorted(plugin_id_list)
            message.append(self.api('plugins.core.utils:format:list:into:columns')(plugin_id_list, cols=3, columnwise=False, gap=6))
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

        ToClientRecord(f"Commands: rerunning command {command}").send(__name__ + ':command_runhistory')
        self.api('libs.io:send:execute')(command)

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
            for i in self.command_history_data:
                message.append('%s : %s' % (self.command_history_data.index(i), i))

        return True, message

    def _savestate(self, _=None):
        """
        save states
        """
        self.command_history_dict.sync()
