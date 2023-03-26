# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/asynch/task_logger.py
#
# File Description: a module to handle exceptions for tasks
#
# From: https://quantlane.com/blog/ensure-asyncio-task-exceptions-get-logged/
#
# By: Vita/Bast
# Standard Library
from typing import Any, Coroutine, Optional, TypeVar, Tuple

import asyncio
import functools

# 3rd Party

# Project
from libs.api import API
from libs.records import LogRecord

api = API(parent_id=__name__)

T = TypeVar('T')

def create_task(
    coroutine: Coroutine[Any, Any, T],
    *,
    message: str = '',
    loop: Optional[asyncio.AbstractEventLoop] = None,
    name: str = '',
) -> 'asyncio.Task[T]':  # This type annotation has to be quoted for Python < 3.9, see https://www.python.org/dev/peps/pep-0585/
    '''
    This helper function wraps a ``loop.create_task(coroutine())`` call and ensures there is
    an exception handler added to the resulting task. If the task raises an exception it is logged
    using the provided ``logger``, with additional context provided by ``message``.
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
    message: str = '',
) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    # Add the pylint ignore: we want to handle all exceptions here so that the result of the task
    # is properly logged. There is no point re-raising the exception in this callback.
    except Exception as e:  # pylint: disable=broad-except
        LogRecord(f"exception in task {task.get_name()} {e} {e.args} {message}",
                  level='error', sources=['asyncio'], exc_info=True).send()
