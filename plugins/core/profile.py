# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/profile.py
#
# File Description: a plugin to profile proxy internals
#
# By: Bast
"""
This plugin profiles functions, commands, and data
"""
# Standard Library
import pprint

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
import libs.argp as argp
from libs.queue import SimpleQueue

NAME = 'Profile Plugin'
SNAME = 'profile'
PURPOSE = 'profile proxy internals'
AUTHOR = 'Bast'
VERSION = 1

REQUIRED = True

class Plugin(BasePlugin):
    """
    a plugin to profile functions, commands, and data
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        BasePlugin.__init__(self, *args, **kwargs)

        self.command_traces = None
        self.changed_mud_data = None
        self.last_command_trace_id = 0
        self.last_changed_mud_data_id = 0

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('setting:add')('commands', False, bool,
                                'flag to echo commands')
        self.api('setting:add')('functions', False, bool,
                                'flag to profile functions')
        self.api('setting:add')('stacklen', 20, int,
                                '# of traces kept')
        self.api('setting:add')('cmdfuncstack', False, bool,
                                'print the function stack in an echo')

        parser = argp.ArgumentParser(
            add_help=False,
            description='show trace info about commands')
        parser.add_argument('-i', '--item',
                            help='the item to show',
                            default='',
                            nargs='?')
        parser.add_argument(
            '-c', '--callstack',
            help="print callstack if available",
            action="store_true",
            default=False)
        self.api('core.commands:command:add')('commands', self.cmd_commands,
                                              parser=parser)

        parser = argp.ArgumentParser(
            add_help=False,
            description='show trace info about data from the mud')
        parser.add_argument('-i', '--item',
                            help='the item to show',
                            default='',
                            nargs='?')
        # parser.add_argument(
        #     '-c', "--callstack",
        #     help="print callstack if available",
        #     action="store_true",
        #     default=False)
        self.api('core.commands:command:add')('muddata', self.cmd_muddata,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='reset command stack')
        self.api('core.commands:command:add')('rstack', self.cmd_rstack,
                                              parser=parser)

        self.command_traces = SimpleQueue(self.api('setting:get')('stacklen'), id_key='id')
        self.changed_mud_data = SimpleQueue(self.api('setting:get')('stacklen'), id_key='id')

        self.api('core.events:register:to:event')('ev_libs.io_execute_trace_finished', self.savecommand, prio=99)
        self.api('core.events:register:to:event')('ev_libs.net.mud_from_mud_event', self.savechanged_mud_data, prio=99)
        self.api('core.events:register:to:event')(f"ev_{self.plugin_id}_var_functions_modified", self.onfunctionschange)

    def onfunctionschange(self, _=None):
        """
        toggle the function profiling
        """
        functions = self.api('setting:get')('functions')
        self.api('libs.timing:toggle')(functions)

    def listcommands(self):
        """
        list the command profiles that have been saved
        """
        self.command_traces.takesnapshot()
        traces = self.command_traces.getsnapshot()
        message = ['Command Traces:']

        for i in traces.items:
            message.append('%-6s : %s' % (i['id'], i['originalcommand']))
        return True, message

    def listchanged_mud_data(self):
        """
        list the muddata profiles that have been saved
        """
        self.changed_mud_data.takesnapshot()
        traces = self.changed_mud_data.getsnapshot()
        message = ['Data Traces:']

        for i in traces.items:
            message.append(f"{i['id']:<6} : {i['trace']['original']}")
        return True, message

    def showchanged_mud_data(self, item_id, callstack=False): # pylint: disable=unused-argument
        """
        find the changed muddata and print it
        """
        snapshot = self.changed_mud_data.getsnapshot()
        if not snapshot:
            self.changed_mud_data.takesnapshot()
            snapshot = self.changed_mud_data.getsnapshot()

        temp_item = snapshot.get_by_id(item_id)
        if temp_item:
            return True, [self.formatmuddatastack(temp_item)]
        else:
            return False, [f"Could not find item: {item_id}"]

    def showcommand(self, item_id, callstack=False):
        """
        find the command trace and format it
        """
        snapshot = self.command_traces.getsnapshot()
        if not snapshot:
            self.command_traces.takesnapshot()
            snapshot = self.command_traces.getsnapshot()

        temp_item = snapshot.get_by_id(item_id)
        if temp_item:
            return True, [self.formatcommandstack(temp_item, callstack)]
        else:
            return False, [f"Could not find item: {item_id}"]

    def cmd_commands(self, args=None):
        """
        get info for a command trace
        """
        if 'item' in args and args['item']:
            return self.showcommand(int(args['item']), callstack=args['callstack'])

        return self.listcommands()

    def cmd_muddata(self, args=None):
        """
        get info for a muddata trace
        """
        if 'item' in args and args['item']:
            return self.showchanged_mud_data(int(args['item']), callstack=False)

        return self.listchanged_mud_data()

    def cmd_rstack(self, _=None):
        """
        reset the command trace
        """
        io_manager = self.api('core.managers:get')('io')

        message = []
        message.append('The following stack was active')
        message.append(f"{io_manager.currenttrace}")
        io_manager.currenttrace = None
        message.append('The stack has been reset')

        return True, message

    def formatmuddatastack(self, stack):
        """
        format the command stack
        """
        message = ['@c------------------- Muddata Trace -------------------@w']
        message.append('%-17s : %s' % ('Original', stack['trace']['original']))

        message.append('@c-------------- Internal Stack --------------@w')
        count = 0
        for i in stack['trace']['changes']:
            count = count + 1
            if 'plugin' in i and i['plugin']:
                apicall = f"{i['plugin']}.formatmuddatatraceitem"
                if self.api('api.has')(apicall):
                    message.append(self.api(apicall)(i))
                    continue

            message.append(f"{count:<2} - {i['plugin'].capitalize():<15} :   {i['flag']}")

            if 'info' in i:
                message.append(f"{' ':<2}   {'Info':<14} :   {i['info']}")

            if 'data' in i:
                message.append(f"{' ':<2}   {'Data':<14} :   {i['data']}")

            if i['flag'] == 'Modify':
                message.append(f"{' ':<2}   {'Original':<16} :   {i['original_data']}")
                message.append(f"{' ':<2}   {'New Command':<16} :   {i['new_data']}")

            message.append('@B-----------------------------------------@w')

        return '\n'.join(message)

    def formatcommandstack(self, stack, callstack=False):
        """
        format the command stack
        """
        message = ['@c------------------- Command Trace -------------------@w']
        message.append(f"{'Original':<17} : {stack['originalcommand']}")
        if stack['fromclient']:
            message.append(f"{'Originated':<17} : from client")
        if stack['internal']:
            message.append(f"{'Originated':<17} : Internal")
        if 'fromplugin' in stack and stack['fromplugin']:
            message.append(f"{'Plugin':<17} : {stack['fromplugin']}")
        message.append(f"{'Show in History':<17} : {stack['showinhistory']}")
        message.append(f"{'Added to History':<17} : {stack['addedtohistory']}")

        message.append('@c-------------- Internal Stack --------------@w')
        count = 0
        for i in stack['changes']:
            count = count + 1
            if 'plugin' in i and i['plugin']:
                apicall = f"{i['plugin']}.formatcmdtraceitem"
                if self.api('libs.api:has')(apicall):
                    message.append(self.api(apicall)(i))
                    continue

            message.append(f"{count:<2} - {i['plugin_id']:<17} :   {i['flag']}")

            if 'info' in i:
                message.append(f"{' ':<2}   {'Info':<16} :   {i['info']}")

            if 'data' in i:
                if isinstance(i['data'], dict):
                    pretty_data = pprint.pformat(i['data'])
                    pretty_data = pretty_data.replace('\n', '\n' + ' ' * 27)
                else:
                    pretty_data = i['data']

                message.append(f"{' ':<2}   {'Data':<16} :   {pretty_data}")

            if i['flag'] == 'Modify':
                message.append(f"{' ':<2}   {'Original Command':<16} :   {i['original_data']}")
                message.append(f"{' ':<2}   {'New Command':<16} :   {i['new_data']}")

            if callstack and 'callstack' in i:
                for line in i['callstack']:
                    message.append(f"{'':<22} :   {line}")

            message.append('@b-----------------------------------------@w')


        return '\n'.join(message)

    def savecommand(self, args):
        """
        echo the command
        """
        args['id'] = self.last_command_trace_id
        self.last_command_trace_id = self.last_command_trace_id + 1
        self.command_traces.enqueue(args)

        echocommands = self.api('setting:get')('commands')

        if echocommands:
            self.api('libs.io:send:client')(self.formatcommandstack(args))

    def savechanged_mud_data(self, args):
        """
        save mud data that was changed
        """
        if args:
            args['id'] = self.last_changed_mud_data_id + 1
            self.last_changed_mud_data_id = self.last_changed_mud_data_id + 1
            self.changed_mud_data.enqueue(args)
