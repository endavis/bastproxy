# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/net/client.py
#
# File Description: Client connection handling.
#
# By: Bast/Jubelo
"""
    Housing the Class(es) and coroutines for accepting and maintaining connections from clients
    via Telnet, Secure Telnet and SSH.

    We do not register to events here, but we do fire events.
"""

# Standard Library
import asyncio
import logging
import datetime

# Third Party
from telnetlib3 import TelnetReaderUnicode, TelnetWriterUnicode, open_connection

# Project
from libs.net import telnet
from libs.api import API
from libs.records import ToClientData, LogRecord, ToMudRecord, NetworkDataLine
from libs.records import NetworkData as BaseNetworkDataRecord
from libs.net.networkdata import NetworkData
from libs.asynch import TaskItem


class MudConnection:
    """
        Each connection when created in async handle_client will instantiate this class.

        Instance variables:
            self.addr is the IP address portion of the client
            self.port is the port portion of the client
            self.conn_type is the type of client connection
                close connection on 3 failed attempts
            self.state is the current state of the client connection
            self.reader is the asyncio.StreamReader for the connection
            self.writer is the asyncio.StreamWriter for the connection

    """
    def __init__(self, addr, port):
        self.addr: str = addr
        self.port: str = port
        self.api = API(owner_id=f"{__name__}")
        #self.conn_type: str = conn_type
        # self.state: dict[str, bool] = {'connected': True}
        self.connected = True
        self.send_queue: asyncio.Queue[NetworkData] = asyncio.Queue()
        self.connected_time =  datetime.datetime.now(datetime.timezone.utc)
        self.reader = None
        self.writer = None
        self.term_type = 'bastproxy'
        #print(self.writer.protocol._extra)  # type: ignore
        # rows = self.writer.protocol._extra['rows']
        # term = self.writer.protocol._extra['TERM']

    async def connect_to_mud(self):
        """
        connect to a mud
        """
        # create a mud connection through telnetlib3
        await open_connection(self.addr, int(self.port),
                             term=self.term_type, shell=self.mud_telnet_handler)
        # print(f'{type(self.reader) = }')
        # print(f'{type(self.writer) = }')
        #await self.mud_telnet_handler(self.reader, self.writer)

    def disconnect_from_mud(self):
        """
        disconnect from a mud
        """
        self.connected = False

    def send_to(self, data: ToMudRecord) -> None:
        """
        add data to the queue
        """
        if not self.connected:
            LogRecord('send_to - Mud is not connected', level='debug', sources=[__name__])()
            return
        loop = asyncio.get_event_loop()
        if data.is_io:
            message = NetworkData(data.message_type, message=''.join(data))
            loop.call_soon_threadsafe(self.send_queue.put_nowait, message)
        else:
            for i in data:
                message = NetworkData(data.message_type, message=i)
                loop.call_soon_threadsafe(self.send_queue.put_nowait, message)

    async def setup_mud(self) -> None:
        """
        send telnet options
        send welcome message to client
        ask for password
        """

        if features := telnet.advertise_features():
            LogRecord(
                "setup_mud - Sending telnet features",
                level='debug',
                sources=[__name__],
            )()
            ToMudRecord([features], message_type='COMMAND-TELNET')('libs.net.client:setup_client')
            LogRecord(
                "setup_mud - telnet features sent",
                level='debug',
                sources=[__name__],
            )()

        if self.writer:
            await self.writer.drain()

    async def mud_read(self) -> None:
        """
            Utilized by the Telnet mud_handler.

            We want this coroutine to run while the mud is connected, so we begin with a while loop
        """
        LogRecord(
            "mud_read - Starting coroutine for mud",
            level='debug',
            sources=[__name__],
        )()

        while self.connected and self.reader:
            inp: str = await self.reader.readline()
            LogRecord(f"client_read - Raw received data in mud_read : {inp}", level='debug', sources=[__name__])()
            LogRecord(f"client_read - inp type = {type(inp)}", level='debug', sources=[__name__])()
            logging.getLogger("data.mud").info(f"{'from_mud':<12} : {inp}")

            if not inp:  # This is an EOF.  Hard disconnect.
                self.connected = False
                return

            # this is where we start with ToClientRecord
            ToClientData(BaseNetworkDataRecord(NetworkDataLine(inp.strip(), originated='mud')))('libs.net.mud:mud_read')

        LogRecord(
            "mud_read - Ending coroutine",
            level='debug',
            sources=[__name__]
        )()

    async def mud_write(self) -> None:
        """
            Utilized by the Telnet and SSH client_handlers.

            We want this coroutine to run while the client is connected, so we begin with a while loop
            We await for any messages from the game to this client, then write and drain it.
        """
        LogRecord(
            "client_write - Starting coroutine for mud_write",
            level='debug',
            sources=[__name__],
        )()
        while self.connected and self.writer:
            msg_obj: NetworkData = await self.send_queue.get()
            if msg_obj.is_io:
                if msg_obj.msg:
                    LogRecord(f"client_write - Writing message to mud: {msg_obj.msg}", level='debug', sources=[__name__])()
                    LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug', sources=[__name__])()
                    self.writer.write(msg_obj.msg)  # type: ignore
                    logging.getLogger("data.mud").info(f"{'to_mud':<12} : {msg_obj.msg}")
                    if msg_obj.is_prompt:
                        self.writer.write(telnet.go_ahead())
                        logging.getLogger(f"data.{self.uuid}").info(f"{'to_client':<12} : {telnet.goahead()}")  # type: ignore
                else:
                    LogRecord(
                        "client_write - No message to write to client.",
                        level='debug',
                        sources=[__name__],
                    )()

            elif msg_obj.is_command_telnet:
                LogRecord(f"client_write - Writing telnet option to mud: {msg_obj.msg}", level='debug', sources=[__name__])()
                LogRecord(f"client_write - type of msg_obj.msg = {type(msg_obj.msg)}", level='debug', sources=[__name__])()
                self.writer.send_iac(msg_obj.msg)  # type: ignore
                logging.getLogger("data.mud").info(f"{'to_client':<12} : {msg_obj.msg}")

            self.api('libs.asynch:task.add')(self.writer.drain, name="mud.write.drain")

        LogRecord(
            "client_write - Ending coroutine",
            level='debug',
            sources=[__name__]
        )()

    async def mud_telnet_handler(self, reader, writer) -> None:
        """
        This handler is for the mud connection and is the starting point for
        creating the tasks necessary to handle the mud connection.
        """
        client_details: str = writer.get_extra_info('peername')

        _, _, *rest = client_details
        LogRecord(f"Mud Connection opened - {self.addr} : {self.port} : {rest}", level='warning', sources=[__name__])()
        self.reader = reader
        self.writer = writer

        tasks: list[asyncio.Task] = [
            TaskItem(self.mud_read(),
                                name="mud telnet read").create(),
            TaskItem(self.mud_write(),
                                name="mud telnet write").create(),
        ]

        if current_task := asyncio.current_task():
            current_task.set_name("mud telnet client handler")

        await self.setup_mud()

        _, rest = await asyncio.wait(tasks, return_when='FIRST_COMPLETED')

        for task in rest:
            task.cancel()

        self.connected = False

        LogRecord(f"Mud Connection closed - {self.addr} : {self.port} : {rest}", level='warning', sources=[__name__])()

        await asyncio.sleep(1)

