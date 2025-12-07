# Project: bastproxy
# Filename: libs/net/listeners.py
#
# File Description: create and manage listeners
#
# By: Bast/Jubelo
"""Module for creating and managing network listeners.

This module provides the `Listeners` class, which allows for the creation and
management of network listeners. It includes methods for checking the availability
of listeners, resetting listener settings to defaults, and creating listeners for
IPv4 and IPv6 addresses.

Key Components:
    - Listeners: A class that manages network listeners.
    - Methods for checking listener availability, resetting settings, and creating
        listeners.

Features:
    - Automatic resetting of listener settings to defaults if no listeners are
        available.
    - Support for both IPv4 and IPv6 listeners.
    - Logging of listener status and errors.

Usage:
    - Instantiate the `Listeners` class to create an object that manages network
        listeners.
    - Use `create_listeners` to start the listeners.
    - The module automatically checks listener availability and resets settings if
        necessary.

Classes:
    - `Listeners`: Manages the creation and monitoring of network listeners.

"""

import asyncio
import contextlib

# Standard Library
import sys

from bastproxy.libs.api import API as BASEAPI
from bastproxy.libs.asynch import TaskItem
from bastproxy.libs.net import client as net_client
from bastproxy.libs.net import server

# Third Party
# Project
from bastproxy.libs.records import LogRecord


