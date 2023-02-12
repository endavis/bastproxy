# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/io.py
#
# File Description: setup messaging for use in the proxy
#
# By: Bast
"""
handle output and input functions, adds items under the send api

The send to client and send to mud functions are the only ones that
will interact with the asyncio event loop, so all data sent to the
mud will go through the apis libs.io:send:mud
"""

# Standard Library
import time
import sys
import traceback
import re
import logging
import asyncio

# Third Party

# Project
from libs.api import API

class ProxyIO(object):  # pylint: disable=too-few-public-methods
    """
    class for IO in the proxy
      APIs for this class
       'send:msg'       : send data through the messaging system for
                            logging purposes
       'send:error'     : send an error
       'send:traceback' : send a traceback
       'send:mud'       : send data to the mud
       'send:execute'   : send data through the parser
    """
    def __init__(self):
        """
        initialize the class
        """
        self.current_trace = None
        self.api = API()

        self.api('libs.api:add')('libs.io', 'send:msg', self._api_msg)
        self.api('libs.api:add')('libs.io', 'send:error', self._api_error)
        self.api('libs.api:add')('libs.io', 'send:traceback', self._api_traceback)
        self.api('libs.api:add')('libs.io', 'send:mud', self._api_tomud)
        self.api('libs.api:add')('libs.io', 'send:execute', self._api_execute)
        self.api('libs.api:add')('libs.io', 'trace:add:execute', self._api_trace_add_execute)

    def _api_trace_add_execute(self, plugin_id, flag, info=None, data=None,
                               original_data=None, new_data=None, callstack=None):
        """
        add a trace when going through execute
          'plugin_id'     : The plugin that made the change
          'flag'          : The type of trace
          'info'          : Info about the trace
          'original data' : The original data
          'new data'      : The modified data
        """
        if self.current_trace:
            trace = {}
            trace['plugin_id'] = plugin_id
            trace['flag'] = flag
            if info:
                trace['info'] = info
            if original_data:
                trace['original_data'] = original_data
            if new_data:
                trace['new_data'] = new_data
            if data:
                trace['data'] = data
            if callstack:
                trace['callstack'] = callstack
            self.current_trace['changes'].append(trace)

    # send a message
    def _api_msg(self, message, level='info', primary=None, secondary=None):
        """  send a message through the log plugin
          @Ymessage@w        = This message to send
          @Yprimary@w    = the primary data tag of the message (default: None)
          @Ysecondary@w  = the secondary data tag of the message
                              (default: None)

        If a plugin called this function, it will be automatically added to the tags

        this function returns no values"""
        tags = []
        plugin = self.api('libs.api:get:caller:plugin')(ignore_plugin_list=['core.plugins'])

        tags.extend(self.api('libs.api:get:plugins:from:stack:list')(ignore_plugin_list=['core.plugins']))

        if not isinstance(secondary, list):
            tags.append(secondary)
        else:
            tags.extend(secondary)

        ttags = set(tags) # take out duplicates
        tags = list(ttags)

        if primary:
            if primary in tags:
                tags.remove(primary)
            tags.insert(0, primary)

        if plugin:
            if not primary:
                if plugin in tags:
                    tags.remove(plugin)
                tags.insert(0, plugin)
            else:
                if plugin not in tags:
                    tags.append(plugin)

        if not tags:
            print(f"Did not get any tags for {message}")
            tags = ['Unknown']

        try:
            self.api('plugins.core.msg:message')(message, level=level, tags=tags)
        except (AttributeError, RuntimeError):
            loggingfunc = getattr(logging.getLogger(primary or plugin), level)
            loggingfunc(message)

    # write and format a traceback
    def _api_traceback(self, message=None):
        """  handle a traceback
          @Ymessage@w  = the message to put into the traceback

        this function returns no values"""
        if not message:
            message = []

        if isinstance(message, str):
            message = [message]

        message.extend(traceback.format_exception(sys.exc_info()[0],
                                         sys.exc_info()[1],
                                         sys.exc_info()[2]))

        message = [i.rstrip('\n').rstrip('\r') for i in message]
        new_message = []
        for message in message:
            if message.find('\n'):
                new_message.extend(message.split('\n'))
            else:
                new_message.append(message)

        self.api('libs.io:send:error')(new_message)

    # write and format an error
    def _api_error(self, message=None, secondary=None):
        """  handle an error
          @Ytext@w      = The error to handle
          @Ysecondary@w = Other datatypes to flag this data

        this function returns no values"""

        if not message:
            message = []

        if isinstance(message, str):
            message = [message]

        message_list = []

        for i in message:
            if self.api('libs.api:has')('plugins.core.colors:colorcode:to:ansicode'):
                message_list.append(f"@x136{i}@w")
            else:
                message_list.append(i)

        self.api('libs.io:send:msg')(message_list, level='error', primary='error', secondary=secondary)

        try:
            self.api('plugins.core.errors:add')(time.strftime(self.api.time_format,
                                                      time.localtime()),
                                        message)
        except (AttributeError, TypeError):
            pass

    # execute a command through the interpreter, most data goes through this
    def _api_execute(self, command, fromclient=False, showinhistory=True): # pylint: disable=too-many-branches
        """  execute a command through the interpreter
        It will first check to see if it is an internal command, and then
        send to the mud if not.
          @Ycommand@w      = the command to send through the interpreter

        this function returns no values"""
        self.api('libs.io:send:msg')(f"execute: got command {repr(command)}",
                                     primary='inputparse')

        tracing = False
        if not self.current_trace:
            tracing = True
            self.current_trace = {}
            self.current_trace['fromclient'] = False
            self.current_trace['internal'] = True
            self.current_trace['changes'] = []
            self.current_trace['showinhistory'] = showinhistory
            self.current_trace['addedtohistory'] = False
            self.current_trace['originalcommand'] = command.strip()
            self.current_trace['fromplugin'] = self.api('libs.api:get:caller:plugin')()

            if fromclient:
                self.current_trace['fromclient'] = True
                self.current_trace['internal'] = False

            self.api('plugins.core.events:raise:event')('ev_libs.io_execute_trace_started', self.current_trace,
                                                calledfrom='libs.io')

        if command == '\r\n':
            self.api('libs.io:send:msg')(f"sending {repr(command)} (cr) to the mud",
                                         primary='inputparse')
            self.api('plugins.core.events:raise:event')('ev_libs.io_to_mud_event', {'data':command,
                                                                            'dtype':'fromclient',
                                                                            'showinhistory':showinhistory},
                                                calledfrom='libs.io')
        else:

            command = command.strip()

            commands = command.split('\r\n')
            if len(commands) > 1:
                self.api('libs.io:trace:add:execute')('libs.io', 'Splitcr',
                                                      info=f"split command: '{command}' into: '{', '.join(commands)}")

            for current_command in commands:
                newdata = self.api('plugins.core.events:raise:event')('ev_libs.io_execute',
                                                              {'fromdata':current_command,
                                                               'fromclient':fromclient,
                                                               'internal':not fromclient,
                                                               'showinhistory':showinhistory},
                                                              calledfrom='libs.io')

                if 'fromdata' in newdata:
                    current_command = newdata['fromdata']
                    current_command = current_command.strip()

                if current_command:
                    # split the command if it has the command seperator in it
                    # and run each one through execute again
                    if self.api.command_split_regex:
                        split_data = re.split(self.api.command_split_regex, current_command)
                    else:
                        split_data = []
                    if len(split_data) > 1:
                        self.api('libs.io:send:msg')(f"broke {current_command} into {split_data}",
                                                     primary='inputparse')
                        self.api('libs.io:trace:add:execute')('libs.io', 'SplitChar',
                                                              data=f"split command: '{current_command}' into: '{', '.join(split_data)}'")

                        for cmd in split_data:
                            self.api('libs.io:send:execute')(cmd, showinhistory=showinhistory)

                    # the command did not have a command seperator
                    else:
                        # take out double command seperators and replaces them with a single one before
                        # sending the data to the mud
                        current_command = current_command.replace('||', '|')
                        if current_command[-1] != '\n':
                            current_command = ''.join([current_command, '\n'])
                        self.api('libs.io:send:msg')(f"sending {current_command.strip()} to the mud",
                                                     primary='inputparse')
                        self.api('plugins.core.events:raise:event')('ev_libs.io_to_mud_event',
                                                            {'data':current_command,
                                                             'dtype':'fromclient',
                                                             'showinhistory':showinhistory},
                                                            calledfrom='libs.io')

        if tracing:
            self.api('plugins.core.events:raise:event')('ev_libs.io_execute_trace_finished', self.current_trace,
                                                calledfrom='libs.io')
            self.current_trace = None

    # send data directly to the mud
    def _api_tomud(self, data, raw=False, dtype='fromclient'):
        """ send data directly to the mud

        This does not go through the interpreter
          @Ydata@w     = the data to send
          @Yraw@w      = don't do anything to this data
          @Ydtype@w    = the datatype

        this function returns no values
        """

        if not raw and data and data[-1] != '\n':
            data = ''.join([data, '\n'])
        self.api('plugins.core.events:raise:event')('ev_libs.io_to_mud_event',
                                            {'data':data,
                                             'dtype':dtype,
                                             'raw':raw},
                                            calledfrom='libs.io')

IO = ProxyIO()
