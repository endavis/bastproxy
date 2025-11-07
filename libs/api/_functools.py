# Project: bastproxy
# Filename: libs/api/_functools.py
#
# File Description: holds items related to functions and call stacks
#
# By: Bast
"""Module for handling function-related utilities and call stack operations.

This module provides utilities for working with function call stacks and
retrieving function arguments. It includes methods for dumping the current
stack trace, identifying the caller's owner ID, and extracting function
arguments.

Key Components:
    - stackdump: Function to dump the current stack trace.
    - get_caller_owner_id: Function to get the owner ID of the caller.
    - get_args: Function to retrieve the arguments of a given function.

Features:
    - Stack trace dumping with optional message and ID.
    - Identification of the caller's owner ID, with support for ignoring
        specific owner IDs.
    - Retrieval of function arguments from the function declaration.

Usage:
    - Use `stackdump` to get a formatted stack trace.
    - Use `get_caller_owner_id` to find the owner ID of the caller.
    - Use `get_args` to get the arguments of a given function.

Functions:
    - `stackdump`: Dumps the current stack trace.
    - `get_caller_owner_id`: Returns the owner ID of the caller.
    - `get_args`: Retrieves the arguments of a given function.

"""
# Standard Library
import inspect
import logging
import traceback
from collections.abc import Callable
from functools import lru_cache
from itertools import chain

# Third Party

# Project


def stackdump(id: str = "", msg: str = "") -> list[str]:
    """Dump the current stack trace.

    This function extracts and formats the current stack trace, optionally
    appending a message and an ID to the output.

    Args:
        id: An optional identifier to append to the stack trace.
        msg: An optional message to append to the stack trace.

    Returns:
        A list of strings representing the formatted stack trace.

    Raises:
        None

    """
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
        lines.append(f"LEAVING STACK_DUMP: {id}" if id else "")

    return lines


def get_caller_owner_id(ignore_owner_list: list[str] | None = None) -> str:
    """Return the owner ID of the caller.

    This function inspects the call stack to determine the owner ID of the caller,
    ignoring any owner IDs specified in the ignore list.

    Args:
        ignore_owner_list: A list of owner IDs to ignore.

    Returns:
        The owner ID of the caller.

    Raises:
        None

    """
    ignore_list = ignore_owner_list or []

    caller_id = "unknown"

    from ._api import API
    from ._apiitem import APIItem

    if frame := inspect.currentframe():
        while frame := frame.f_back:
            if "self" in frame.f_locals and not isinstance(
                frame.f_locals["self"], APIItem
            ):
                tcs = frame.f_locals["self"]
                if (
                    hasattr(tcs, "owner_id")
                    and tcs.owner_id
                    and tcs.owner_id not in ignore_list
                ):
                    caller_id = tcs.owner_id
                    break
                if (
                    hasattr(tcs, "api")
                    and isinstance(tcs.api, API)
                    and tcs.api.owner_id
                    and tcs.api.owner_id not in ignore_list
                ):
                    caller_id = tcs.api.owner_id
                    break

    if caller_id == "unknown":
        logger = logging.getLogger(__name__)
        logger.warn(f"Unknown caller_id for API call: {inspect.stack()[1][3]}")

    return caller_id


@lru_cache(maxsize=128)
def get_args(api_function: Callable) -> str:
    """Retrieve the arguments of a given function.

    This function inspects the signature of the provided function and extracts
    its arguments, excluding 'self'. The arguments are formatted and returned
    as a string.

    Args:
        api_function: The function whose arguments are to be retrieved.

    Returns:
        A string representing the formatted arguments of the function.

    Raises:
        None

    """
    sig = inspect.signature(api_function)
    argn: list[str] = [f"@Y{str(i)}@w" for i in sig.parameters if str(i) != "self"]
    args: str = ", ".join(argn)

    return args
