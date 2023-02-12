# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/msg.py
#
# File Description: a plugin to handle messaging in the proxy
#
# By: Bast
"""
This module handles messaging to various places: log files, console, clients, etc
"""
# Standard Library
from __future__ import print_function
import logging
import os

# 3rd Party

# Project
import libs.argp as argp
from libs.record import ToClientRecord
from libs.persistentdict import PersistentDict
from plugins._baseplugin import BasePlugin

NAME = 'Messaging'
SNAME = 'msg'
PURPOSE = 'Handles sending messages to various places: log files, console, clients, etc'
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

        self.log_directory = self.api.BASEDATAPATH / 'logs'

        try:
            os.makedirs(self.save_directory)
        except OSError:
            pass
        self.datatypes = {}
        self.datatypes_to_client = PersistentDict(
            self.save_directory /'datatypes_to_client.txt',
            'c')
        self.datatypes_to_console = PersistentDict(
            self.save_directory / 'datatypes_to_console.txt',
            'c')
        self.datatypes_to_file = PersistentDict(
            self.save_directory / 'datatypes_to_file.txt',
            'c')

        self.colors = {}

        self.log_handlers = {}

        self.colors['error'] = '@x136'

        # new api format
        self.api('libs.api:add')('message', self.api_msg)
        self.api('libs.api:add')('add:datatype', self.api_adddtype)
        self.api('libs.api:add')('toggle:to:console', self.api_toggletoconsole)
        self.api('libs.api:add')('toggle:to:file', self.api_toggletofile)
        self.api('libs.api:add')('toggle:to:client', self.api_toggletoclient)

        # add some default datatypes
        self.api(f"{self.plugin_id}:add:datatype")('default')
        self.api(f"{self.plugin_id}:add:datatype")('frommud')
        self.api(f"{self.plugin_id}:add:datatype")('startup')
        self.api(f"{self.plugin_id}:add:datatype")('shutdown')
        self.api(f"{self.plugin_id}:add:datatype")('error')

        # log some datatypes by default
        self.api(f"{self.plugin_id}:toggle:to:client")('error')
        self.api(f"{self.plugin_id}:toggle:to:console")('error')
        self.api(f"{self.plugin_id}:toggle:to:console")('default')
        self.api(f"{self.plugin_id}:toggle:to:console")('startup')
        self.api(f"{self.plugin_id}:toggle:to:console")('shutdown')

        self.dependencies = ['core.events']

    # add a datatype to the log
    def api_adddtype(self, datatype):
        """  add a datatype
        @Ydatatype@w  = the datatype to add

        this function returns no values"""
        if datatype not in self.datatypes:
            self.datatypes[datatype] = True
            self.datatypes_to_client[datatype] = False
            self.datatypes_to_console[datatype] = False

    # process a message, use send:msg instead for the api
    def api_msg(self, msg, tags=None, level='info'):
        """  send a message
        @Ymsg@w        = This message to send
        @Ydatatype@w   = the type to toggle

        this function returns no values"""
        senttoconsole = False
        senttoclient = False
        if not msg:
            msg = []

        if isinstance(msg, str):
            msg = [msg]

        for dtag in tags:
            if dtag and dtag != 'None' \
                  and dtag != 'default':

                if dtag in self.datatypes_to_file and self.datatypes_to_file[dtag]['logger_name']:
                    loggingfunc = getattr(logging.getLogger(self.datatypes_to_file[dtag]['logger_name']), level)
                    loggingfunc('\n'.join(msg))

                if self.api('libs.api:has')('plugins.core.colors:colorcode:to:ansicode') and \
                        dtag in self.colors:
                    msg = [self.api('plugins.core.colors:colorcode:to:ansicode')(self.colors[dtag] + i) for i in msg if i]

                if dtag in self.datatypes_to_client and self.datatypes_to_client[dtag] and not senttoclient:
                    ToClientRecord(msg).send(__name__ + ':api_msg')
                    senttoclient = True

                if dtag in self.datatypes_to_console and self.datatypes_to_console[dtag] and not senttoconsole:
                    loggingfunc = getattr(logging.getLogger(dtag), level)
                    loggingfunc('\n'.join(msg))
                    senttoconsole = True

    # toggle logging a datatype to the clients
    def api_toggletoclient(self, datatype, flag=True):
        """  toggle a data type to show to clients
        @Ydatatype@w  = the type to toggle, can be multiple (list)
        @Yflag@w      = True to send to clients, false otherwise (default: True)

        this function returns no values"""
        if datatype in self.datatypes_to_client and datatype != 'frommud':
            self.datatypes_to_client[datatype] = flag

        self.api('libs.io:send:msg')(f"setting {datatype} to log to client")

        self.datatypes_to_client.sync()

    # toggle logging datatypes to the clients
    def cmd_client(self, args):
        """
        toggle datatypes shown to client
        """
        tmsg = []
        if args['datatype']:
            for i in args['datatype']:
                if i in self.datatypes_to_client and i != 'frommud':
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
    def api_toggletoconsole(self, datatype, flag=True):
        """  toggle a data type to show to console
        @Ydatatype@w  = the type to toggle
        @Yflag@w      = True to send to console, false otherwise (default: True)

        this function returns no values"""
        if datatype in self.datatypes_to_console and datatype != 'frommud':
            self.datatypes_to_console[datatype] = flag

        self.api('libs.io:send:msg')(f"setting {datatype} to log to console")

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
    def api_toggletofile(self, datatype, timestamp=True):
        """  toggle a data type to show to file
        @Ydatatype@w  = the type to toggle
        @Yflag@w      = True to send to file, false otherwise (default: True)

        this function returns no values"""
        logger_name = datatype + '-log'
        if datatype in self.datatypes_to_file:
            logger = logging.getLogger(logger_name)
            logger.removeHandler(self.log_handlers[datatype])
            del self.datatypes_to_file[datatype]
            self.datatypes_to_file.sync()
            del self.log_handlers[datatype]
            return 'off'
        else:
            logger_file_path = self.api.BASEDATALOGPATH / datatype
            logger_file_handler = logging.handlers.TimedRotatingFileHandler(logger_file_path, when='midnight')
            if timestamp:
                logger_file_handler.formatter = logging.Formatter('%(asctime)s ' + self.api.TIMEZONE + ' : %(name)-11s - %(message)s')
            else:
                logger_file_handler.formatter = logging.Formatter('%(name)-13s - %(message)s')
            logger_file_handler.setLevel(logging.DEBUG)
            logger = logging.getLogger(logger_name)
            logger.addHandler(logger_file_handler)
            logger.propagate = False
            self.datatypes_to_file[datatype] = {'timestamp':timestamp, 'logger_name':logger_name}
            self.datatypes_to_file.sync()
            self.log_handlers[datatype] = logger_file_handler
            return 'on'

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
        tmsg = []
        tmsg.append('Data Types')
        tmsg.append('-' *  30)
        match = args['match']
        tkeys = self.datatypes.keys()
        tkeys = sorted(tkeys)
        for i in tkeys:
            if not match or match in i:
                tmsg.append(i)
        return True, tmsg

    def logmud(self, args):
        """
        log all data from the mud
        """
        if 'frommud' in self.datatypes_to_file and self.datatypes_to_file['frommud']['file']:
            if args['eventname'] == 'ev_libs.net.mud_from_mud_event':
                data = args['noansi']
            elif args['eventname'] == 'ev_libs.io_to_mud_event':
                data = 'tomud: ' + args['data'].strip()
            self.logtofile(data, 'frommud', stripcolor=False)
        return args

    def initialize(self):
        """
        initialize external stuff
        """
        BasePlugin.initialize(self)

        #print('log api before adding', self.api.api)

        #print('log api after adding', self.api.api)
        self.api('plugins.core.events:register:to:event')('ev_libs.net.mud_from_mud_event', self.logmud)
        self.api('plugins.core.events:register:to:event')('ev_libs.io_to_mud_event', self.logmud)
        self.api('plugins.core.events:register:to:event')(f"ev_{self.plugin_id}_savestate", self._savestate)

        parser = argp.ArgumentParser(add_help=False,
                                     description="""toggle datatypes to clients

          if no arguments, data types that are currenty sent to clients will be listed""")
        parser.add_argument('datatype',
                            help='a list of datatypes to toggle',
                            default=[],
                            nargs='*')
        self.api('plugins.core.commands:command:add')('client',
                                              self.cmd_client,
                                              lname='Logger',
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
                                              lname='Logger',
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
                                              lname='Logger',
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='list all datatypes')
        parser.add_argument('match',
                            help='only list datatypes that have this argument in their name',
                            default='',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('types',
                                              self.cmd_types,
                                              lname='Logger',
                                              parser=parser)

        #print('log loaded')

    def _savestate(self, _=None):
        """
        save items not covered by baseplugin class
        """
        self.datatypes_to_client.sync()
        self.datatypes_to_file.sync()
        self.datatypes_to_console.sync()
