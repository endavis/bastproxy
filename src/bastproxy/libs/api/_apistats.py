# Project: bastproxy
# Filename: libs/api/_apstats.py
#
# File Description: holds the functionality to track api stats
#
# By: Bast
"""Module for tracking API call statistics.

This module provides classes to track the number of times specific APIs are called
by different callers. It includes functionality to log detailed call information
and manage statistics for multiple APIs.

Key Components:
    - APIStatItem: A class to track the number of calls to a specific API.
    - StatsManager: A class to manage statistics for multiple APIs.

Features:
    - Track the number of calls to specific APIs.
    - Log detailed call information, including caller IDs.
    - Manage statistics for multiple APIs.

Usage:
    - Instantiate `APIStatItem` to track calls to a specific API.
    - Use `StatsManager` to manage statistics for multiple APIs.
    - Add calls to the statistics using `add_call` methods.
    - Retrieve statistics using `get_all_stats` and `get_stats` methods.

Classes:
    - `APIStatItem`: Represents a class that tracks the number of calls to a specific
        API.
    - `StatsManager`: Represents a class that manages statistics for multiple APIs.

"""
# Standard Library

# Third Party

# Project
from ._functools import stackdump


class APIStatItem:
    """Tracks the number of calls to a specific API."""

    def __init__(self, full_api_name: str) -> None:
        """Initialize an APIStatItem object.

        Args:
            full_api_name: Full name of the API, including the full package,
                module, and name of the function.

        """
        self.full_api_name: str = full_api_name
        self.calls_by_caller: dict[str, int] = {}
        self.detailed_calls: dict[str, int] = {}
        self.count: int = 0  # Total number of calls to this API

    def add_call(self, caller_id: str) -> None:
        """Add a call to the APIStatItem object.

        This method increments the call count for the API and logs detailed call
        information, including the caller ID. If the caller ID is unknown, a stack
        trace is logged.

        Args:
            caller_id: ID of the caller making the API call.

        Returns:
            None

        Raises:
            None

        """
        self.count += 1
        if not caller_id or caller_id == "unknown":
            stack = stackdump(
                msg=(
                    "------------ Unknown caller_id for API call: "
                    f"{self.full_api_name} -----------------"
                )
            )
            stack.insert(0, "\n")
            try:
                from bastproxy.libs.records import LogRecord

                LogRecord(stack, level="warning", sources=[__name__])()
            except ImportError:
                print("\n".join(stack))
                print()
        if caller_id not in self.detailed_calls:
            self.detailed_calls[caller_id] = 0
        self.detailed_calls[caller_id] += 1

        if ":" in caller_id:
            caller_id = caller_id.split(":")[0]
        if caller_id not in self.calls_by_caller:
            self.calls_by_caller[caller_id] = 0
        self.calls_by_caller[caller_id] += 1


class StatsManager:
    """Manages statistics for multiple APIs."""

    def __init__(self) -> None:
        """Initialize a StatsManager object.

        This method initializes a StatsManager object, which manages statistics
        for multiple APIs.

        """
        self.stats: dict[str, APIStatItem] = {}

    def add_call(self, full_api_name: str, caller_id: str) -> None:
        """Add a call to the statistics for a specific API.

        This method increments the call count for the specified API and logs
        detailed call information, including the caller ID. If the caller ID is
        unknown, a stack trace is logged.

        Args:
            full_api_name: Full name of the API, including the full package,
                module, and name of the function.
            caller_id: ID of the caller making the API call.

        Returns:
            None

        Raises:
            None

        """
        if full_api_name not in self.stats:
            self.stats[full_api_name] = APIStatItem(full_api_name)
        self.stats[full_api_name].add_call(caller_id)

    def get_all_stats(self) -> dict[str, APIStatItem]:
        """Retrieve statistics for all APIs.

        This method returns a dictionary containing statistics for all tracked APIs.
        Each key in the dictionary is the full name of an API, and the corresponding
        value is an `APIStatItem` object that tracks the number of calls to that API.

        Returns:
            A dictionary containing `APIStatItem` objects for all tracked APIs.

        Raises:
            None

        """
        return self.stats

    def get_stats(self, full_api_name: str) -> APIStatItem:
        """Retrieve statistics for a specific API.

        This method returns an `APIStatItem` object that tracks the number of calls
        to the specified API. If the API is not already tracked, a new `APIStatItem`
        object is created and added to the statistics.

        Args:
            full_api_name: Full name of the API, including the full package,
                module, and name of the function.

        Returns:
            An `APIStatItem` object that tracks the number of calls to the specified
                API.

        Raises:
            None

        """
        if full_api_name not in self.stats:
            self.stats[full_api_name] = APIStatItem(full_api_name)
        return self.stats.get(full_api_name)


# return self.stats.setdefault(full_api_name, APIStatItem(full_api_name))

STATS_MANAGER = StatsManager()
