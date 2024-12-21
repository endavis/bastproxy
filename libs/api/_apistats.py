# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_apstats.py
#
# File Description: holds the functionality to track api stats
#
# By: Bast
"""Implementation of the StatsManager class to track API stats.
"""
# Standard Library

# Third Party

# Project
from ._functools import stackdump


class APIStatItem:
    """This class is used to track the number of times that a particular
    API has been called by a particular caller.  The full_api_name is
    the full name of the API, including the full package, module,
    and name of the function, and the caller_id is the ID of
    the object/function that is making the call.
    """

    def __init__(self, full_api_name: str) -> None:
        """Initializes an APIStatItem object.

        Args:
            full_api_name (str): Full name of the API, including the full package,
                module, and name of the function.

        """
        self.full_api_name: str = full_api_name
        self.calls_by_caller: dict[str, int] = {}
        self.detailed_calls: dict[str, int] = {}
        self.count: int = 0  # Total number of calls to this API

    def add_call(self, caller_id: str) -> None:
        """Adds a call to the APIStatItem object.

        Args:
            caller_id (str): ID of the caller

        """
        self.count += 1
        if not caller_id or caller_id == "unknown":
            stack = stackdump(
                msg=f"------------ Unknown caller_id for API call: {self.full_api_name} -----------------"
            )
            stack.insert(0, "\n")
            try:
                from libs.records import LogRecord

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
    """Holds the stats for all API items."""

    def __init__(self) -> None:
        """Initializes a StatsManager object."""
        self.stats: dict[str, APIStatItem] = {}

    def add_call(self, full_api_name: str, caller_id: str) -> None:
        """Adds a call to the StatsManager object.

        Args:
            full_api_name (str): Full name of the API, including the full package,
                module, and name of the function.
            caller_id (str): Id of what object is calling the function

        """
        if full_api_name not in self.stats:
            self.stats[full_api_name] = APIStatItem(full_api_name)
        self.stats[full_api_name].add_call(caller_id)

    def get_all_stats(self) -> dict[str, APIStatItem]:
        """Returns the stats held in the StatsManager object.

        Returns:
            dict: A dictionary of the stats held in the object.

        """
        return self.stats

    def get_stats(self, full_api_name) -> APIStatItem | None:
        """Returns the stats for a specific API.

        Args:
            full_api_name (str): Full name of the API, including the full package,
                module, and name of the function.

        Returns:
            dict: A dictionary of the stats for the API.

        """
        return self.stats.get(full_api_name, None)


STATS_MANAGER = StatsManager()
