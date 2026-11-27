# Project: bastproxy
# Filename: plugins/core/web/libs/_call.py
#
# File Description: commands run over the client socket
#
# By: Bast
"""Command calls: a client runs a ``#bp`` command over the socket and gets a structured reply."""

# Standard Library
import asyncio
import inspect
import shlex
from collections.abc import Callable
from typing import Any

from ._ws import SocketConnection, SocketHub, envelope, error_message

# keep module identity across a reload of the plugin (other objects hold this class)
CANRELOAD = False

# below the hub's handler timeout, so a slow command is answered instead of cut off
CALL_TIMEOUT = 25.0
MAX_ID_LENGTH = 64
MAX_COMMAND_LENGTH = 256

# runs a command: (command, argument string) -> a `command.run.structured` reply or awaitable
Runner = Callable[[str, str], Any]
# colour coded text -> spans
SpansConverter = Callable[[str], list[dict[str, Any]]]


class Calls:
    """Handles the ``call`` message: runs the command and sends a ``result`` message."""

    def __init__(
        self,
        hub: SocketHub,
        runner: Runner,
        to_spans: SpansConverter,
        timeout: float = CALL_TIMEOUT,
    ) -> None:
        self._hub = hub
        self._runner = runner
        self._to_spans = to_spans
        self._timeout = timeout
        hub.register("call", self._call)

    def close(self) -> None:
        """Drop the handler."""
        self._hub.unregister("call")

    @staticmethod
    def _bad(connection: SocketConnection, text: str) -> None:
        connection.send(error_message("bad_message", text, "call"))

    @staticmethod
    def _arguments(value: Any) -> str | None:
        """The argument string of a call: a string as given, a list of strings joined."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return shlex.join(value)
        return None

    async def _call(self, connection: SocketConnection, message: dict[str, Any]) -> None:
        call_id = message.get("id")
        valid_id = (isinstance(call_id, str) and 0 < len(call_id) <= MAX_ID_LENGTH) or (
            isinstance(call_id, int) and not isinstance(call_id, bool)
        )
        if not valid_id:
            self._bad(connection, "call needs an id, a string of up to 64 characters or an integer")
            return
        command = message.get("command")
        if not isinstance(command, str) or not 0 < len(command) <= MAX_COMMAND_LENGTH:
            self._bad(connection, "call needs a command name")
            return
        arguments = self._arguments(message.get("args"))
        if arguments is None:
            self._bad(connection, "args must be a string or a list of strings")
            return
        if connection.view_only:
            connection.send(
                error_message("view_only", "this session cannot run commands", "call", id=call_id)
            )
            return
        try:
            async with asyncio.timeout(self._timeout):
                reply = self._runner(command, arguments)
                if inspect.isawaitable(reply):
                    reply = await reply
        except TimeoutError:
            connection.send(
                envelope(
                    "result",
                    id=call_id,
                    ok=False,
                    reason="timeout",
                    reply={"lines": [], "data": None},
                )
            )
            return
        fields: dict[str, Any] = {
            "id": call_id,
            "ok": bool(reply["ok"]),
            "reply": {
                "lines": [self._to_spans(line) for line in reply["lines"]],
                "data": reply["data"],
            },
        }
        if not fields["ok"]:
            fields["reason"] = reply["reason"]
        connection.send(envelope("result", **fields))
