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
    - TimedBlock: A context manager that times a block and always finishes the timer.

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
    - `TimedBlock`: Times a ``with`` block, finishing the timer even when it raises.

"""

# Standard Library
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from timeit import default_timer
from typing import Any
from uuid import uuid4

# 3rd Party
# Project
from bastproxy.libs.api import API as BASEAPI
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to

API_OWNER = "libs.timing"
API = BASEAPI(owner_id=API_OWNER)


@dataclass(slots=True)
class TimerRecord:
    """One running timer: its name, start time, owning caller and arguments."""

    name: str
    start: float
    owner_id: str
    args: Any = None


class TimedBlock:
    """Time a ``with`` block, finishing the timer even when the block raises.

    ``elapsed`` holds the finish result once the block exits.
    """

    # No owner_id or api attribute: get_caller_owner_id walks the ``self`` of each
    # frame, so this frame must not look like an owner. It is skipped to the caller.

    def __init__(self, name: str, args: Any = None) -> None:
        self.name = name
        self.args = args
        self.uid: str | None = None
        self.elapsed: float | None = None

    def __enter__(self) -> "TimedBlock":
        self.uid = API("libs.timing:timing.start")(self.name, self.args)
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.elapsed = API("libs.timing:timing.finish")(self.uid)


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
        It logs the start and finish times using the API. The timer finishes
        even when the wrapped function raises.

        Args:
            *arg: Positional arguments passed to the wrapped function.

        Returns:
            The result of the wrapped function.

        Raises:
            None

        """
        with TimedBlock(func.__name__, arg):
            return func(*arg)

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

        self.timing: dict[str, TimerRecord] = {}

        self.api("libs.api:api.add.for.object")(API_OWNER, self)

    @AddAPI("timing.toggle", description="toggle the enabled flag")
    def _api_timing_toggle(self, tbool: bool | None = None) -> None:
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

    @AddAPI("timing.start", description="start a timer")
    def _api_timing_start(self, timername: str = "", args: Any | None = None) -> str | None:
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
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.api.owner_id])
            self.timing[uid] = TimerRecord(
                name=timername,
                start=default_timer(),
                owner_id=owner_id,
                args=args,
            )
            log_to(
                [__name__, owner_id],
                logging.DEBUG,
                "starttimer - %s %-20s : started - from %s with args %s",
                uid,
                timername,
                owner_id,
                args,
            )
            return uid
        return None

    @AddAPI("timing.finish", description="finish a timer")
    def _api_timing_finish(self, uid: str | None) -> float | None:
        """Finish a timer and log the elapsed time.

        This method finishes a timer identified by its unique identifier and logs
        the elapsed time using the API. It calculates the time taken for the timer
        and logs the information, including any associated arguments.

        Args:
            uid: The unique identifier of the timer to finish. None means the timer
                was started while timing was disabled, so there is nothing to finish.

        Returns:
            The elapsed time in milliseconds, or None if timing is disabled, uid is
                None or the timer is not found.

        Raises:
            None

        """
        if uid is None:
            return None
        timerfinish = default_timer()
        if uid in self.timing:
            # Always remove the entry, even when timing was turned off after the
            # timer started, so it does not leak (#190).
            timer = self.timing.pop(uid)
            if not self.enabled:
                return None
            timername = timer.name
            time_taken = (timerfinish - timer.start) * 1000.0
            if args := timer.args:
                log_to(
                    [__name__, timer.owner_id],
                    logging.DEBUG,
                    "finishtimer - %s %-20s : finished in %s ms - with args %s",
                    uid,
                    timername,
                    time_taken,
                    args,
                )
            else:
                log_to(
                    [__name__, timer.owner_id],
                    logging.DEBUG,
                    "finishtimer - %s %-20s : finished in %s ms",
                    uid,
                    timername,
                    time_taken,
                )
            return time_taken
        if self.enabled:
            owner_id = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.api.owner_id])
            log_to(
                [__name__, owner_id],
                logging.ERROR,
                "finishtimer - %s not found - called from %s",
                uid,
                owner_id,
            )
        return None


TIMING = Timing()
