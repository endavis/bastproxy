# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/log.py
#
# File Description: a plugin to change logging settings
#
# By: Bast
"""
This module handles changing logging settings
"""
# Standard Library
import logging
import os

# 3rd Party

# Project
import libs.argp as argp
from libs.persistentdict import PersistentDict
from plugins._baseplugin import BasePlugin
from libs.record import LogRecord, RMANAGER

NAME = 'Logging'
SNAME = 'log'
PURPOSE = 'Handles changing logging settings'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

class Plugin(BasePlugin):
    """
    a class to manage logging
    """
    def __init__(self, *args, **kwargs):
        """
        init the class
        """
        super().__init__(*args, **kwargs)

        self.can_reload_f = False
        self.record_manager = RMANAGER
        self.log_directory = self.api.BASEDATAPATH / 'logs'

        try:
            os.makedirs(self.save_directory)
        except OSError:
            pass
        self.datatypes_to_client = PersistentDict(
            self.save_directory /'datatypes_to_client.txt',
            'c')
        self.datatypes_to_console = PersistentDict(
            self.save_directory / 'datatypes_to_console.txt',
            'c')
        self.datatypes_to_file = PersistentDict(
            self.save_directory / 'datatypes_to_file.txt',
            'c')

        self.api('setting:add')('color_error', '@x136', 'color',
                                'the color for error messages')
        self.api('setting:add')('color_warning', '@y', 'color',
                                'the color for warning messages')
        self.api('setting:add')('color_info', '@w', 'color',
                                'the color for info messages')
        self.api('setting:add')('color_debug', '@x246', 'color',
                                'the color for debug messages')
        self.api('setting:add')('color_critical', '@r', 'color',
                                'the color for critical messages')
        self.setting_values.pload()


        # new api format
        self.api('libs.api:add')('toggle:log:to:console', self.api_toggletoconsole)
        self.api('libs.api:add')('toggle:log:to:file', self.api_toggletofile)
        self.api('libs.api:add')('toggle:log:to:client', self.api_toggletoclient)
        self.api('libs.api:add')('can:log:to:console', self._api_can_log_to_console)
        self.api('libs.api:add')('can:log:to:file', self._api_can_log_to_file)
        self.api('libs.api:add')('can:log:to:client', self._api_can_log_to_client)
        self.api('libs.api:add')('get:level:color', self._api_get_level_color)

    def _api_get_level_color(self, level):
        """
        get the color for a log level
        """
        if isinstance(level, int):
            level = logging.getLevelName(level).lower()
        match level:
            case 'error':
                return self.setting_values['color_error']
            case 'warning':
                return self.setting_values['color_warning']
            case 'info':
                return self.setting_values['color_info']
            case 'debug':
                return self.setting_values['color_debug']
            case 'critical':
                return self.setting_values['color_critical']
            case _:
                return ''

    def _api_can_log_to_console(self, logger, level):
        """
        check if a logger can log to the console

        if the logger hasn't been seen, it will default to logging.INFO
        """
        if logger not in self.datatypes_to_console:
            self.datatypes_to_console[logger] = logging.INFO
            self.datatypes_to_console.sync()

        if level >= self.datatypes_to_console[logger]:
            return True

        return False

    def _api_can_log_to_file(self, logger, level):
        """
        check if a logger can log to the file

        if the logger hasn't been seen, it will default to logging.INFO
        """
        if logger not in self.datatypes_to_file:
            self.datatypes_to_file[logger] = logging.INFO
            self.datatypes_to_file.sync()

        if level >= self.datatypes_to_file[logger]:
            return True

        return False

    def _api_can_log_to_client(self, logger, level):
        """
        check if a logger can log to the client

        if the logger hasn't been seen, do not allow logging to the client
        logging to the client must be explicitly enabled
        """
        if logger in self.datatypes_to_client and level >= self.datatypes_to_client[logger]:
            return True

        return False

    def _api_log_level_set(self, datatype, level):
        """
        set the log level for a datatype
        """
        self.log_levels[datatype] = level

    # toggle logging a datatype to the clients
    def api_toggletoclient(self, datatype, level=logging.INFO, flag=True):
        """  toggle a data type to show to clients
        @Ydatatype@w  = the type to toggle, can be multiple (list)
        @Yflag@w      = True to send to clients, false otherwise (default: True)

        this function returns no values"""
        if isinstance(level, str):
            level = getattr(logging, level.upper(), None)
        if not level:
            LogRecord(f"api_toggletoclient: invalid log level {level}",
                      'error', sources=[self.plugin_id, datatype]).send()
            return

        if flag and not datatype in self.datatypes_to_client:
            self.datatypes_to_client[datatype] = level
        else:
            if datatype in self.datatypes_to_client:
                del(self.datatypes_to_client[datatype])

        LogRecord(f"setting {datatype} to log to client at level {logging.getLevelName(level)}",
                  'debug', sources=[self.plugin_id, datatype]).send()
        self.datatypes_to_client.sync()

    # toggle logging datatypes to the clients
    def cmd_client(self, args):
        """
        toggle datatypes shown to client
        """
        tmsg = []
        if args['datatype']:
            for i in args['datatype']:
                if i in self.datatypes_to_client:
                    self.datatypes_to_client[i] = not self.datatypes_to_client[i]
                    if self.datatypes_to_client[i]:
                        tmsg.append(f"setting {i} to log to client")
                    else:
                        tmsg.append(f"no longer sending {i} to client")

                elif i != 'frommud':
                    tmsg.append(f"datatype {i} does not exist")
            self.datatypes_to_client.sync()
            return True, tmsg

        tmsg.append('Current types going to client')
        for i in self.datatypes_to_client:
            if self.datatypes_to_client[i]:
                tmsg.append(i)
        return True, tmsg

    # toggle logging a datatype to the console
    def api_toggletoconsole(self, datatype, flag=True, level='info'):
        """  toggle a data type to show to console
        @Ydatatype@w  = the type to toggle
        @Yflag@w      = True to send to console, false otherwise (default: True)

        this function returns no values"""
        if isinstance(level, str):
            level = getattr(logging, level.upper(), None)
        if not level:
            LogRecord(f"api_toggletoconsole: invalid log level {level}", 'error',
                      sources=[self.plugin_id, datatype]).send()
            return

        if flag and not datatype in self.datatypes_to_console:
            self.datatypes_to_console[datatype] = level
        else:
            if datatype in self.datatypes_to_console:
                del(self.datatypes_to_console[datatype])

        LogRecord(f"setting {datatype} to log to console at level {logging.getLevelName(level)}",
                  'debug', sources=[self.plugin_id, datatype]).send()

        self.datatypes_to_console.sync()

    # toggle logging datatypes to the console
    def cmd_console(self, args):
        """
        log datatypes to the console
        """
        tmsg = []
        if args['datatype']:
            for i in args['datatype']:
                if i in self.datatypes_to_console and i != 'frommud':
                    self.datatypes_to_console[i] = not self.datatypes_to_console[i]
                    if self.datatypes_to_console[i]:
                        tmsg.append(f"setting {i} to console")
                    else:
                        tmsg.append(f"no longer sending {i} to console")

                elif i != 'frommud':
                    tmsg.append(f"datatype {i} does not exist")
            self.datatypes_to_console.sync()
            return True, tmsg

        tmsg.append('Current types going to console')
        for i in self.datatypes_to_console:
            if self.datatypes_to_console[i]:
                tmsg.append(i)
        return True, tmsg

    # toggle logging a datatype to a file
    def api_toggletofile(self, datatype, flag=True, level=logging.INFO):
        """  toggle a data type to show to file
        @Ydatatype@w  = the type to toggle
        @Yflag@w      = True to send to file, false otherwise (default: True)

        this function returns no values"""
        if isinstance(level, str):
            level = getattr(logging, level.upper(), None)
        if not level:
            LogRecord(f"api_toggletofile: invalid log level {level}",
                      'error', sources=[self.plugin_id, datatype]).send()
            return

        if flag and not datatype in self.datatypes_to_file:
            self.datatypes_to_file[datatype] = level
        else:
            if datatype in self.datatypes_to_file:
                del(self.datatypes_to_file[datatype])

        LogRecord(f"setting {datatype} to log to file at level {logging.getLevelName(level)}",
                  'debug', sources=[self.plugin_id, datatype]).send()


    # toggle a datatype to log to a file
    def cmd_file(self, args):
        """
        toggle a datatype to log to a file
        """
        tmsg = []
        timestamp = True
        if args['datatype'] != 'list':
            dtype = args['datatype']
            timestamp = args['notimestamp']

            result = self.api(f"{self.plugin_id}:toggle:to:file")(dtype, timestamp)

            if result == 'on':
                tmsg.append(f"Sending {dtype} to file")
            elif result == 'off':
                tmsg.append(f"No longer sending {dtype} to file")

            return True, tmsg
        else:
            tmsg.append('Current types going to file')
            for i in self.datatypes_to_file:
                if self.datatypes_to_file[i]:
                    tmsg.append(f"{i:<20} - Timestamp: {self.datatypes_to_file[i]['timestamp']}")
            return True, tmsg

    # show all types
    def cmd_types(self, args):
        """
        list data types
        """
        types = []
        types.extend(self.datatypes_to_client.keys())
        types.extend(self.datatypes_to_console.keys())
        types.extend(self.datatypes_to_file.keys())
        types = sorted(set(types))
        tmsg = []
        tmsg.append('Data Types')
        tmsg.append('-' *  30)
        match = args['match']
        for i in types:
            if not match or match in i:
                tmsg.append(i)
        return True, tmsg

    def initialize(self):
        """
        initialize external stuff
        """
        BasePlugin.initialize(self)

        self.api('plugins.core.events:register:to:event')(f"ev_{self.plugin_id}_savestate", self._savestate)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""toggle datatypes to clients

          if no arguments, data types that are currenty sent to clients will be listed""")
        parser.add_argument('datatype',
                            help='a list of datatypes to toggle',
                            default=[],
                            nargs='*')
        parser.add_argument('level',
                            help='a list of datatypes to toggle',
                            default='info',
                            choices=['debug', 'info', 'warning', 'error', 'critical'],
                            nargs='*')
        self.api('plugins.core.commands:command:add')('client',
                                              self.cmd_client,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""toggle datatype to log to a file

          the file will be located in the data/logs/<dtype> directory

          the filename for the log will be <date>.log
              Example: Tue-Feb-26-2013.log

          if no arguments, types that are sent to file will be listed""")
        parser.add_argument('datatype',
                            help='the datatype to toggle',
                            default='list',
                            nargs='?')
        parser.add_argument('-n',
                            '--notimestamp',
                            help='do not log to file with a timestamp',
                            action='store_false')
        self.api('plugins.core.commands:command:add')('file',
                                              self.cmd_file,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""toggle datatypes to the console

          if no arguments, data types that are currenty sent to the console will be listed""")
        parser.add_argument('datatype',
                            help='a list of datatypes to toggle',
                            default=[],
                            nargs='*')
        self.api('plugins.core.commands:command:add')('console',
                                              self.cmd_console,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list all datatypes')
        parser.add_argument('match',
                            help='only list datatypes that have this argument in their name',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('types',
                                              self.cmd_types,
                                              parser=parser)

    def _savestate(self, _=None):
        """
        save items not covered by baseplugin class
        """
        self.datatypes_to_client.sync()
        self.datatypes_to_file.sync()
        self.datatypes_to_console.sync()
