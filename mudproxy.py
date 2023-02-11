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
from libs.net import telnetlib3
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

def setup_api():
    """
    find the base path of the bastproxy.py file for later use
    in importing plugins and create data directories
    """
    npath = Path(__file__).resolve()
    BASEAPI.BASEPATH = npath.parent

    msg = f"setup_api - setting basepath to: {BASEAPI.BASEPATH}"
    if API('libs.api:has')('libs.io:send:msg'):
        API('libs.io:send:msg')(msg, level='info', primary='mudproxy')
    else:
        print(msg)

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
  API('core.managers:add')('libs.io', IO)

  # add some logging of various plugins and functionality
  API('core.msg:add:datatype')('net')
  API('core.msg:toggle:to:console')('net')
  API('core.msg:add:datatype')('inputparse')
  API('core.msg:add:datatype')('ansi')
  API('core.msg:add:datatype')('libs.io')

async def shutdown(signal_, loop_) -> None:
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.
    """
    log.warning(f"shutdown - Received exit signal {signal_.name}")

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    log.info(f"shutdown - Cancelling {len(tasks)} outstanding tasks")

    for task in tasks:
        task.cancel()

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    log.warning(f"shutdown - Exceptions: {exceptions}")
    loop_.stop()


def handle_exceptions(loop_, context) -> None:
    """
        We attach this as the exception handler to the event loop.  Currently we just
        log, as warnings, any exceptions caught.
    """
    msg = context.get('exception', context['message'])
    log.warning(f"handle_exceptions - Caught exception: {msg} in loop: {loop_}")
    log.warning(f"handle_exceptions - Caught in task: {asyncio.current_task()}")


if __name__ == "__main__":

    # create an ArgumentParser to parse the command line
    parser = libs.argp.ArgumentParser(description='A python mud proxy')

    # create a port option, this sets the variable automatically in the proxy plugin
    parser.add_argument(
        '-p',
        '--port',
        help='the port for the proxy to listen on',
        default=9000)

    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        default=False,
        help='Set log level to debug',
    )

    args = vars(parser.parse_args())

    log_level = logging.DEBUG if args['debug'] else logging.INFO

    # setup the various paths for use
    setup_api()

    # setup file logging and network data logging
    libs.log.setup_loggers(log_level)

    log: logging.Logger = logging.getLogger('mudproxy')
    log.debug(f"Args: {args}")

    # initialize all plugins
    log.info('Plugin Manager - loading')
    # instantiate the plugin manager
    from plugins import PluginMgr
    plugin_manager = PluginMgr()

    # initialize the plugin manager which will load plugins
    plugin_manager.initialize()
    log.info('Plugin Manager - loaded')
    post_plugins_init()

    API.__class__.startup = False
    API('core.events:raise:event')('ev_bastproxy_proxy_ready', calledfrom='bastproxy')

    all_servers: list[asyncio.Task] = []

    telnet_port: int = args['port']
    log.info(f"__main__ - Creating client Telnet listener on port {telnet_port}")

    all_servers.append(
        telnetlib3.create_server(
            host='localhost',
            port=telnet_port,
            shell=libs.net.client.client_telnet_handler,
            connect_maxwait=0.5,
            timeout=3600,
            #log=log,
        ))

    log.info('__main__ - Launching proxy loop')

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    log.debug('__main__ - setting up signal handlers')
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: create_task(shutdown(sig, loop), name='shutdown'))

    #loop.set_exception_handler(handle_exceptions)

    for server in all_servers:
        log.debug(f"running server: {server}")
        loop.run_until_complete(server)

    log.debug('run_forever')
    loop.run_forever()

    log.info('__main__ - shut down.')
