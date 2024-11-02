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
from libs.api import API as BASEAPI
from libs.asynch import run_asynch
from plugins.core.log import formatTime_RFC3339_UTC, formatTime_RFC3339

# The modules below are imported to add their functions to the API
from libs import timing
from libs.plugins import reloadutils

# set this to True to log in UTC timezone, False to log in local timezone
BASEAPI.LOG_IN_UTC_TZ = True

# set the start time
BASEAPI.proxy_start_time = datetime.datetime.now(datetime.timezone.utc)

# set the startup flag
BASEAPI.startup = True

# set the logging format (this is overwritten when libs.log.setup_loggers is called)
logging.basicConfig(
    stream=sys.stdout,
    level='INFO',
    format="%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s",
)

# change LOG_IN_UTC_TZ to False if you want to log in local time
# updates the formatter for the logging module
if BASEAPI.LOG_IN_UTC_TZ:
    logging.Formatter.formatTime = formatTime_RFC3339_UTC
else:
    logging.Formatter.formatTime = formatTime_RFC3339

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
        """
        Run the MudProxy application.

        This function instantiates the plugin manager which loads plugins,
        adds events, and creates listeners.
        It also sets the necessary settings based on the provided arguments.
        Finally, it starts the async loop and logs the application's exit.

        Args:
            args (dict): A dictionary of arguments passed to the function.

        Returns:
            None

        Examples:
            mudproxy = MudProxy()
            mudproxy.run({'port': 8080, 'IPv4_address': '127.0.0.1'})
        """
        LogRecord(f"setup_api - setting basepath to: {BASEAPI.BASEPATH}",
                level='info', sources=['mudproxy'])()

        # Load plugins
        LogRecord('Loading Plugin Loader', level='info', sources=['mudproxy'])()

        # instantiate the plugin manager
        from libs.plugins.loader import PluginLoader
        plugin_loader = PluginLoader()

        LogRecord('Plugin Manager - loaded', level='info', sources=['mudproxy'])()

        # load plugins on startup
        plugin_loader.load_plugins_on_startup()

        LogRecord('Plugin Manager - all plugins loaded', level='info', sources=['mudproxy'])()

        # do any post plugin loaded actions
        self.post_plugins_loaded()

        # add events
        self.api.add_events()
        self.api('plugins.core.events:add.event')('ev_bastproxy_proxy_ready', 'mudproxy',
                                            description=['An event raised when the proxy is ready to accept connections'],
                                            arg_descriptions={'None': None})

        args_listen_port: int = args['port']
        plugin_listen_port = self.api('plugins.core.settings:get')('plugins.core.proxy', 'listenport')

        args_ipv4_address = args['IPv4_address']
        plugin_ipv4_address = self.api('plugins.core.settings:get')('plugins.core.proxy', 'ipv4address')

        if args_listen_port != -1 and plugin_listen_port != args_listen_port:
            self.api('plugins.core.settings:change')('plugins.core.proxy', 'listenport', args_listen_port)

        if args_ipv4_address and plugin_ipv4_address != args_ipv4_address:
            self.api('plugins.core.settings:change')('plugins.core.proxy', 'ipv4address', args_ipv4_address)

        # done starting up, set the flag to False and raise the ev_bastproxy_proxy_ready event
        BASEAPI.startup = False

        LogRecord('__main__ - BastProxy ready', level='info', sources=['mudproxy'])()

        self.api('plugins.core.events:raise.event')('ev_bastproxy_proxy_ready', calledfrom='mudproxy')

        from libs.net.listeners import Listeners
        Listeners().create_listeners()

        LogRecord('__main__ - Launching async loop', level='info', sources=['mudproxy'])()

        run_asynch()

        LogRecord('__main__ - exiting', level='info', sources=['mudproxy'])()

    def post_plugins_loaded(self):
        """
        do any actions that are post plugin init here
        """
        pass

if __name__ == "__main__":
    import libs.argp

    # create an ArgumentParser to parse the command line
    parser = libs.argp.ArgumentParser(description='A python mud proxy')
    parser.formatter_class = libs.argp.CustomFormatter

    # create a port option, this sets the variable automatically in the proxy plugin
    parser.add_argument(
        '-p',
        '--port',
        help='the port for the proxy to listen on, \nwill override the plugins.core.proxy listenport setting (default: 9999)',
        default=-1)

    parser.add_argument(
        '-pf',
        '--profile',
        help='profile code',
        action='store_true',
        default=False)

    parser.add_argument(
        '--IPv4-address',
        help='the ip4 address to bind to (default: localhost)',
        default='')

    args = vars(parser.parse_args())

    MP = MudProxy()

    if args['profile']:
        import cProfile
        import pstats
        import io
        with cProfile.Profile() as pr:
            MP.run(args)

            sortby = pstats.SortKey.CUMULATIVE
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats()

            result=s.getvalue()
            # chop the string into a csv-like buffer
            result='ncalls'+result.split('ncalls')[-1]
            result='\n'.join([','.join(line.rstrip().split(None,5)) for line in result.split('\n')])
            # save it to disk
            with open('profile.csv', 'w+') as f:
                f.write(result)
    else:
        MP.run(args)
