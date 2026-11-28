# Project: bastproxy
# Filename: plugins/core/web/libs/_subscribe.py
#
# File Description: topic subscriptions on the client socket
#
# By: Bast
"""Topic subscriptions: a client follows a data provider over the client socket."""

# Standard Library
import asyncio
from collections.abc import Callable, Iterable
from typing import Any

from bastproxy.libs.logger import get_logger

from . import _http
from ._store import ProviderListeners, RouteTable, run_snapshot, socket_fields
from ._tls import LOGGER_NAME
from ._ws import SocketConnection, SocketHub, envelope, error_message

# keep module identity across a reload of the plugin (other objects hold this class)
CANRELOAD = False

DEBOUNCE = 0.1


class Subscriptions:
    """Sends a provider's snapshot to the sockets that follow its topic, debounced.

    Which topics a socket follows lives on the socket (``SocketConnection.subscriptions``);
    this keeps only the per-topic timers and flush tasks.
    """

    def __init__(
        self,
        hub: SocketHub,
        routes: Callable[[], RouteTable],
        listeners: ProviderListeners,
        debounce: float = DEBOUNCE,
    ) -> None:
        self._hub = hub
        self._routes = routes
        self._listeners = listeners
        self._debounce = debounce
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        hub.register("subscribe", self._subscribe)
        hub.register("unsubscribe", self._unsubscribe)
        listeners.add(self.changed)

    def close(self) -> None:
        """Stop listening, drop the handlers and cancel timers and flushes."""
        self._listeners.remove(self.changed)
        self._hub.unregister("subscribe")
        self._hub.unregister("unsubscribe")
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        for task in list(self._tasks):
            task.cancel()

    def _followers(self, topic: str) -> list[SocketConnection]:
        return [c for c in self._hub.connections() if topic in c.subscriptions]

    def changed(self, topic: str) -> None:
        """A provider's data changed: schedule one update for the topic."""
        if topic in self._timers or not self._followers(topic):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            get_logger(LOGGER_NAME).warning("no event loop to update subscribers of %s", topic)
            return
        self._timers[topic] = loop.call_later(self._debounce, self._fire, topic)

    def removed(self, topics: Iterable[str]) -> None:
        """Providers were removed: tell their subscribers and drop the subscriptions."""
        for topic in topics:
            timer = self._timers.pop(topic, None)
            if timer is not None:
                timer.cancel()
            self._drop(topic)

    def _drop(self, topic: str) -> None:
        for connection in self._followers(topic):
            connection.subscriptions.discard(topic)
            connection.send(
                error_message("topic_removed", f"the topic {topic} is gone", topic=topic)
            )

    def _fire(self, topic: str) -> None:
        self._timers.pop(topic, None)
        task = asyncio.get_running_loop().create_task(self._flush(topic), name="ws-flush")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _flush(self, topic: str) -> None:
        """Send the topic's snapshot to everyone who follows it."""
        if not self._followers(topic):
            return
        route = self._routes().provider_for_topic(topic)
        if route is None or route.provider is None or route.provider.snapshot is None:
            self._drop(topic)
            return
        try:
            async with asyncio.timeout(_http.HANDLER_TIMEOUT):
                data = await run_snapshot(route.provider.snapshot)
                fields = socket_fields(route.provider, data)
        except Exception:
            get_logger(LOGGER_NAME).error("snapshot of %s failed", topic, exc_info=True)
            message = error_message(
                "snapshot_failed", f"the snapshot of {topic} failed", topic=topic
            )
        else:
            message = envelope("update", topic=topic, **fields)
        for connection in self._followers(topic):
            connection.send(message)

    async def _subscribe(self, connection: SocketConnection, message: dict[str, Any]) -> None:
        topic = message.get("topic")
        if not isinstance(topic, str) or not topic:
            connection.send(
                error_message("bad_message", "subscribe needs a string topic", "subscribe")
            )
            return
        route = self._routes().provider_for_topic(topic)
        if route is None or route.provider is None or route.provider.snapshot is None:
            connection.send(
                error_message(
                    "unknown_topic", f"unknown topic {topic[:128]!r}", "subscribe", topic=topic
                )
            )
            return
        try:
            data = await run_snapshot(route.provider.snapshot)
            fields = socket_fields(route.provider, data)
        except TimeoutError:
            raise  # the generic handler timeout answers
        except Exception:
            get_logger(LOGGER_NAME).error("snapshot of %s failed", topic, exc_info=True)
            connection.send(
                error_message(
                    "snapshot_failed", f"the snapshot of {topic} failed", "subscribe", topic=topic
                )
            )
            return
        if connection.send(envelope("snapshot", topic=topic, **fields)):
            connection.subscriptions.add(topic)

    def _unsubscribe(self, connection: SocketConnection, message: dict[str, Any]) -> None:
        topic = message.get("topic")
        if isinstance(topic, str):
            connection.subscriptions.discard(topic)
