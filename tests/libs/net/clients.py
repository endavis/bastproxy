"""Scripted telnet peers for the link tests (#58); not a test file.

``ScriptedClient`` is a raw TCP client that answers ``DO``/``WILL`` per option,
inflates the stream after ``SB MCCP2`` and collects what it saw, so a test can run
"client A accepts, client B refuses" against one proxy server. ``proxy_server``
runs the proxy's own ``create_server`` with ``compression=True``. ``scripted_mud``
is a raw TCP server standing in for a MUD that records the bytes it receives.
"""

import asyncio
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any

from telnetlib3.mud import gmcp_encode, msdp_encode
from telnetlib3.telopt import (
    DO,
    DONT,
    GMCP,
    IAC,
    MCCP2_COMPRESS,
    MSDP,
    SB,
    SE,
    TTYPE,
    WILL,
    WONT,
)

from bastproxy.libs.net.server import create_server

TIMEOUT = 5
_VERBS = (DO, DONT, WILL, WONT)


async def wait_until(predicate: Callable[[], bool]) -> None:
    """Poll until ``predicate()`` is true; raise ``TimeoutError`` after ``TIMEOUT`` seconds."""
    async with asyncio.timeout(TIMEOUT):
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(0.02)


def sb_frame(option: bytes, payload: bytes) -> bytes:
    """Frame ``payload`` as ``IAC SB option ... IAC SE``, escaping IAC bytes."""
    return IAC + SB + option + payload.replace(IAC, IAC + IAC) + IAC + SE


class ScriptedClient:
    """A raw telnet client that answers per option and inflates MCCP2 streams.

    Attributes:
        agree: Options the client accepts (always including TTYPE), both ``WILL x`` (answered ``DO``) and
            ``DO x`` (answered ``WILL``). Anything else is refused. A
            ``DONT``/``WONT`` is never answered.
        raw: Every byte received, compressed bytes included.
        text: Received data with telnet commands removed and MCCP2 inflated.
        commands: Every ``(verb, option)`` received.
        subnegotiations: Every ``(option, payload)`` SB received other than MCCP2, IAC IAC unescaped.
        mccp2_starts: Count of ``SB MCCP2`` received.
        stream_ends: Count of compressed streams that ended with ``Z_STREAM_END``.

    """

    def __init__(self, agree: set[bytes] | None = None) -> None:
        """Create the client; call ``connect`` to open it."""
        # telnetlib3 starts advanced negotiation (where the proxy offers MCCP2)
        # only after the client affirms some option, so TTYPE is always accepted
        self.agree: set[bytes] = {TTYPE, *(agree or set())}
        self.raw = bytearray()
        self.text = bytearray()
        self.commands: list[tuple[bytes, bytes]] = []
        self.subnegotiations: list[tuple[bytes, bytes]] = []
        self.mccp2_starts = 0
        self.stream_ends = 0
        self._pending = bytearray()
        self._inflater: Any = None
        self._answered: set[tuple[bytes, bytes]] = set()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None

    async def connect(self, port: int) -> None:
        """Open the connection and start collecting."""
        self._reader, self._writer = await asyncio.open_connection("127.0.0.1", port)
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        assert self._reader is not None
        while data := await self._reader.read(4096):
            self.raw.extend(data)
            self._feed(data)

    def _feed(self, data: bytes) -> None:
        if self._inflater is not None:
            try:
                data = self._inflater.decompress(data)
            except zlib.error:
                self._inflater = None
                return
            if self._inflater.eof:
                unused = self._inflater.unused_data
                self._inflater = None
                self.stream_ends += 1
                self._parse(data)
                if unused:
                    self._feed(unused)
                return
        self._parse(data)

    def _parse(self, data: bytes) -> None:
        self._pending.extend(data)
        buf = self._pending
        i = 0
        while i < len(buf):
            if buf[i : i + 1] != IAC:
                self.text.append(buf[i])
                i += 1
                continue
            if i + 1 >= len(buf):
                break
            verb = bytes(buf[i + 1 : i + 2])
            if verb in _VERBS:
                if i + 2 >= len(buf):
                    break
                self._command(verb, bytes(buf[i + 2 : i + 3]))
                i += 3
            elif verb == SB:
                end = bytes(buf).find(IAC + SE, i)
                if end == -1:
                    break
                opt = bytes(buf[i + 2 : i + 3])
                if opt != MCCP2_COMPRESS:
                    payload = bytes(buf[i + 3 : end]).replace(IAC + IAC, IAC)
                    self.subnegotiations.append((opt, payload))
                i = end + 2
                if opt == MCCP2_COMPRESS:
                    self.mccp2_starts += 1
                    self._inflater = zlib.decompressobj()
                    rest = bytes(buf[i:])
                    del buf[:]
                    if rest:
                        self._feed(rest)
                    return
            else:
                i += 2
        del buf[:i]

    def _command(self, verb: bytes, opt: bytes) -> None:
        self.commands.append((verb, opt))
        if verb not in (DO, WILL) or (verb, opt) in self._answered:
            return
        self._answered.add((verb, opt))
        yes, no = (DO, DONT) if verb == WILL else (WILL, WONT)
        self.send(IAC + (yes if opt in self.agree else no) + opt)

    def send(self, data: bytes) -> None:
        """Write raw bytes to the server."""
        assert self._writer is not None
        self._writer.write(data)

    def gmcp(self, package: str, data: Any = None) -> None:
        """Send a GMCP message."""
        self.send(sb_frame(GMCP, gmcp_encode(package, data)))

    def msdp(self, variables: dict[str, Any]) -> None:
        """Send an MSDP message."""
        self.send(sb_frame(MSDP, msdp_encode(variables)))

    async def wait_for(self, predicate: Callable[[], bool]) -> None:
        """Wait until ``predicate()`` is true, or fail the test on timeout."""
        await wait_until(predicate)

    async def close(self) -> None:
        """Close the connection and stop collecting."""
        if self._writer is not None:
            self._writer.close()
            with suppress(OSError):
                await self._writer.wait_closed()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task


