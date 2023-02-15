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
import libs.argp as argp
from libs.records import LogRecord
from plugins._baseplugin import BasePlugin

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
        self.api('libs.api:add')('add:error', self._api_add_error)
        self.api('libs.api:add')('get:errors', self._api_get_errors)
        self.api('libs.api:add')('clear:all:errors', self._api_clear_all_errors)

        self.dependencies = []

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

        parser = argp.ArgumentParser(add_help=False,
                                     description='show errors')
        parser.add_argument('number',
                            help='list the last <number> errors',
                            default='-1',
                            nargs='?')
        self.api('plugins.core.commands:command:add')('show',
                                              self.cmd_show,
                                              parser=parser)

        parser = argp.ArgumentParser(add_help=False,
                                     description='clear errors')
        self.api('plugins.core.commands:command:add')('clear',
                                              self.cmd_clear,
                                              parser=parser)

        self.api('plugins.core.events:register:to:event')('ev_bastproxy_proxy_ready', self.proxy_ready)

    # show all errors that happened during startup
    def proxy_ready(self, _=None):
        """
        show all errors that happened during startup
        """
        errors = self.api('plugins.core.errors:get:errors')()

        msg = ['The following errors happened during startup:']
        if errors:
            msg.append('Proxy Errors')
            for i in errors:
                msg.append('')
                msg.append(f"Time: {i['timestamp']}")
                msg.append(f"Error: {i['msg']}")

            LogRecord(msg, level='error', sources=[self.plugin_id, 'mudproxy']).send()


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

    def cmd_show(self, args=None):
        """
        @G%(name)s@w - @B%(cmdname)s@w
          show the error queue
          @CUsage@w: show
        """
        msg = []
        try:
            number = int(args['number'])
        except ValueError:
            msg.append('Please specify a number')
            return False, msg

        errors = self.api('plugins.core.errors:get:errors')()

        if not errors:
            msg.append('There are no errors')
        else:
            if args and number > 0:
                for i in errors[-int(number):]:
                    msg.append('')
                    msg.append(f"Time: {i['timestamp']}")
                    msg.append(f"Error: {i['msg']}")

            else:
                for i in errors:
                    msg.append('')
                    msg.append(f"Time: {i['timestamp']}")
                    msg.append(f"Error: {i['msg']}")

        return True, msg

    def cmd_clear(self, args=None):
        # pylint: disable=unused-argument
        """
        clear errors
        """
        self.api('errors.clear')()

        return True, ['Errors cleared']
