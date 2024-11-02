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
from libs.records import ToClientData, LogRecord, ToMudData, NetworkDataLine
from libs.records import NetworkData as NetworkData
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
        self.send_queue: asyncio.Queue[NetworkDataLine] = asyncio.Queue()
        self.connected_time =  datetime.datetime.now(datetime.timezone.utc)
        self.reader = None
        self.writer = None
        self.lines_to_read = 15
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
                             term=self.term_type, shell=self.mud_telnet_handler,
                             encoding='utf8')
        # print(f'{type(self.reader) = }')
        # print(f'{type(self.writer) = }')
        #await self.mud_telnet_handler(self.reader, self.writer)

    def disconnect_from_mud(self):
        """
        disconnect from a mud
        """
        self.connected = False

    def send_to(self, data: NetworkDataLine) -> None:
        """
        add data to the queue
        """
        if not self.connected:
            LogRecord("send_to - Not connected to the mud, cannot send data",
                      level='debug',
                      sources=[__name__])()
            return
        loop = asyncio.get_event_loop()
        if not isinstance(data, NetworkDataLine):
            LogRecord(f"client: send_to - {self.uuid} got a type that is not NetworkDataLine : {type(data)}",
                      level='error', stack_info=True,
                      sources=[__name__])()
        else:
            loop.call_soon_threadsafe(self.send_queue.put_nowait, data)

    async def setup_mud(self) -> None:
        """
        send telnet options
        send welcome message to client
        ask for password
        """

        if features := telnet.advertise_features():
            LogRecord(
                "setup_mud - Sending telnet features",
                level='info',
                sources=[__name__],
            )()
            networkdata = NetworkData([], owner_id="mud:setup_mud")
            networkdata.append(NetworkDataLine(features, originated='internal', line_type="COMMAND-TELNET"))
            ToMudData(networkdata)()
            LogRecord(
                "setup_mud - telnet features sent",
                level='info',
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
            level='info',
            sources=[__name__],
        )()

        while self.connected and self.reader:
            # print('mud_read - waiting for data')
            inp: str = ''

            data = NetworkData([], owner_id="mud_read")
            while True:
                inp = await self.reader.readline()
                if not inp:
                    print('no data from readline')
                    break
                LogRecord(f"client_read - readline - Raw received data in mud_read : {inp}", level='debug', sources=[__name__])()
                LogRecord(f"client_read - readline - inp type = {type(inp)}", level='debug', sources=[__name__])()
                data.append(NetworkDataLine(inp.rstrip(), originated='mud'))
                logging.getLogger("data.mud").info(f"{'from_mud':<12} : {inp}")
                if len(self.reader._buffer) <= 0 or b'\n' not in self.reader._buffer or len(data) == self.lines_to_read:
                    break

            if len(self.reader._buffer) > 0 and b'\n' not in self.reader._buffer:
                inp: str = await self.reader.read(len(self.reader._buffer))
                LogRecord(f"client_read - read - Raw received data in mud_read : {inp}", level='debug', sources=[__name__])()
                LogRecord(f"client_read - read - inp type = {type(inp)}", level='debug', sources=[__name__])()
                data.append(NetworkDataLine(inp, originated='mud', had_line_endings=False))
                logging.getLogger("data.mud").info(f"{'from_mud':<12} : {inp}")

            if self.reader.at_eof():  # This is an EOF.  Hard disconnect.
                self.connected = False
                return

            # this is where we start with ToClientData
            ToClientData(data)()

            # this is so we don't hog the asyncio loop
            await asyncio.sleep(0)

        LogRecord(
            "mud_read - Ending coroutine",
            level='info',
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
        while self.connected and self.writer and not self.writer.connection_closed:
            msg_obj: NetworkDataLine = await self.send_queue.get()
            if msg_obj.is_io:
                if msg_obj.line:
                    LogRecord(f"mud_write - Writing message to mud: {msg_obj.line}",
                            level='debug',
                            sources=[__name__])()
                    LogRecord(f"mud_write - type of msg_obj.msg = {type(msg_obj.line)}",
                            level='debug',
                            sources=[__name__])()
                    self.writer.write(msg_obj.line)
                    logging.getLogger("data.mud").info(f"{'to_mud':<12} : {msg_obj.line}")
                else:
                    LogRecord(
                        "client_write - No message to write to client.",
                        level='debug',
                        sources=[__name__],
                    )()
            elif msg_obj.is_command_telnet:
                LogRecord(f"mud_write - type of msg_obj.msg = {type(msg_obj.line)}",
                        level='debug',
                        sources=[__name__])()
                LogRecord(f"mud_write - Writing telnet option mud: {repr(msg_obj.line)}",
                            level='debug',
                            sources=[__name__])()
                self.writer.send_iac(msg_obj.line)
                logging.getLogger("data.mud").info(f"{'to_client':<12} : {msg_obj.line}")

        LogRecord("mud_write - Ending coroutine",
                  level='debug',
                  sources=[__name__])()

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
        self.reader.readline = unicode_readline_monkeypatch.__get__(reader)

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

async def unicode_readline_monkeypatch(self):
    r"""
    Read one line.

    Where "line" is a sequence of characters ending with CR LF, LF,
    or CR NUL. This readline function is a strict interpretation of
    Telnet Protocol :rfc:`854`.

    The sequence "CR LF" must be treated as a single "new line" character
    and used whenever their combined action is intended; The sequence "CR
    NUL" must be used where a carriage return alone is actually desired;
    and the CR character must be avoided in other contexts.

    And therefor, a line does not yield for a stream containing a
    CR if it is not succeeded by NUL or LF.

    ================= =====================
    Given stream      readline() yields
    ================= =====================
    ``--\r\x00---``   ``--\r``, ``---`` *...*
    ``--\r\n---``     ``--\r\n``, ``---`` *...*
    ``--\n---``       ``--\n``, ``---`` *...*
    ``--\r---``       ``--\r``, ``---`` *...*
    ================= =====================

    If EOF is received before the termination of a line, the method will
    yield the partially read string.

    Note: this is a monkey-patch of the TelnetReaderUnicode.readline method
    to support \n\r line endings.
    """
    if self._exception is not None:
        raise self._exception

    line = bytearray()
    not_enough = True

    while not_enough:
        while self._buffer and not_enough:
            search_results_pos_kind = (
                (self._buffer.find(b"\r\n"), b"\r\n"),
                (self._buffer.find(b"\n\r"), b"\n\r"),
                (self._buffer.find(b"\r\x00"), b"\r\x00"),
                (self._buffer.find(b"\r"), b"\r"),
                (self._buffer.find(b"\n"), b"\n"),
            )

            # sort by (position, length * -1), so that the
            # smallest sorted value is the longest-match,
            # preferring '\r\n' over '\r', for example.
            matches = [
                (_pos, len(_kind) * -1, _kind)
                for _pos, _kind in search_results_pos_kind
                if _pos != -1
            ]

            if not matches:
                line.extend(self._buffer)
                self._buffer.clear()
                continue

            # position is nearest match,
            pos, _, kind = min(matches)
            if kind == b"\r\x00":
                # trim out '\x00'
                begin, end = pos + 1, pos + 2
            elif kind in [b"\r\n", b"\n\r"]:
                begin = end = pos + 2
            else:
                # '\r' or '\n'
                begin = end = pos + 1
            line.extend(self._buffer[:begin])
            del self._buffer[:end]
            not_enough = False

        if self._eof:
            break

        if not_enough:
            await self._wait_for_data("readline")

    self._maybe_resume_transport()
    buf = bytes(line)
    return self.decode(buf)