class Listeners:
    """Manage the creation and monitoring of network listeners."""

    def __init__(self) -> None:
        """Initialize the Listeners class.

        This method initializes the Listeners class by setting up the necessary
        attributes for managing network listeners, including tasks for checking
        listener availability and creating listeners for both IPv4 and IPv6
        addresses.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self.listener_tries = 1
        self.api = BASEAPI(owner_id="mudproxy")
        self.check_listener_task: TaskItem | None = None
        self.check_listener_taskname = "Check Listeners Available"
        self.ipv4_task: TaskItem | None = None
        self.ipv4_taskname = "Proxy Telnet Listener IPv4"
        self.ipv4_start = False
        self.ipv6_task: TaskItem | None = None
        self.ipv6_taskname = "Proxy Telnet Listener IPv6"
        self.ipv6_start = False

    async def check_listeners_available(self) -> None:
        """Check the availability of network listeners.

        This method checks if the network listeners for both IPv4 and IPv6 addresses
        are available. If no listeners are available, it resets the listener settings
        to defaults and retries. If the listeners are still not available after
        multiple attempts, it logs an error and exits the program.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        await asyncio.sleep(2)

        if self.listener_tries > 2:
            LogRecord(
                "No listeners available, defaults did not work. Please check the "
                "settings in data/plugins/plugins.core.proxy",
                level="error",
                sources=["mudproxy"],
            )()
            sys.exit(1)

        ipv4 = self.api("plugins.core.settings:get")("plugins.core.proxy", "ipv4")
        ipv6 = self.api("plugins.core.settings:get")("plugins.core.proxy", "ipv6")
        self.ipv4_start = False
        self.ipv6_start = False

        if ipv4 and self.ipv4_task and self.ipv4_task.done:
            with contextlib.suppress(Exception):
                _ = self.ipv4_task.result
                self.ipv4_start = True
        if ipv6 and self.ipv6_task and self.ipv6_task.done:
            with contextlib.suppress(Exception):
                _ = self.ipv6_task.result
                self.ipv6_start = True

        listen_port = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "listenport"
        )
        if ipv4 and not self.ipv4_start:
            ipv4_address = self.api("plugins.core.settings:get")(
                "plugins.core.proxy", "ipv4address"
            )
            LogRecord(
                f"IPv4 Listener did not start on {ipv4_address}:{listen_port}, please "
                "check errors and update settings",
                level="error",
                sources=["mudproxy"],
            )()

        if ipv6 and not self.ipv6_start:
            ipv6_address = self.api("plugins.core.settings:get")(
                "plugins.core.proxy", "ipv6address"
            )
            LogRecord(
                f"IPv6 Listener did not start on {ipv6_address}:{listen_port}, please "
                "check errors and update settings",
                level="error",
                sources=["mudproxy"],
            )()

        if not (ipv4 and self.ipv4_start) and not (ipv6 and self.ipv6_start):
            LogRecord(
                "No listeners available, resetting to defaults",
                level="error",
                sources=["mudproxy"],
            )()
            self.reset_listener_settings()
            self.listener_tries = self.listener_tries + 1
            self.check_listener_taskname = (
                f"Check Listeners Available - Try {self.listener_tries!s}"
            )
            self.create_listeners()

        else:
            msg = "Listening on "
            tlist = []
            if self.ipv4_start:
                tlist.append("IPv4")
            if self.ipv6_start:
                tlist.append("IPv6")
            msg = (
                msg
                + " and ".join(tlist)
                + " port "
                + str(
                    self.api("plugins.core.settings:get")(
                        "plugins.core.proxy", "listenport"
                    )
                )
            )

            LogRecord(msg, level="info", sources=["mudproxy"])()

    def reset_listener_settings(self) -> None:
        """Reset listener settings to their default values.

        This method resets the listener settings for both IPv4 and IPv6 addresses
        to their default values. It updates the settings in the configuration to
        ensure that the listeners are set to their default states.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self.api("plugins.core.settings:change")(
            "plugins.core.proxy", "ipv4", "default"
        )
        self.api("plugins.core.settings:change")(
            "plugins.core.proxy", "ipv6", "default"
        )
        self.api("plugins.core.settings:change")(
            "plugins.core.proxy", "ipv4address", "default"
        )
        self.api("plugins.core.settings:change")(
            "plugins.core.proxy", "ipv6address", "default"
        )
        self.api("plugins.core.settings:change")(
            "plugins.core.proxy", "listenport", "default"
        )

    def _create_listeners(self) -> None:
        """Create listeners for both IPv4 and IPv6 addresses.

        This method creates network listeners for both IPv4 and IPv6 addresses based
        on the current settings. If no listeners are enabled, it enables the default
        IPv4 listener. It also imports the necessary client handler for the server
        creation.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        listen_port = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "listenport"
        )

        ipv4 = self.api("plugins.core.settings:get")("plugins.core.proxy", "ipv4")
        ipv4_address = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "ipv4address"
        )

        ipv6 = self.api("plugins.core.settings:get")("plugins.core.proxy", "ipv6")
        ipv6_address = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "ipv6address"
        )

        if not ipv4 and not ipv6:
            LogRecord(
                "No listeners enabled, adding default ipv4 listener",
                level="error",
                sources=["mudproxy"],
            )()
            self.api("plugins.core.settings:change")("plugins.core.proxy", "ipv4", True)
            ipv4 = True

        # add IPv4 listener
        if ipv4:
            self.ipv4_task = self.api("libs.asynch:task.add")(
                server.create_server(
                    host=ipv4_address,
                    port=listen_port,
                    shell=net_client.client_telnet_handler,
                    connect_maxwait=0.5,
                    timeout=3600,
                    encoding="utf8",
                ),
                self.ipv4_taskname,
                startstring=f"{ipv4_address}:{listen_port}",
            )

        # add IPv6 listener
        if ipv6:
            self.ipv6_task = self.api("libs.asynch:task.add")(
                server.create_server(
                    host=ipv6_address,
                    port=listen_port,
                    shell=net_client.client_telnet_handler,
                    connect_maxwait=0.5,
                    timeout=3600,
                    encoding="utf8",
                ),
                self.ipv6_taskname,
                startstring=f"{ipv6_address}:{listen_port}",
            )

    def create_listeners(self) -> None:
        """Create and start network listeners.

        This method initiates the creation of network listeners for both IPv4 and
        IPv6 addresses. It first resets the listener settings to their default values
        if no listeners are available. Then, it creates the listeners based on the
        current settings and starts the tasks for checking listener availability.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self._create_listeners()

        self.check_listener_task = self.api("libs.asynch:task.add")(
            self.check_listeners_available(),
            self.check_listener_taskname,
        )
