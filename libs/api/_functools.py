# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_functools.py
#
# File Description: holds items related to functions and call stacks
#
# By: Bast
"""
tools to work with functions and call stacks
"""
# Standard Library
import traceback
import inspect
import logging
import typing
from functools import lru_cache
from itertools import chain

# Third Party

# Project

def stackdump(id='', msg='') -> list[str]:
    raw_tb = traceback.extract_stack()
    entries: list[str] = traceback.format_list(raw_tb)

    # Remove the last two entries for the call to extract_stack() and to
    # the one before that, this function. Each entry consists of single
    # string with consisting of two lines, the script file path then the
    # line of source code making the call to this function.
    del entries[-2:]

    # Split the stack entries on line boundaries.
    lines = list(chain.from_iterable(line.splitlines() for line in entries if line))
    if msg:  # Append it to last line with name of caller function.
        lines.insert(0, msg)
        lines.append(f'LEAVING STACK_DUMP: {id}' if id else '')

    return lines

def get_caller_owner_id(ignore_owner_list: list[str] | None = None) -> str:
    """
    Returns the owner ID of the plugin that called the current function.

    It goes through the stack and checks each frame for one of the following:
        an owner_id attribute
        an api attribute and gets the owner_id from that

    Args:
        ignore_owner_list (list[str]): A list of owner IDs to ignore if they are on the stack.

    Returns:
        str: The owner ID of the plugin on the stack.
    """
    ignore_list = ignore_owner_list or []

    caller_id = 'unknown'

    from ._api import API
    from ._apiitem import APIItem

    if frame := inspect.currentframe():
        while frame := frame.f_back:
            if 'self' in frame.f_locals and not isinstance(frame.f_locals['self'], APIItem):
                tcs = frame.f_locals['self']
                if (
                    hasattr(tcs, 'owner_id')
                    and tcs.owner_id
                    and tcs.owner_id not in ignore_list
                ):
                    caller_id = tcs.owner_id
                    break
                if (
                    hasattr(tcs, 'api')
                    and isinstance(tcs.api, API)
                    and tcs.api.owner_id
                    and tcs.api.owner_id not in ignore_list
                ):
                    caller_id = tcs.api.owner_id
                    break

    if caller_id == 'unknown':
        logger = logging.getLogger(__name__)
        logger.warn(f"Unknown caller_id for API call: {inspect.stack()[1][3]}")

    return caller_id

@lru_cache(maxsize=128)
def get_args(api_function: typing.Callable) -> str:
    """
    Get the arguments of a given function from a it's function declaration.

    Parameters
    ----------
    api_function : Callable
        The function to get the arguments for.

    Returns
    -------
    str
        A string containing the function arguments.
    """
    sig = inspect.signature(api_function)
    argn: list[str] = [f"@Y{str(i)}@w" for i in sig.parameters if str(i) != 'self']
    args: str = ', '.join(argn)

    return args
