# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: networkmessage.py
#
# File Description: Message queues for passing input and output to clients.
#
# By: Bast/Jubelo
"""
    Housing the message queues and one Class to facilitate data between the proxy
    and the mud and clients.
"""

# Standard Library
import asyncio
from uuid import uuid4

# Third Party

# Project

# There is only one game connection, create a asyncio.Queue to hold messages to the game from
# clients.
messages_to_game = asyncio.Queue()

class NetworkData:
    """
    A Message is specifically a message meant for a connected client.

    message should be a byte string

    COMMAND-TELNET
        command should be a byte string of telnet options
    IO
        just a regular byte string to send
    """
    def __init__(self, msg_type, **kwargs):
        self.msg = kwargs.get('message', '')
        self.prompt = kwargs.get('is_prompt', 'false')
        self.client_uuid = kwargs.get('client_uuid', None)
        self.uuid = uuid4().hex
        self.msg_type = None
        if msg_type in ['IO', 'COMMAND-TELNET']:
            self.msg_type = msg_type

    @property
    def is_command_telnet(self):
        """
        A shortcut property to determine if this message is a Telnet Opcode.
        """
        return self.msg_type == 'COMMAND-TELNET'

    @property
    def is_io(self):
        """
        A shortcut property to determine if this message is normal I/O.
        """
        return self.msg_type == 'IO'

    @property
    def is_prompt(self):
        """
        A shortcut property to determine if this message is a prompt (versus normal I/O).
        """
        return self.prompt == 'true'
