# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/task_logger.py
#
# File Description: a plugin to handle exceptions for tasks
#
# From: https://quantlane.com/blog/ensure-asyncio-task-exceptions-get-logged/
#
# By: Vita/Bast
# Standard Library
from typing import Any, Coroutine, Optional, TypeVar, Tuple

import asyncio
import functools
import logging

# 3rd Party

# Project
from libs.api import API
api = API()

T = TypeVar('T')

def create_task(
    coroutine: Coroutine[Any, Any, T],
    *,
    message: str = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    name: str = '',
) -> 'asyncio.Task[T]':  # This type annotation has to be quoted for Python < 3.9, see https://www.python.org/dev/peps/pep-0585/
    '''
    This helper function wraps a ``loop.create_task(coroutine())`` call and ensures there is
    an exception handler added to the resulting task. If the task raises an exception it is logged
    using the provided ``logger``, with additional context provided by ``message`` and optionally
    ``message_args``.
    '''
    if loop is None:
        loop = asyncio.get_running_loop()
    if name:
        task = loop.create_task(coroutine, name=name)
    else:
        task = loop.create_task(coroutine)
    task.add_done_callback(
        functools.partial(_handle_task_result, message = message)
    )
    return task


def _handle_task_result(
    task: asyncio.Task,
    *,
    message: str = None,
) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    # Ad the pylint ignore: we want to handle all exceptions here so that the result of the task
    # is properly logged. There is no point re-raising the exception in this callback.
    except Exception as e:  # pylint: disable=broad-except
        # print(f"exception in task {task.get_name()} {e}")
        # print(e.args)
        api('libs.io:send:traceback')(f"exception in task {task.get_name()}")
        #logger.exception(message, *message_args)