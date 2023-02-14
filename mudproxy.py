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
import asyncio
import logging
import signal
import time
import os
import sys
from pathlib import Path

# Third Party

# Project
import libs.log
import libs.net.client
import libs.argp
from libs.task_logger import create_task
from libs.api import API as BASEAPI
from libs.net import server
from libs.record import LogRecord

# import io so the "send" functions are added to the api
from libs import io      # pylint: disable=unused-import
# import timing so the "timing" functions are added to the api
from libs import timing


logging.basicConfig(stream=sys.stdout,
                    level='INFO',
                    format=f"%(asctime)s {time.strftime('%z')} : %(name)-12s - %(levelname)-9s - %(message)s")

API = BASEAPI()
API.__class__.proxy_start_time = time.localtime()
API.__class__.startup = True

BASEAPI.TIMEZONE = time.strftime('%z')

npath = Path(__file__).resolve()
BASEAPI.BASEPATH = npath.parent

LogRecord(f"setup_api - setting basepath to: {BASEAPI.BASEPATH}",
          level='info', sources=['mudproxy']).send()

BASEAPI.BASEDATAPATH = BASEAPI.BASEPATH / 'data'
BASEAPI.BASEDATAPLUGINPATH = BASEAPI.BASEDATAPATH / 'plugins'
BASEAPI.BASEDATALOGPATH = BASEAPI.BASEDATAPATH / 'logs'
BASEAPI.BASEPLUGINPATH = BASEAPI.BASEPATH / 'plugins'

os.makedirs(BASEAPI.BASEDATAPATH, exist_ok=True)
os.makedirs(BASEAPI.BASEDATALOGPATH, exist_ok=True)
os.makedirs(BASEAPI.BASEDATAPLUGINPATH, exist_ok=True)

def post_plugins_init():
  """
  do any actions that are post plugin init here
  """
  # add the IO manager
  from libs.io import IO
  API('plugins.core.managers:add')('libs.io', IO)

async def shutdown(signal_, loop_) -> None:
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.
    """
    LogRecord(f"shutdown - Received exit signal {signal_.name}", level='warning', sources=['mudproxy']).send()

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    LogRecord(f"shutdown - Cancelling {len(tasks)} outstanding tasks", level='warning', sources=['mudproxy']).send()

    for task in tasks:
        task.cancel()

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    LogRecord(f"shutdown - Exceptions: {exceptions}", level='warning', sources=['mudproxy']).send()
    loop_.stop()


def handle_exceptions(loop_, context) -> None:
    """
        We attach this as the exception handler to the event loop.  Currently we just
        log, as warnings, any exceptions caught.
    """
    msg = context.get('exception', context['message'])
    LogRecord(f"handle_exceptions - Caught exception: {msg} in loop: {loop_}", level='warning', sources=['mudproxy']).send()
    LogRecord(f"handle_exceptions - Caught in task: {asyncio.current_task()}", level='warning', sources=['mudproxy']).send()


if __name__ == "__main__":

    # create an ArgumentParser to parse the command line
    parser = libs.argp.ArgumentParser(description='A python mud proxy')

    # create a port option, this sets the variable automatically in the proxy plugin
    parser.add_argument(
        '-p',
        '--port',
        help='the port for the proxy to listen on',
        default=9000)

    args = vars(parser.parse_args())

    # setup file logging and network data logging
    libs.log.setup_loggers(logging.DEBUG)

    # initialize all plugins
    LogRecord('Plugin Manager - loading', level='info', sources=['mudproxy']).send()

    # instantiate the plugin manager
    from plugins import PluginMgr
    plugin_manager = PluginMgr()

    # initialize the plugin manager which will load plugins
    plugin_manager.initialize()
    LogRecord('Plugin Manager - loaded', level='info', sources=['mudproxy']).send()
    post_plugins_init()

    API.__class__.startup = False
    API('plugins.core.events:raise:event')('ev_bastproxy_proxy_ready', calledfrom='bastproxy')

    all_servers: list[asyncio.Task] = []

    telnet_port: int = args['port']
    LogRecord(f"__main__ - Creating proxy Telnet listener on port {telnet_port}", level='info', sources=['mudproxy']).send()

    all_servers.append(
        server.create_server(
            host='localhost',
            port=telnet_port,
            shell=libs.net.client.client_telnet_handler,
            connect_maxwait=0.5,
            timeout=3600,
            #log=log,
        ))

    LogRecord('__main__ - Launching proxy loop', level='info', sources=['mudproxy']).send()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    LogRecord('__main__ - setting up signal handlers', level='debug', sources=['mudproxy']).send()
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: create_task(shutdown(sig, loop), name='shutdown'))

    #loop.set_exception_handler(handle_exceptions)

    for server in all_servers:
        LogRecord(f"__main__ - running server: {server}", level='debug', sources=['mudproxy']).send()
        loop.run_until_complete(server)

    LogRecord('__main__ - run_forever', level='debug', sources=['mudproxy']).send()
    loop.run_forever()

    LogRecord('__main__ - exiting', level='info', sources=['mudproxy']).send()

