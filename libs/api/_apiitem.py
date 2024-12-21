# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_apiitem.py
#
# File Description: holds the apiitem class
#
# By: Bast
"""Module for managing API items with tracking and descriptive capabilities.

This module provides the `APIItem` class, which wraps API functions to track their
usage and provide detailed information about them. It integrates with a statistics
manager to record the number of times an API has been called and to retrieve
statistical data about the API's usage.

Key Components:
    - APIItem: A class that wraps an API function to track its usage and provide
        detailed information about it.

Features:
    - Tracks the usage of API functions.
    - Provides detailed information about API functions, including their name, owner,
        and description.
    - Integrates with a statistics manager to record and retrieve API usage data.
    - Supports retrieving detailed descriptions and source code of API functions.
    - Handles overwriting of API functions and maintains information about the
        overwritten API.

Usage:
    - Instantiate `APIItem` with the full API name, function, owner ID, and description.
    - Call the `APIItem` instance to invoke the wrapped API function and track its
        usage.
    - Access properties like `count` and `stats` to retrieve usage statistics.
    - Use the `detail` method to get detailed information about the API function.

Classes:
    - `APIItem`: Represents an API function with tracking and descriptive capabilities.

"""
# Standard Library
import typing
import inspect

# Third Party

# Project
from ._apistats import STATS_MANAGER, APIStatItem
from ._functools import get_caller_owner_id, get_args


class APIItem:
    """Represents an API function with tracking and descriptive capabilities.

    This class wraps an API function to track its usage and provide detailed
    information about it, including its name, owner, and description. It also
    integrates with a StatsManager to record the number of times the API has
    been called and to retrieve statistical data about the API's usage.

    """

    def __init__(
        self,
        full_api_name: str,
        tfunction: typing.Callable,
        owner_id: str | None,
        description: list | str = "",
    ) -> None:
        """Initialize the APIItem with the given parameters.

        This constructor initializes the APIItem with the provided API name,
        function, owner ID, and description. It also sets up the instance and
        overwritten API attributes, and processes the description if it is
        not provided.

        Args:
            full_api_name: The full name of the API.
            tfunction: The function to be wrapped by the APIItem.
            owner_id: The ID of the owner of the API.
            description: A description of the API.

        Returns:
            None

        Raises:
            None


        """
        self.full_api_name: str = full_api_name
        self.owner_id: str = owner_id or "unknown"
        self.tfunction: typing.Callable = tfunction
        self.instance: bool = False
        self.overwritten_api: APIItem | None = None
        if not description:
            comments = inspect.getcomments(self.tfunction)
            comments = comments[2:].strip() if comments else ""
            description = comments.splitlines()
        elif isinstance(description, str):
            description = description.splitlines()

        self.description: list = description

    def __call__(self, *args, **kwargs):
        """Call the wrapped API function and track its usage.

        This method calls the wrapped API function with the provided arguments and
        keyword arguments. It also tracks the usage of the API by recording the
        caller's owner ID and updating the statistics manager.

        Args:
            *args: Positional arguments to pass to the API function.
            **kwargs: Keyword arguments to pass to the API function.

        Returns:
            The result of the API function call.

        Raises:
            None

        """
        caller_id: str = get_caller_owner_id()
        STATS_MANAGER.add_call(self.full_api_name, caller_id)
        return self.tfunction(*args, **kwargs)

    @property
    def count(self) -> int:
        """Return the count of times the API has been called.

        This property retrieves the count of times the API has been called from the
        statistics manager. If no statistics are found for the API, it returns 0.

        Returns:
            int: The count of times the API has been called.

        Raises:
            None

        """
        if stats := STATS_MANAGER.stats.get(self.full_api_name, None):
            return stats.count
        return 0

    @property
    def stats(self) -> APIStatItem:
        """Return the statistics for the API.

        This property retrieves the statistics for the API from the statistics manager.
        It provides detailed information about the API's usage, including the count of
        calls and other relevant metrics.

        Returns:
            APIStatItem: The statistics for the API.

        Raises:
            None

        """
        return STATS_MANAGER.get_stats(self.full_api_name)

    def detail(self, show_function_code: bool = False) -> list[str]:
        """Return detailed information about the API.

        This method generates a detailed description of the API, including its name,
        owner, description, function code, and other relevant information. It can
        optionally include the source code of the function.

        Args:
            show_function_code: Whether to include the function's source code.

        Returns:
            A list of strings containing detailed information about the API.

        Raises:
            None

        """
        description = []
        for i, line in enumerate(self.description):
            if not line:
                continue
            if i == 0:
                description.append(f"@C{'Description':<11}@w : {line}")
            else:
                description.append(f"{'':<13}   {line}")

        tmsg: list[str] = [
            f"@C{'API':<11}@w : {self.full_api_name}",
            *description,
            f"@C{'Function':<11}@w : {self.tfunction}",
            f"@C{'Owner':<11}@w : {self.owner_id}",
            f"@C{'Instance':<11}@w : {self.instance}",
            "",
        ]

        args = get_args(self.tfunction)

        location_split = self.full_api_name.split(":")
        name = location_split[0]
        command_name = ":".join(location_split[1:])
        tdict = {
            "name": name,
            "cmdname": command_name,
            "api_location": self.full_api_name,
        }

        tmsg.append(f"@G{self.full_api_name}@w({args})")
        if self.tfunction.__doc__:
            tmsg.append(self.tfunction.__doc__ % tdict)

        if sourcefile := inspect.getsourcefile(self.tfunction):
            from ._api import API

            tmsg.append("")
            tmsg.append(
                f"function defined in {sourcefile.replace(str(API.BASEPATH), '')}"
            )

        if show_function_code:
            tmsg.append("")
            text_list, _ = inspect.getsourcelines(self.tfunction)
            tmsg.extend([i.replace("@", "@@").rstrip("\n") for i in text_list])

        if self.overwritten_api:
            tmsg.append("")
            tmsg.extend(("", "This API overwrote the following:"))
            tmsg.extend(f"    {line}" for line in self.overwritten_api.detail())

        return tmsg

    def __repr__(self) -> str:
        """Return a string representation of the APIItem object.

        This method returns a string that provides a concise representation of the
        APIItem object, including its full API name, owner ID, and the wrapped
        function.

        Returns:
            str: A string representation of the APIItem object.

        Raises:
            None

        """
        return f"APIItem({self.full_api_name}, {self.owner_id}, {self.tfunction})"

    def __str__(self) -> str:
        """Return a human-readable string representation of the APIItem object.

        This method returns a human-readable string that provides a detailed
        representation of the APIItem object, including its full API name, owner ID,
        and the wrapped function.

        Returns:
            str: A human-readable string representation of the APIItem object.

        Raises:
            None

        """
        return f"APIItem({self.full_api_name}, {self.owner_id}, {self.tfunction})"
