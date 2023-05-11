# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/log.py
#
# File Description: a plugin to change logging settings
#
# By: Bast
"""
This module handles changing logging settings

see info/logging_notes.txt for more information about logging
"""

import contextlib
# Standard Library
import logging
import os
import numbers

# 3rd Party

# Project
import libs.argp as argp
from libs.persistentdict import PersistentDict
from plugins._baseplugin import BasePlugin
from libs.records import LogRecord, RMANAGER

NAME = 'Logging'
SNAME = 'log'
PURPOSE = 'Handles changing and testing of logging configuration'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

def get_toplevel(logger_name):
    """
    get the toplevel logger from a name
    """
    return logger_name.split(':')[0] if ":" in logger_name else logger_name

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
        self.logtype_col_length = 35

        self.type_counts = {}

        with contextlib.suppress(OSError):
            os.makedirs(self.save_directory)
        self.handlers = {}
        self.handlers['client'] = PersistentDict(self.plugin_id,
            self.save_directory /'logtypes_to_client.txt',
            'c')
        self.handlers['console'] = PersistentDict(self.plugin_id,
            self.save_directory / 'logtypes_to_console.txt',
            'c')
        self.handlers['file'] = PersistentDict(self.plugin_id,
            self.save_directory / 'logtypes_to_file.txt',
            'c')

        self.api(f"{self.plugin_id}:setting.add")('color_error', '@x136', 'color',
                                'the color for error messages')
        self.api(f"{self.plugin_id}:setting.add")('color_warning', '@y', 'color',
                                'the color for warning messages')
        self.api(f"{self.plugin_id}:setting.add")('color_info', '@w', 'color',
                                'the color for info messages')
        self.api(f"{self.plugin_id}:setting.add")('color_debug', '@x246', 'color',
                                'the color for debug messages')
        self.api(f"{self.plugin_id}:setting.add")('color_critical', '@r', 'color',
                                'the color for critical messages')

        # new api format
        self.api('libs.api:add')(self.plugin_id, 'set.log.to.console', self.api_set_log_to_console)
        self.api('libs.api:add')(self.plugin_id, 'set.log.to.file', self.api_set_log_to_file)
        self.api('libs.api:add')(self.plugin_id, 'set.log.to.client', self.api_set_log_to_client)
        self.api('libs.api:add')(self.plugin_id, 'can.log.to.console', self._api_can_log_to_console)
        self.api('libs.api:add')(self.plugin_id, 'can.log.to.file', self._api_can_log_to_file)
        self.api('libs.api:add')(self.plugin_id, 'can.log.to.client', self._api_can_log_to_client)
        self.api('libs.api:add')(self.plugin_id, 'get.level.color', self._api_get_level_color)
        self.api('libs.api:add')(self.plugin_id, 'add.log.count', self._api_add_log_count)

    def _api_add_log_count(self, logtype, level):
        """
        add a log count
        """
        logger_name = get_toplevel(logtype)
        if logger_name not in self.type_counts:
            self.type_counts[logger_name] = {
                'debug': 0,
                'info': 0,
                'warning': 0,
                'error': 0,
                'critical': 0,
            }
        if level not in self.type_counts[logger_name]:
            self.type_counts[logger_name][level] = 0
        self.type_counts[logger_name][level] += 1

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
        logger_name = get_toplevel(logger)
        if logger_name not in self.handlers['console']:
            self.handlers['console'][logger_name] = 'info'
            self.handlers['console'].sync()

        convlevel = getattr(logging, self.handlers['console'][logger_name].upper(), logging.INFO)
        return level >= convlevel

    def _api_can_log_to_file(self, logger, level):
        """
        check if a logger can log to the file

        if the logger hasn't been seen, it will default to logging.INFO
        """
        logger_name = get_toplevel(logger)
        if logger_name not in self.handlers['file']:
            self.handlers['file'][logger_name] = 'info'
            self.handlers['file'].sync()

        convlevel = getattr(logging, self.handlers['file'][logger_name].upper(), logging.INFO)
        return level >= convlevel

    def _api_can_log_to_client(self, logger, level):
        """
        check if a logger can log to the client

        if the logger hasn't been seen, do not allow logging to the client
        logging to the client must be explicitly enabled
        """
        logger_name = get_toplevel(logger)
        return logger_name in self.handlers['client'] and level >= getattr(
            logging, self.handlers['client'][logger_name].upper(), logging.INFO)

    # toggle logging a logtype to the clients
    def api_set_log_to_client(self, logtype, level: str='info', flag=True):
        """  toggle a log type to show to clients
        @Ylogtype@w   = the type to toggle, can be multiple (list)
        @Yflag@w      = True to send to clients, false otherwise (default: True)

        this function returns no values"""
        LogRecord(f"api_set_log_to_client: {logtype} {level} {flag}",
                    level='debug', sources=[self.plugin_id])()

        logger_name = get_toplevel(logtype)
        if isinstance(level, numbers.Number):
            level = logging.getLevelName(level).lower()
        if not level:
            LogRecord(f"api_toggletoclient: invalid log level {level}",
                      level='error', sources=[self.plugin_id, logger_name])()
            return

        if flag and logger_name not in self.handlers['client']:
            self.handlers['client'][logger_name] = level
            LogRecord(f"setting {logger_name} to log to client at level {level}",
                      level='debug', sources=[self.plugin_id, logger_name])()
        elif not flag and logger_name in self.handlers['client']:
            del(self.handlers['client'][logger_name])
            LogRecord(f"removing {logger_name} logging to client {level}",
                      level='debug', sources=[self.plugin_id, logger_name])()

        self.handlers['client'].sync()

    # toggle logging logtypes to the clients
    def _command_client(self):
        """
        toggle logtypes shown to client
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        level = args['level']
        if args['logtype']:
            remove = not args['remove']
            for i in args['logtype']:
                logger_name = get_toplevel(i)
                self.api(f"{self.plugin_id}:set.log.to.client")(logger_name, level=level, flag=remove)
                if logger_name in self.handlers['client']:
                    tmsg.append(f"setting {logger_name} to log to client at level {level}")
                else:
                    tmsg.append(f"no longer sending {logger_name} to client")

            self.handlers['client'].sync()
            return True, tmsg

        tmsg.extend(
            (
                'Current types going to client',
                f"{'logtype':<{self.logtype_col_length}}{'level':<}",
            )
        )
        tmsg.extend(
            f"{i:<{self.logtype_col_length}}{self.handlers['client'][i]:<}"
            for i in self.handlers['client']
            if self.handlers['client'][i]
        )
        return True, tmsg

    # toggle logging a logtype to the console
    def api_set_log_to_console(self, logtype, level='info'):
        """  toggle a log type to show to console
        @Ylogtype@w   = the type to toggle
        @Yflag@w      = True to send to console, false otherwise (default: True)

        this function returns no values"""
        LogRecord(f"api_set_log_to_console: {logtype} {level}",
                    level='debug', sources=[self.plugin_id])()

        logger_name = get_toplevel(logtype)
        if isinstance(level, numbers.Number):
            level = logging.getLevelName(level).lower()
        if not level:
            LogRecord(f"api_set_log_to_console: invalid log level {level}",
                      level='error', sources=[self.plugin_id, logger_name])()
            return

        self.handlers['console'][logger_name] = level
        LogRecord(f"setting {logger_name} to log to console at level {level}",
                  level='debug', sources=[self.plugin_id, logger_name])()

        self.handlers['console'].sync()

    # toggle logging logtypes to the console
    def _command_console(self):
        """
        toggle logtypes to the console
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        if args['logtype']:
            for i in args['logtype']:
                logger_name = get_toplevel(i)
                if logger_name not in self.handlers['console']:
                    self.handlers['console'][logger_name] = 'info'
                if self.handlers['console'][logger_name] == 'info':
                    self.api(f"{self.plugin_id}:set.log.to.console")(logger_name, level='debug')
                    tmsg.append(f"setting {logger_name} to log to console at level 'debug'")
                else:
                    self.api(f"{self.plugin_id}:set.log.to.console")(logger_name, level='info')
                    tmsg.append(f"setting {logger_name} to log to console at default level 'info'")

            self.handlers['console'].sync()
            return True, tmsg

        tmsg.extend(
            (
                'Current types going to console',
                f"{'logtype':<{self.logtype_col_length}}{'level':<}",
            )
        )
        tmsg.extend(
            f"{i:<{self.logtype_col_length}}{self.handlers['console'][i]:<}"
            for i in self.handlers['console']
            if self.handlers['console'][i]
        )
        return True, tmsg

    # toggle logging a logtype to a file
    def api_set_log_to_file(self, logtype, level='info'):
        """  toggle a log type to show to file
        @Ylogtype@w   = the type to toggle
        @Yflag@w      = True to send to file, false otherwise (default: True)

        this function returns no values"""
        if isinstance(level, numbers.Number):
            level = logging.getLevelName(level).lower()
        if not level:
            LogRecord(f"api_set_log_to_file: invalid log level {level}",
                      level='error', sources=[self.plugin_id, logtype])()
            return

        logger_name = get_toplevel(logtype)
        self.handlers['file'][logger_name] = level
        LogRecord(f"setting {logger_name} to log to file at level {level}",
                  level='debug', sources=[self.plugin_id, logger_name])()

        self.handlers['file'].sync()

    # toggle a logtype to log to a file
    def _command_file(self):
        """
        toggle a logtype to log to a file
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        tmsg = []
        if args['logtype']:
            for i in args['logtype']:
                logger_name = get_toplevel(i)
                if logger_name not in self.handlers['file']:
                    self.handlers['file'][logger_name] = 'info'
                if self.handlers['file'][logger_name] == 'info':
                    self.api(f"{self.plugin_id}:set.log.to.file")(logger_name, level='debug')
                    tmsg.append(f"setting {logger_name} to log to file at level 'debug'")
                else:
                    self.api(f"{self.plugin_id}:set.log.to.file")(logger_name, level='info')
                    tmsg.append(f"setting {logger_name} to log to file at default level 'info'")

            self.handlers['file'].sync()
            return True, tmsg

        tmsg.extend(
            (
                'Current types going to file',
                f"{'logtype':<{self.logtype_col_length}}{'level':<}",
            )
        )
        tmsg.extend(
            f"{i:<{self.logtype_col_length}}{self.handlers['file'][i]:<}"
            for i in self.handlers['file']
            if self.handlers['file'][i]
        )
        return True, tmsg

    # show all types
    def _command_types(self):
        """
        list log types
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        types = []
        types.extend(self.handlers['client'].keys())
        types.extend(self.handlers['console'].keys())
        types.extend(self.handlers['file'].keys())
        types = sorted(set(types))
        tmsg = [
            'Statistics are only tracked after the log plugin is loaded',
            'so they will not be accurate for all log types.',
            '-' * 79,
        ]
        match = args['match']

        if match:
            types = [i for i in types if match in i]

        if types:
            tmsg.extend(
                (
                    f"{'logtype':<{self.logtype_col_length}} : {'debug':<5} {'info':<5} {'warning':<7} {'error':<5} {'critical':<8}",
                    '-' * 79,
                )
            )
            for i in types:
                if i in self.type_counts:
                    tmsg.append(f"{i:<{self.logtype_col_length}} : {self.type_counts[i]['debug']:<5} {self.type_counts[i]['info']:<5} {self.type_counts[i]['warning']:<7} {self.type_counts[i]['error']:<5} {self.type_counts[i]['critical']:<8}")
                else:
                    tmsg.append(f"{i:<{self.logtype_col_length}} : {'0':<5} {'0':<5} {'0':<7} {'0':<5} {'0':<8}")
        else:
            tmsg.append(f"No matches found for {match}")

        return True, tmsg


    def _command_test(self):
        """
        send test records to logging facilities
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        logtype = args['logtype']
        message = args['message']
        level = args['loglevel']

        tmsg = [f"'{message}' sent to '{logtype}' as level '{level}'"]

        lr = LogRecord(message, level=level, sources=[logtype])
        lr()

        tmsg.extend(
            (
                f"Console: {lr.wasemitted['console']}",
                f"File: {lr.wasemitted['file']}",
                f"Client: {lr.wasemitted['client']}",
            )
        )
        return True, tmsg

    def _command_clean(self):
        """
        remove log types that have not been used
        """
        types = []
        types.extend(self.handlers['client'].keys())
        types.extend(self.handlers['console'].keys())
        types.extend(self.handlers['file'].keys())
        types = sorted(set(types))

        remove = []

        for i in types:
            if i not in self.type_counts:
                remove.append(i)
            elif max(self.type_counts[i].values()) <= 0:
                remove.append(i)

        tmsg = ['Removed the following types:']
        for i in remove:
            tmsg.append(i)
            if i in self.handlers['client']:
                del(self.handlers['client'][i])
            if i in self.handlers['console']:
                del(self.handlers['console'][i])
            if i in self.handlers['file']:
                del(self.handlers['file'][i])
            if i in self.type_counts:
                del(self.type_counts[i])

        self.handlers['file'].sync()
        self.handlers['client'].sync()
        self.handlers['console'].sync()

        return True, tmsg

    def initialize(self):
        """
        initialize external stuff
        """
        BasePlugin.initialize(self)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""toggle logtypes to clients

          if no arguments, log types that are currenty sent to clients will be listed""")
        parser.add_argument('logtype',
                            help='a list of logtypes to toggle',
                            default=[],
                            nargs='*')
        parser.add_argument('-l',
                            '--level',
                            help='the level to log at',
                            default='info',
                            choices=['debug', 'info', 'warning', 'error', 'critical'])
        parser.add_argument('-r',
                            '--remove',
                            help='remove the logtype from logging to the client',
                            action='store_true',
                            default=False)

        self.api('plugins.core.commands:command.add')('client',
                                              self._command_client,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""toggle logtype to log to a file

          the file will be located in the data/logs/<logtype> directory

          if no arguments, types that are sent to file will be listed""")
        parser.add_argument('logtype',
                            help='the logtype to toggle',
                            default='list',
                            nargs='?')
        parser.add_argument('-n',
                            '--notimestamp',
                            help='do not log to file with a timestamp',
                            action='store_false')
        self.api('plugins.core.commands:command.add')('file',
                                              self._command_file,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""change the level of logging for a logtype to the console
          this will toggle the logtype between 'info' and 'debug'

          if no arguments, log types that are currenty sent to the console will be listed""")
        parser.add_argument('logtype',
                            help='a list of logtypes to toggle',
                            default=[],
                            nargs='*')
        self.api('plugins.core.commands:command.add')('console',
                                              self._command_console,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list all logtypes')
        parser.add_argument('match',
                            help='only list logtypes that have this argument in their name',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command.add')('types',
                                              self._command_types,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""test logging facilities""")
        parser.add_argument('message',
                            help='the text to log')
        parser.add_argument('-l',
                            '--logtype',
                            help='the facility to test',
                            required=True)
        parser.add_argument('-ll',
                            '--loglevel',
                            help='the level for the test',
                            default='info',
                            choices=['debug', 'info', 'warning', 'error', 'critical'],
                            required=True)
        self.api('plugins.core.commands:command.add')('test',
                                              self._command_test,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""clean up log types

          will remove any log types that have not been used""")
        self.api('plugins.core.commands:command.add')('clean',
                                              self._command_clean,
                                              parser=parser)

    def savestate(self):
        """
        save items not covered by baseplugin class
        """
        super().savestate()
        self.handlers['client'].sync()
        self.handlers['file'].sync()
        self.handlers['console'].sync()
