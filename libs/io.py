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
import re

# Third Party

# Project
from libs.api import API
from libs.records import LogRecord

class ProxyIO(object):  # pylint: disable=too-few-public-methods
    """
    class for IO in the proxy
      APIs for this class
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
        self.api = API(owner_id=__name__)

        self.api('libs.api:add')('libs.io', 'send:mud', self._api_tomud)
        self.api('libs.api:add')('libs.io', 'send:execute', self._api_execute)
        self.api('libs.api:add')('libs.io', 'trace:add:execute', self._api_trace_add_execute)

    def _api_trace_add_execute(self, owner_id, flag, info=None, data=None,
                               original_data=None, new_data=None, callstack=None):
        """
        add a trace when going through execute
          'owner_id'     : The plugin that made the change
          'flag'          : The type of trace
          'info'          : Info about the trace
          'original data' : The original data
          'new data'      : The modified data
        """
        if self.current_trace:
            trace = {}
            trace['owner_id'] = owner_id
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

    # execute a command through the interpreter, most data goes through this
    def _api_execute(self, command, fromclient=False, showinhistory=True): # pylint: disable=too-many-branches
        """  execute a command through the interpreter
        It will first check to see if it is an internal command, and then
        send to the mud if not.
          @Ycommand@w      = the command to send through the interpreter

        this function returns no values"""
        LogRecord(f"_api_execute: got {command}",
                  level='debug', sources=[__name__]).send()

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
            self.current_trace['owner_id'] = self.api('libs.api:get:caller:owner')()

            if fromclient:
                self.current_trace['fromclient'] = True
                self.current_trace['internal'] = False

            self.api('plugins.core.events:raise:event')('ev_libs.io_execute_trace_started', self.current_trace,
                                                calledfrom='libs.io')

        if command == '\r\n':
            LogRecord('_api_execute: sending cr to the mud',
                      level='debug', sources=[__name__]).send()
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
                        LogRecord(f"_api_execute: split command: '{current_command}' into: '{', '.join(split_data)}",
                                  level='debug', sources=[__name__]).send()
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
                        LogRecord(f"_api_execute: sending {current_command.strip()} to the mud",
                                  level='debug', sources=[__name__]).send()
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
