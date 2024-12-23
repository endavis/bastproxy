# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/net/__init__.py
#
# File Description: update telnetlib3 with MUD protocols
#
# By: Bast/Jubelo
"""Module for updating telnetlib3 with MUD protocols.

This module updates the telnetlib3 library with various MUD protocols by adding
new attributes to the `telnetlib3.telopt` module. It ensures that the protocols
are available for use in telnet connections.

Key Components:
    - `mud_protocols`: A dictionary mapping protocol names to their byte values.
    - Code to add protocols to `telnetlib3.telopt` if they are not already present.

Features:
    - Automatic addition of MUD protocols to `telnetlib3.telopt`.
    - Debug logging for added protocols.

Usage:
    - This module is automatically executed when imported to update `telnetlib3`.

"""

# update telnetlib3 with mud protocols
import telnetlib3.telopt
from libs.records import LogRecord


mud_protocols = {
    "MSSP": bytes([70]),
    "MSDP": bytes([69]),
    "MCCP_COMPRESS": bytes([85]),
    "MCCP2_COMPRESS": bytes([86]),
    "MXP": bytes([91]),
    "MSP": bytes([90]),
    "A102": bytes([102]),  # Aardwolf 102
    "ATCP": bytes([200]),  # Achaea 200
    "GMCP": bytes([201]),
}

for item in mud_protocols:
    if not hasattr(telnetlib3.telopt, item):
        LogRecord(
            f"Adding {item} to telnetlib3.telopt", level="debug", sources=[__name__]
        )()
        setattr(telnetlib3.telopt, item, mud_protocols[item])
        telnetlib3.telopt._DEBUG_OPTS[mud_protocols[item]] = item  # type: ignore
