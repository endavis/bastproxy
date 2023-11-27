# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_apiitem.py
#
# File Description: holds the apiitem class
#
# By: Bast
"""
Hold the APIItem class that wraps an API function to track its use and
provide information about it.
"""
# Standard Library
import typing
import inspect

# Third Party

# Project
from ._apistats import STATS_MANAGER, APIStatItem
from ._functools import get_caller_owner_id, get_args

class APIItem:
    """
    Wraps an API function to track its use.
    """
    def __init__(self, full_api_name: str, tfunction: typing.Callable, owner_id: str | None,
                 description: list | str ='') -> None:
        """
        Initializes an APIItem object.

        Args:
            full_api_name (str): Full name of the API, e.g. 'plugins.core.log:reset
            tfunction (callable): The function to be wrapped.
            owner_id (str): Unique id of the owner calling the function.
        """
        self.full_api_name: str = full_api_name
        self.owner_id: str = owner_id or 'unknown'
        self.tfunction: typing.Callable = tfunction
        self.instance: bool = False
        self.overwritten_api: APIItem | None = None
        if not description:
            comments = inspect.getcomments(self.tfunction)
            comments = comments[2:].strip() if comments else ''
            description = comments.split('\n')
        elif isinstance(description, str):
            description = description.split('\n')

        self.description: list = description

    def __call__(self, *args, **kwargs):
        """
        Calls the wrapped function and adds a call to the StatsManager object.
        """
        caller_id: str = get_caller_owner_id()
        STATS_MANAGER.add_call(self.full_api_name, caller_id)
        return self.tfunction(*args, **kwargs)

    @property
    def count(self) -> int:
        """
        Returns the number of times the API has been called.

        Returns:
            int: The number of times the API has been called.
        """
        if stats := STATS_MANAGER.stats.get(self.full_api_name, None):
            return stats.count
        return 0

    @property
    def stats(self) -> APIStatItem | None:
        """
        Returns the stats for the API.

        Returns:
            dict: A dictionary of the stats for the API.
        """
        if _ := STATS_MANAGER.stats.get(self.full_api_name, None):
            return STATS_MANAGER.stats[self.full_api_name]
        else:
            return None

    def detail(self, show_function_code=False) -> list[str]:
        """
        create a detailed message for this item
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
            '',
        ]

        args = get_args(self.tfunction)

        location_split = self.full_api_name.split(':')
        name = location_split[0]
        command_name = ':'.join(location_split[1:])
        tdict = {'name':name, 'cmdname':command_name, 'api_location':self.full_api_name}

        tmsg.append(f"@G{self.full_api_name}@w({args})")
        if self.tfunction.__doc__:
            tmsg.append(self.tfunction.__doc__ % tdict)

        if sourcefile := inspect.getsourcefile(self.tfunction):
            from ._api import API
            tmsg.append('')
            tmsg.append(f"function defined in {sourcefile.replace(str(API.BASEPATH), '')}")

        if show_function_code:
            tmsg.append('')
            text_list, _ = inspect.getsourcelines(self.tfunction)
            tmsg.extend([i.replace('@', '@@').rstrip('\n') for i in text_list])

        if self.overwritten_api:
            tmsg.append('')
            tmsg.extend(('', "This API overwrote the following:"))
            tmsg.extend(f"    {line}" for line in self.overwritten_api.detail())

        return tmsg

    def __repr__(self) -> str:
        """
        Returns a string representation of the APIItem object.

        Returns:
            str: A string representation of the object.
        """
        return f"APIItem({self.full_api_name}, {self.owner_id}, {self.tfunction})"

    def __str__(self) -> str:
        """
        Returns a string representation of the APIItem object.

        Returns:
            str: A string representation of the object.
        """
        return f"APIItem({self.full_api_name}, {self.owner_id}, {self.tfunction})"