class ProxyServer:
    """The proxy's client-link server; each connection's shell writes what a test queues.

    ``writers[i]`` and ``queues[i]`` belong to the i-th connection. Put text on a
    queue to have that client's shell write it; put ``None`` to end the shell.
    """

    def __init__(self) -> None:
        """Create an empty server state."""
        self.writers: list[Any] = []
        self.queues: list[asyncio.Queue[str | None]] = []
        self.port = 0

    async def shell(self, _reader: Any, writer: Any) -> None:
        """Write queued text to the client until told to stop."""
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.queues.append(queue)
        self.writers.append(writer)
        while (msg := await queue.get()) is not None:
            writer.write(msg)
            await writer.drain()
        writer.close()

    async def connect(self, agree: set[bytes] | None = None) -> ScriptedClient:
        """Connect a new scripted client and wait for its shell to start."""
        before = len(self.writers)
        client = ScriptedClient(agree)
        await client.connect(self.port)
        await client.wait_for(lambda: len(self.writers) > before)
        # let the server's initial negotiation finish
        await asyncio.sleep(0.5)
        return client


@asynccontextmanager
async def proxy_server() -> AsyncIterator[ProxyServer]:
    """Run ``create_server`` as the listeners do, with ``compression=True``."""
    proxy = ProxyServer()
    srv = await create_server(
        host="127.0.0.1",
        port=0,
        shell=proxy.shell,
        encoding="utf8",
        compression=True,
        force_binary=True,
        encoding_errors="replace",
        connect_maxwait=0.3,
    )
    proxy.port = srv.sockets[0].getsockname()[1]
    try:
        yield proxy
    finally:
        for queue in proxy.queues:
            queue.put_nowait(None)
        srv.close()
        await asyncio.wait_for(srv.wait_closed(), TIMEOUT)


class ScriptedMud:
    """A raw TCP server standing in for a MUD; ``received`` holds what clients sent."""

    def __init__(self, script: Callable[["ScriptedMud", asyncio.StreamWriter], Awaitable[None]]):
        """Create the MUD; ``script`` runs for each connection."""
        self.script = script
        self.received = bytearray()
        self.port = 0
        self._tasks: list[asyncio.Task[None]] = []

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async def collect() -> None:
            while data := await reader.read(4096):
                self.received.extend(data)

        task = asyncio.create_task(collect())
        self._tasks.append(task)
        try:
            await self.script(self, writer)
        finally:
            writer.close()

    async def wait_for(self, predicate: Callable[[], bool]) -> None:
        """Wait until ``predicate()`` is true, or fail the test on timeout."""
        await wait_until(predicate)

    @staticmethod
    def gmcp_frame(package: str, data: Any = None) -> bytes:
        """The bytes of a GMCP message, to write from a script."""
        return sb_frame(GMCP, gmcp_encode(package, data))

    @staticmethod
    def msdp_frame(variables: dict[str, Any]) -> bytes:
        """The bytes of an MSDP message, to write from a script."""
        return sb_frame(MSDP, msdp_encode(variables))


@asynccontextmanager
async def scripted_mud(
    script: Callable[[ScriptedMud, asyncio.StreamWriter], Awaitable[None]],
) -> AsyncIterator[ScriptedMud]:
    """Run a raw TCP server whose per-connection behaviour is ``script``."""
    mud = ScriptedMud(script)
    server = await asyncio.start_server(mud._handle, "127.0.0.1", 0)
    mud.port = server.sockets[0].getsockname()[1]
    try:
        yield mud
    finally:
        server.close()
        for task in mud._tasks:
            task.cancel()
        await asyncio.gather(*mud._tasks, return_exceptions=True)
        await server.wait_closed()
