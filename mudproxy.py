#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Project: Bast's MUD Proxy
# Filename: mudproxy.py
#
# File Description: This is the main file for the MUD Proxy.
#
# By: Bast/Jubelo
"""Module for managing and running the MUD Proxy application.

This module provides the `MudProxy` class, which is responsible for initializing
and running the MUD Proxy application. It includes methods for loading plugins,
setting up events, and managing application settings. The module also configures
logging and sets up necessary paths for the application.

Key Components:
    - MudProxy: The main class for the MUD Proxy application.
    - Methods for loading plugins, setting up events, and managing settings.
    - Configuration of logging and application paths.

Features:
    - Automatic loading of plugins on startup.
    - Event management and notification system.
    - Configuration of application settings based on provided arguments.
    - Logging setup with support for UTC and local time zones.
    - Profiling support for performance analysis.

Usage:
    - Instantiate MudProxy to create an object that manages the MUD Proxy application.
    - Use the `run` method to start the application with the necessary arguments.
    - Configure logging and application paths as needed.

Classes:
    - `MudProxy`: Represents the main class for the MUD Proxy application.

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
from libs import timing  # noqa: F401
from libs.plugins import reloadutils  # noqa: F401

# set this to True to log in UTC timezone, False to log in local timezone
BASEAPI.LOG_IN_UTC_TZ = True

# set the start time
BASEAPI.proxy_start_time = datetime.datetime.now(datetime.timezone.utc)

# set the startup flag
BASEAPI.startup = True

# set the logging format (this is overwritten when libs.log.setup_loggers is called)
logging.basicConfig(
    stream=sys.stdout,
    level="INFO",
    format="%(asctime)s : %(levelname)-9s - %(name)-22s - %(message)s",
)

# change LOG_IN_UTC_TZ to False if you want to log in local time
# updates the formatter for the logging module
if BASEAPI.LOG_IN_UTC_TZ:
    logging.Formatter.formatTime = formatTime_RFC3339_UTC
else:
    logging.Formatter.formatTime = formatTime_RFC3339

# set the base path from the parent of the current file
BASEAPI.BASEPATH = Path(__file__).resolve().parent

# set the paths based on where the executable is
BASEAPI.BASEDATAPATH = BASEAPI.BASEPATH / "data"
BASEAPI.BASEDATAPLUGINPATH = BASEAPI.BASEDATAPATH / "plugins"
BASEAPI.BASEDATALOGPATH = BASEAPI.BASEDATAPATH / "logs"
BASEAPI.BASEPLUGINPATH = BASEAPI.BASEPATH / "plugins"

os.makedirs(BASEAPI.BASEDATAPATH, exist_ok=True)
os.makedirs(BASEAPI.BASEDATALOGPATH, exist_ok=True)
os.makedirs(BASEAPI.BASEDATAPLUGINPATH, exist_ok=True)


class MudProxy:
    """Main class for the MUD Proxy application.

    This class is responsible for initializing and running the MUD Proxy
    application. It includes methods for loading plugins, setting up events,
    and managing application settings.

    """

    def __init__(self) -> None:
        """Initialize the MudProxy instance.

        This constructor sets up the necessary attributes for the MudProxy
        application, including the API instance with the owner ID set to
        "mudproxy".

        """
        self.api = BASEAPI(owner_id="mudproxy")

    def run(self, args: dict) -> None:
        """Run the MUD Proxy application with the provided arguments.

        This method sets up the necessary configurations and starts the MUD Proxy
        application. It loads plugins, sets up events, and manages application
        settings based on the provided arguments.

        Args:
            args: A dictionary containing the arguments for the application, including
                the port and IPv4 address.

        Returns:
            None

        Raises:
            KeyError: If required keys are not found in the arguments dictionary.

        """
        LogRecord(
            f"setup_api - setting basepath to: {BASEAPI.BASEPATH}",
            level="info",
            sources=["mudproxy"],
        )()

        # Load plugins
        LogRecord("Loading Plugin Loader", level="info", sources=["mudproxy"])()

        # instantiate the plugin manager
        from libs.plugins.loader import PluginLoader

        plugin_loader = PluginLoader()

        LogRecord("Plugin Manager - loaded", level="info", sources=["mudproxy"])()

        # load plugins on startup
        plugin_loader.load_plugins_on_startup()

        LogRecord(
            "Plugin Manager - all plugins loaded", level="info", sources=["mudproxy"]
        )()

        # do any post plugin loaded actions
        self.post_plugins_loaded()

        # add events
        self.api.add_events()
        self.api("plugins.core.events:add.event")(
            "ev_bastproxy_proxy_ready",
            "mudproxy",
            description=[
                "An event raised when the proxy is ready to accept connections"
            ],
            arg_descriptions={"None": None},
        )

        args_listen_port: int = args["port"]
        plugin_listen_port = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "listenport"
        )

        args_ipv4_address = args["IPv4_address"]
        plugin_ipv4_address = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "ipv4address"
        )

        if args_listen_port != -1 and plugin_listen_port != args_listen_port:
            self.api("plugins.core.settings:change")(
                "plugins.core.proxy", "listenport", args_listen_port
            )

        if args_ipv4_address and plugin_ipv4_address != args_ipv4_address:
            self.api("plugins.core.settings:change")(
                "plugins.core.proxy", "ipv4address", args_ipv4_address
            )

        # done starting up, set the flag to False and raise the
        # ev_bastproxy_proxy_ready event
        BASEAPI.startup = False

        LogRecord("__main__ - BastProxy ready", level="info", sources=["mudproxy"])()

        self.api("plugins.core.events:raise.event")(
            "ev_bastproxy_proxy_ready", calledfrom="mudproxy"
        )

        from libs.net.listeners import Listeners

        Listeners().create_listeners()

        LogRecord(
            "__main__ - Launching async loop", level="info", sources=["mudproxy"]
        )()

        run_asynch()

        LogRecord("__main__ - exiting", level="info", sources=["mudproxy"])()

    def post_plugins_loaded(self) -> None:
        """Perform actions after all plugins have been loaded.

        This method is called after all plugins have been loaded during the startup
        process. It can be used to perform any necessary post-loading actions, such as
        additional configuration or initialization steps.

        Returns:
            None

        Raises:
            None

        """
        pass


def main() -> None:
    """Start the MUD Proxy.

    This function sets up the argument parser, parses the command line arguments,
    and initializes the MudProxy instance. It also handles profiling if the
    profile option is specified.

    Returns:
        None

    Raises:
        SystemExit: If the argument parsing fails or if the application exits.

    """
    import libs.argp

    # create an ArgumentParser to parse the command line
    parser = libs.argp.ArgumentParser(description="A python mud proxy")
    parser.formatter_class = libs.argp.CustomFormatter

    # create a port option, this sets the variable automatically in the proxy plugin
    parser.add_argument(
        "-p",
        "--port",
        help=(
            "the port for the proxy to listen on, \nwill override the "
            "plugins.core.proxy listenport setting (default: 9999)"
        ),
        default=-1,
    )

    parser.add_argument(
        "-pf", "--profile", help="profile code", action="store_true", default=False
    )

    parser.add_argument(
        "--IPv4-address",
        help="the ip4 address to bind to (default: localhost)",
        default="",
    )

    args = vars(parser.parse_args())

    MP = MudProxy()

    if args["profile"]:
        import cProfile
        import pstats
        import io

        with cProfile.Profile() as pr:
            MP.run(args)

            sortby = pstats.SortKey.CUMULATIVE
            stream = io.StringIO()
            ps = pstats.Stats(pr, stream=stream).sort_stats(sortby)
            ps.print_stats()

            result = stream.getvalue()
            # chop the string into a csv-like buffer
            result = "ncalls" + result.split("ncalls")[-1]
            result = "\n".join(
                [",".join(line.rstrip().split(None, 5)) for line in result.split("\n")]
            )
            # save it to disk
            with open("profile.csv", "w+") as f:
                f.write(result)
    else:
        MP.run(args)


if __name__ == "__main__":
    main()
