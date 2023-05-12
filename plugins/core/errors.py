# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/errors.py
#
# File Description: a plugin to handle errors
#
# By: Bast
"""
This plugin shows and clears errors seen during plugin execution
"""
# Standard Library

# 3rd Party

# Project
from libs.records import LogRecord
from plugins._baseplugin import BasePlugin
from libs.commands import AddParser, AddArgument

NAME = 'Error Plugin'
SNAME = 'errors'
PURPOSE = 'show and manage errors'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

class Plugin(BasePlugin):
    """
    a plugin to handle errors
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the instance
        """
        super().__init__(*args, **kwargs)

        self.errors = []

        # new api format
        self.api('libs.api:add')(self.plugin_id, 'add.error', self._api_add_error)
        self.api('libs.api:add')(self.plugin_id, 'get.errors', self._api_get_errors)
        self.api('libs.api:add')(self.plugin_id, 'clear.all.errors', self._api_clear_all_errors)

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        self.api('plugins.core.events:register.to.event')('ev_bastproxy_proxy_ready', self.evc_proxy_ready)

    # show all errors that happened during startup
    def evc_proxy_ready(self):
        """
        show all errors that happened during startup
        """
        if errors := self.api('plugins.core.errors:get.errors')():
            msg = ['The following errors happened during startup:', 'Proxy Errors']
            for i in errors:
                msg.extend(('',
                            f"Time  : {i['timestamp']}",
                            f"Error : {i['msg']}"))
            LogRecord(msg, level='error', sources=[self.plugin_id, 'mudproxy'])()


    # add an error to the list
    def _api_add_error(self, timestamp, error):
        """add an error

        this function adds an error to the list
        """
        self.errors.append({'timestamp':timestamp,
                            'msg':error})

    # get the errors that have been seen
    def _api_get_errors(self):
        """ get errors

        this function has no arguments

        this function returns the list of errors
        """
        return self.errors

    # clear errors
    def _api_clear_all_errors(self):
        """ clear errors

        this function has no arguments

        this function returns no values
        """
        self.errors = []

    @AddParser(description='show errors')
    @AddArgument('number',
                            help='list the last <number> errors',
                            default='-1',
                            nargs='?')
    def _command_show(self):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          show the error queue
          @CUsage@w: show
        """
        args = self.api('plugins.core.commands:get.current.command.args')()
        msg = []
        try:
            number = int(args['number'])
        except ValueError:
            msg.append('Please specify a number')
            return False, msg

        if errors := self.api('plugins.core.errors:get.errors')():
            if args and number > 0:
                for i in errors[-number:]:
                    msg.extend(('', f"Time  : {i['timestamp']}",
                                    f"Error : {i['msg']}"))
            else:
                for i in errors:
                    msg.extend(('', f"Time   : {i['timestamp']}",
                                    f"Error  : {i['msg']}"))
        else:
            msg.append('There are no errors')
        return True, msg

    @AddParser(description='clear errors')
    def _command_clear(self):
        """
        clear errors
        """
        self.api('errors.clear')()

        return True, ['Errors cleared']

