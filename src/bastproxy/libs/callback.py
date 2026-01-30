# Project: bastproxy
# Filename: libs/callback.py
#
# File Description: a class to track callbacks
#
# By: Bast
"""Module for tracking and managing callback functions.

This module provides the `Callback` class, which allows for the tracking and
management of callback functions. It includes methods for executing the callback,
checking equality, and generating a hash for the callback, making it a valuable
tool for managing event-driven programming.

Key Components:
    - Callback: A class that represents a callback function with tracking capabilities.

Features:
    - Automatic tracking of callback execution count and last execution time.
    - Equality checks between callback instances and functions.
    - Hash generation for callback instances.
    - String representation of callback instances.

Usage:
    - Instantiate `Callback` to create a callback object with a specific function.
    - Use the `execute` method to run the callback function.
    - Compare callback instances using equality operators.
    - Generate a hash for a callback instance using the `__hash__` method.

Classes:
    - `Callback`: Represents a class that tracks and manages callback functions.

"""

# Standard Library
import datetime
from collections.abc import Callable
from typing import Any

# 3rd Party
# Project
from bastproxy.libs.api import API


class Callback:
    """Class to track and manage callback functions.

    This class provides methods for executing the callback, checking equality,
    and generating a hash for the callback. It also tracks the execution count
    and the last execution time of the callback.
    """

    def __init__(
        self, name: str, owner_id: str, func: Callable, enabled: bool = True
    ) -> None:
        """Initialize the callback with the given parameters.

        Args:
            name: The name of the callback.
            owner_id: The ID of the owner of the callback.
            func: The function to be called when the callback is executed.
            enabled: Whether the callback is enabled or not. Defaults to True.

        """
        self.name: str = name
        self.owner_id: str = owner_id or f"{owner_id}:callback:{name}"
        self.api = API(owner_id=self.owner_id)
        self.raised_count: int = 0
        self.func: Callable = func
        self.enabled: bool = enabled
        self.created_time: datetime.datetime = datetime.datetime.now(datetime.UTC)
        self.last_raised_datetime: datetime.datetime | None = None

    def __hash__(self) -> int:
        """Generate a hash for the callback.

        This method generates a unique hash for the callback instance based on its
        function, owner ID, name, and creation time.

        Returns:
            int: The generated hash value.

        """
        return (
            hash(self.func)
            + hash(self.owner_id)
            + hash(self.name)
            + hash(self.created_time)
        )

    def __eq__(self, other_function: Any) -> bool:
        """Check equality between this callback and another function or callback.

        This method checks if the given function or callback is equal to this callback
        instance. It compares the hash values if the other object is a Callback
        instance, or directly compares the functions if the other object is a callable.

        Args:
            other_function: The function or callback to compare against this callback.

        Returns:
            bool: True if the functions or callbacks are equal, False otherwise.

        """
        if isinstance(other_function, Callback):
            return hash(self) == hash(other_function)

        return isinstance(other_function, Callable) and other_function == self.func

    def execute(self, args: dict | None = None) -> Any:
        """Execute the callback function.

        This method executes the callback function with the provided arguments, if any.
        It updates the last execution time and increments the execution count.

        Args:
            args: The arguments to pass to the callback function. Defaults to None.

        Returns:
            Any: The result of the callback function execution.

        Raises:
            Exception: If the callback function raises an exception.

        """
        self.last_raised_datetime = datetime.datetime.now(datetime.UTC)
        self.raised_count = self.raised_count + 1
        return self.func(args) if args else self.func()

    def __str__(self) -> str:
        """Return a string representation of the callback.

        This method returns a string that represents the callback instance, including
        its name and owner ID.

        Returns:
            str: The string representation of the callback.

        """
        return f"Event {self.name:<10} : {self.owner_id:<15}"
