#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Project: Bast's MUD Proxy
# Filename: mudproxy.py
#
# File Description: This is the main file for the MUD Proxy.
#
# By: Bast/Jubelo
"""
    Mud Proxy that supports multiple clients logged into a single user on a MUD.

    It will support clients that can interact with the mud as well as clients that can only see output.

    It will support multiple MUD protocols, such as GMCP, MCCP2, etc.
"""

# Standard Library
import logging
import datetime
import os
import sys
from pathlib import Path

# Third Party

# Project
from libs.records import LogRecord
from libs.log import setup_loggers
from libs.api import API as BASEAPI
from libs.net import server
from libs.asynch import run_asynch

# The modules below are imported to add their functions to the API
from libs import io
from libs import timing

# set the logging format (this is overwritten when libs.log.setup_loggers is called)
logging.basicConfig(stream=sys.stdout,
                    level='INFO',
                    format="%(asctime)s " + BASEAPI.TIMEZONE + " : %(levelname)-9s - %(name)-22s - %(message)s")

# set the start time
BASEAPI.proxy_start_time = datetime.datetime.now(datetime.timezone.utc)

# set the startup flag
BASEAPI.startup = True

# set the timezone
tzinfo = BASEAPI.proxy_start_time.tzinfo
if tzinfo:
    BASEAPI.TIMEZONE = tzinfo.tzname(BASEAPI.proxy_start_time) or ''

# set the base path from the parent of the current file
npath = Path(__file__).resolve()
BASEAPI.BASEPATH = npath.parent

# set the paths based on where the executable is
BASEAPI.BASEDATAPATH = BASEAPI.BASEPATH / 'data'
BASEAPI.BASEDATAPLUGINPATH = BASEAPI.BASEDATAPATH / 'plugins'
BASEAPI.BASEDATALOGPATH = BASEAPI.BASEDATAPATH / 'logs'
BASEAPI.BASEPLUGINPATH = BASEAPI.BASEPATH / 'plugins'

os.makedirs(BASEAPI.BASEDATAPATH, exist_ok=True)
os.makedirs(BASEAPI.BASEDATALOGPATH, exist_ok=True)
os.makedirs(BASEAPI.BASEDATAPLUGINPATH, exist_ok=True)

class MudProxy:
    """
    The main class for the MUD Proxy
    """
    def __init__(self):
        """
        initialize the class
        """
        self.api = BASEAPI(owner_id='mudproxy')

    def run(self, args):
        LogRecord(f"setup_api - setting basepath to: {BASEAPI.BASEPATH}",
                level='info', sources=['mudproxy']).send()

        # setup file logging and network data logging
        setup_loggers(logging.DEBUG)

        # initialize all plugins
        LogRecord('Plugin Manager - loading', level='info', sources=['mudproxy']).send()

        # instantiate the plugin manager
        from plugins._manager import PluginMgr
        plugin_manager = PluginMgr()

        # initialize the plugin manager which will load plugins
        plugin_manager.initialize()
        LogRecord('Plugin Manager - loaded', level='info', sources=['mudproxy']).send()

        # do any post plugin init actions
        self.post_plugins_init()

        # add events
        self.api.add_events()
        self.api('plugins.core.events:add:event')('ev_bastproxy_proxy_ready', 'bastproxy',
                                            description='An event to be raised when the proxy is ready to accept connections',
                                            arg_descriptions={'None': None})

        # done starting up, set the flag to False and raise the ev_bastproxy_proxy_ready event
        BASEAPI.startup = False
        self.api('plugins.core.events:raise:event')('ev_bastproxy_proxy_ready', calledfrom='bastproxy')

        telnet_port: int = args['port']
        LogRecord(f"__main__ - Creating proxy Telnet listener on port {telnet_port}", level='info', sources=['mudproxy']).send()

        # import the client handler here so that the server can be created
        import libs.net.client

        self.api('libs.asynch:task:add')(
            server.create_server(
                host='localhost',
                port=telnet_port,
                shell=libs.net.client.client_telnet_handler,
                connect_maxwait=0.5,
                timeout=3600,
            ), 'Proxy Telnet Listener')

        LogRecord('__main__ - Launching proxy loop', level='info', sources=['mudproxy']).send()

        run_asynch()

        LogRecord('__main__ - exiting', level='info', sources=['mudproxy']).send()

    def post_plugins_init(self):
        """
        do any actions that are post plugin init here
        """
        # add the IO manager
        from libs.io import IO
        self.api('plugins.core.managers:add')('libs.io', IO)

if __name__ == "__main__":
    import libs.argp

    # create an ArgumentParser to parse the command line
    parser = libs.argp.ArgumentParser(description='A python mud proxy')

    # create a port option, this sets the variable automatically in the proxy plugin
    parser.add_argument(
        '-p',
        '--port',
        help='the port for the proxy to listen on',
        default=9000)

    args = vars(parser.parse_args())

    MP = MudProxy()
    MP.run(args)
