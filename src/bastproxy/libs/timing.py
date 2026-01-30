# Project: bastproxy
# Filename: libs/timing.py
#
# File Description: a module to time functions
#
# By: Bast
"""Module for timing functions and managing timing operations.

This module provides the `Timing` class and `duration` decorator to measure and
manage the execution time of functions. It includes methods for starting and
finishing timers, toggling the timing functionality, and logging the timing
information using the provided API.

Key Components:
    - Timing: A class that manages timing operations.
    - duration: A decorator to measure the duration of function calls.

Features:
    - Start and finish timers with unique identifiers.
    - Toggle the timing functionality on and off.
    - Log timing information with detailed context.
    - Measure the duration of function calls using the `duration` decorator.

Usage:
    - Instantiate the `Timing` class to create a timing manager.
    - Use the `duration` decorator to measure the execution time of functions.
    - Start and finish timers using the `start` and `finish` methods.
    - Toggle the timing functionality using the `toggle` method.

Classes:
    - `Timing`: Manages timing operations and logs timing information.

"""

# Standard Library
from collections.abc import Callable
from functools import wraps
from timeit import default_timer
from typing import Any
from uuid import uuid4

# 3rd Party
# Project
from bastproxy.libs.api import API as BASEAPI
from bastproxy.libs.api import AddAPI
from bastproxy.libs.records import LogRecord

API = BASEAPI(owner_id=__name__)


def duration(func: Callable[..., Any]) -> Callable[..., Any]:
    """Measure the duration of a function call.

    This decorator wraps a function to measure the time it takes to execute. It
    logs the start and finish times using the API.

    Args:
        func: The function to be wrapped and timed.

    Returns:
        The wrapped function.

    Raises:
        None

    """

    @wraps(func)
    def wrapper(*arg) -> Any:
        """Measure execution time.

        This function wraps the original function to measure its execution time.
        It logs the start and finish times using the API.

        Args:
            *arg: Positional arguments passed to the wrapped function.

        Returns:
            The result of the wrapped function.

        Raises:
            None

        """
        tname = f"{func.__name__}"
        uid = API("libs.timing:start")(tname, arg)
        res = func(*arg)
        API("libs.timing:finish")(uid)
        return res

    return wrapper


class Timing:
    """Manages timing operations and logs timing information.

    This class provides methods to start and finish timers, toggle the timing
    functionality, and log timing information using the provided API. It is
    designed to help measure and manage the execution time of various operations.

    """

    def __init__(self) -> None:
        """Initialize the Timing instance.

        This method initializes the Timing instance, setting up the API, enabling
        the timing functionality, and preparing the timing dictionary.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self.api: BASEAPI = API
        self.enabled: bool = True

        self.timing: dict[str, Any] = {}

        self.api("libs.api:add.apis.for.object")(__name__, self)

    @AddAPI("toggle", description="toggle the enabled flag")
    def _api_toggle(self, tbool: bool | None = None) -> None:
        """Toggle the enabled flag.

        This method toggles the enabled flag for the Timing instance. If a boolean
        value is provided, it sets the enabled flag to that value. Otherwise, it
        toggles the current state of the enabled flag.

        Args:
            tbool: Optional boolean value to set the enabled flag.

        Returns:
            None

        Raises:
            None

        """
        self.enabled = not self.enabled if tbool is None else bool(tbool)

    @AddAPI("start", description="start a timer")
    def _api_start(self, timername: str = "", args: Any | None = None) -> str | None:
        """Start a timer with a unique identifier.

        This method starts a timer with a unique identifier and logs the start time
        using the API. It records the timer name, start time, owner ID, and any
        additional arguments provided.

        Args:
            timername: The name of the timer.
            args: Optional arguments to be associated with the timer.

        Returns:
            The unique identifier of the started timer, or None if timing is disabled.

        Raises:
            None

        """
        uid = uuid4().hex
        if self.enabled:
            owner_id = self.api("libs.api:get.caller.owner")()
            self.timing[uid] = {
                "name": timername,
                "start": default_timer(),
                "owner_id": owner_id,
                "args": args,
            }
            LogRecord(
                f"starttimer - {uid} {timername:<20} : started - from {owner_id} with args {args}",
                level="debug",
                sources=[__name__, owner_id],
            )()
            return uid
        return None

    @AddAPI("finish", description="finish a timer")
    def _api_finish(self, uid: str) -> float | None:
        """Finish a timer and log the elapsed time.

        This method finishes a timer identified by its unique identifier and logs
        the elapsed time using the API. It calculates the time taken for the timer
        and logs the information, including any associated arguments.

        Args:
            uid: The unique identifier of the timer to finish.

        Returns:
            The elapsed time in milliseconds, or None if timing is disabled or the
                timer is not found.

        Raises:
            None

        """
        if self.enabled:
            timerfinish = default_timer()
            if uid in self.timing:
                timername = self.timing[uid]["name"]
                time_taken = (timerfinish - self.timing[uid]["start"]) * 1000.0
                if args := self.timing[uid]["args"]:
                    LogRecord(
                        f"finishtimer - {uid} {timername:<20} : finished in "
                        f"{time_taken} ms - with args {args}",
                        level="debug",
                        sources=[__name__, self.timing[uid]["owner_id"]],
                    )()
                else:
                    LogRecord(
                        f"finishtimer - {uid} {timername:<20} : finished in {time_taken} ms",
                        level="debug",
                        sources=[__name__, self.timing[uid]["owner_id"]],
                    )()
                del self.timing[uid]
                return time_taken
            owner_id = self.api("libs.api:get.caller.owner")()
            LogRecord(
                f"finishtimer - {uid} not found - called from {owner_id}",
                level="error",
                sources=[__name__, owner_id],
            )()
        return None


TIMING = Timing()
