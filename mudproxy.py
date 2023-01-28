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

# Third Party

# Project
#from libs.net.mudserver import MudServer
#from libs.net.mudclient import MudClient
import libs.net.client
import libs.argp
from libs.net import telnetlib3


async def shutdown(signal_, loop_) -> None:
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.
    """
    log.warning("mudproxy.py:shutdown - Received exit signal %s", signal_.name)

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    log.info("mudproxy.py:shutdown - Cancelling %s outstanding tasks",
             len(tasks))

    for task in tasks:
        task.cancel()

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    log.warning("mudproxy.py:shutdown - Exceptions: %s", exceptions)
    loop_.stop()


def handle_exceptions(loop_, context) -> None:
    """
        We attach this as the exception handler to the event loop.  Currently we just
        log, as warnings, any exceptions caught.
    """
    msg = context.get("exception", context["message"])
    log.warning(
        "mudproxy.py:handle_exceptions - Caught exception: %s in loop: %s",
        msg, loop_)
    log.warning("mudproxy.py:handle_exceptions - Caught in task: %s",
                asyncio.current_task())


if __name__ == "__main__":
    # create an ArgumentParser to parse the command line
    parser = libs.argp.ArgumentParser(description='A python mud proxy')
    
    # create a port option, this sets the variable automatically in the proxy plugin
    parser.add_argument(
        '-p', 
        "--port",
        help="the port for the proxy to listen on",
        default=9000)
    
    parser.add_argument(
        '-d',
        '--debug',
        action="store_true",
        default=False,
        help='Set log level to debug',
    )

    args = vars(parser.parse_args())

    log_level = logging.DEBUG if args['debug'] else logging.INFO

    # setup the various paths for use

    libs.log.setup_loggers(log_level)

    log: logging.Logger = logging.getLogger(__name__)
    log.debug("Args: %s", args)

    all_servers: list[asyncio.tasks] = []

    telnet_port: int = args['port']
    log.info(
        "mudproxy.py:__main__ - Creating client Telnet listener on port %s",
        telnet_port)

    all_servers.append(
        telnetlib3.create_server(
            host="localhost",
            port=telnet_port,
            shell=libs.net.client.client_telnet_handler,
            connect_maxwait=0.5,
            timeout=3600,
            #log=log,
        ))

    log.info("mudproxy.py:__main__ - Launching proxy loop")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    log.debug('mudproxy.py:__main__ - setting up signal handlers')
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(shutdown(sig, loop)))

    loop.set_exception_handler(handle_exceptions)

    for server in all_servers:
        log.debug('running server: %s', server)
        loop.run_until_complete(server)

    log.debug('run_forever')
    loop.run_forever()

    log.info("mudproxy.py:__main__ - shut down.")
