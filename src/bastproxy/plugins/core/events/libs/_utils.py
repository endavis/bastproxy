# Project: bastproxy
# Filename: plugins/core/events/_utils.py
#
# File Description: Holds the decorator for registering to events
#
# By: Bast
"""Decorator for registering functions to events.

This module provides the `RegisterToEvent` decorator class that allows
functions to be automatically registered as event listeners.

"""

# Standard Library
from collections.abc import Callable
from typing import Any, Protocol, cast

# 3rd Party

# Project

CANRELOAD = False


class EventFunc(Protocol):
    """A callable that carries the ``event_registration`` attribute set by the decorator."""

    event_registration: list[dict[str, Any]]
    __self__: Any

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class RegisterToEvent:
    """a class to decorate a function to register it to an event."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the event registration decorator.

        Args:
            **kwargs: Keyword arguments including:
                event_name: the event to register to
                priority: the priority to register the function with (Default: 50).

        """
        self.registration_args = {"event_name": "", "priority": 50} | kwargs

    def __call__(self, func: Callable[..., Any]) -> Any:
        target = cast(EventFunc, func)
        if not hasattr(func, "event_registration"):
            target.event_registration = []
        target.event_registration.append(self.registration_args)

        return func
