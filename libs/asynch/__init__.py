# Project: bastproxy
# Filename: libs/asynch/__init__.py
#
# File Description: a module to handle asynchronous tasks
#
# By: Bast
#
"""Module to handle asynchronous tasks.

This module provides classes and functions to manage and execute asynchronous tasks
using asyncio. It includes a task manager, a queue manager, and utility functions for
handling task results and shutdown processes.

Key Components:
    - TaskItem: Represents an asynchronous task item.
    - QueueManager: Manages the queue of tasks to be executed asynchronously.
    - _handle_task_result: Handles the result of an asyncio task.
    - shutdown: Handles the shutdown process.
    - run_asynch: Runs the asynchronous event loop.

Features:
    - Creation and management of asyncio tasks.
    - Logging of task creation and exceptions.
    - Queue management for asynchronous tasks.
    - Signal handling for graceful shutdown.

Usage:
    - Instantiate QueueManager to manage task queues.
    - Use TaskItem to create and manage individual tasks.
    - Call run_asynch to start the event loop and handle tasks.
    - Use shutdown to handle graceful shutdown on receiving signals.

Classes:
    - `TaskItem`: Represents an asynchronous task item.
    - `QueueManager`: Manages the queue of tasks to be executed asynchronously.

"""
# Standard Library
import asyncio
import functools
import signal
import warnings
from collections.abc import Callable
from typing import Awaitable, Coroutine, Optional

# 3rd Party
# Project
from libs.api import API as BASEAPI
from libs.records import LogRecord


def _handle_task_result(
    task: asyncio.Task,
    *,
    message: str = "",
) -> None:
    """Handle the result of an asyncio task.

    This function is called when an asyncio task completes. It logs any exceptions
    that occur during the execution of the task.

    Args:
        task: The asyncio task whose result is being handled.
        message: Additional message to include in the log record.

    Returns:
        None

    Raises:
        None

    """
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    # Add the pylint ignore: we want to handle all exceptions here so that the
    # result of the task is properly logged. There is no point re-raising the
    # exception in this callback.
    except Exception as e:  # pylint: disable=broad-except
        LogRecord(
            f"exception in task {task.get_name()} {e} {e.args} {message}",
            level="error",
            sources=["asyncio"],
            exc_info=True,
        )()


class TaskItem:
    """Represents an asynchronous task item.

    This class encapsulates an asynchronous task, providing methods to create and
    manage the task, check its completion status, and retrieve its result.
    """

    def __init__(
        self, func: Awaitable | Callable, name: str, startstring: str = ""
    ) -> None:
        """Initialize a TaskItem object.

        This constructor initializes the task item with the provided coroutine or
        callable function, name, and optional start string. It validates the type
        of the provided function and prepares the coroutine for execution.

        Args:
            func: The coroutine or callable function to be executed.
            name: The name of the task.
            startstring: Additional string to include in the log record
                when the task is created. Defaults to ''.

        Returns:
            None

        Raises:
            TypeError: If the provided function is neither a coroutine nor a callable.

        """
        self.func = func
        self.task = None
        self.name = name
        self.startstring = startstring
        if asyncio.iscoroutine(self.func):
            self.coroutine: Coroutine = self.func
        elif isinstance(self.func, Callable):
            self.coroutine: Coroutine = self.func()
        else:
            LogRecord(
                f"(Task) {self.name} : {func} is not a coroutine or callable",
                level="error",
                sources=[__name__],
            )()

    @property
    def done(self) -> bool:
        """Check if the task is done.

        This property returns True if the task has completed, otherwise False.

        Returns:
            True if the task is done, False otherwise.

        """
        return self.task.done() if self.task else False

    @property
    def result(self) -> Optional[object]:
        """Retrieve the result of the task.

        This property returns the result of the task if it has completed. If the task
        has not been created or is not yet done, it returns None.

        Returns:
            The result of the task if it is done, otherwise None.

        """
        return self.task.result() if self.task else None

    def create(
        self,
        message: str = "",
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> asyncio.Task:
        """Create and start the asynchronous task.

        This method creates an asyncio task from the provided coroutine and starts
        its execution. It logs the creation of the task and adds a callback to handle
        the task's result upon completion.

        Args:
            message: Additional message to include in the log record.
            loop: The asyncio event loop to use for creating the task. If None, the
            current running loop is used.

        Returns:
            asyncio.Task: The created asyncio task.

        Raises:
            RuntimeError: If the task cannot be created due to an invalid event loop.

        """
        LogRecord(
            f"(Task) (create) {self.name} : {self.startstring}",
            level="debug",
            sources=[__name__],
        )()
        if loop is None:
            loop = asyncio.get_running_loop()
        if self.name:
            self.task = loop.create_task(self.coroutine, name=self.name)
        else:
            self.task = loop.create_task(self.coroutine)
        self.task.add_done_callback(
            functools.partial(_handle_task_result, message=message)
        )
        LogRecord(
            f"(Task) {self.name} : {self.task}", level="debug", sources=[__name__]
        )()
        if self.startstring:
            LogRecord(
                f"(Task) {self.name} : Created - {self.startstring}",
                level="debug",
                sources=[__name__],
            )()
        else:
            LogRecord(
                f"(Task) {self.name} : Created", level="debug", sources=[__name__]
            )()
        return self.task


class QueueManager:
    """Manages the queue of tasks to be executed asynchronously."""

    def __init__(self) -> None:
        """Initialize the QueueManager.

        This constructor initializes the QueueManager instance, setting up the task
        queue and API for managing tasks. It prepares the queue to hold asyncio tasks
        and registers the API method for adding tasks to the queue.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        # holds the asyncio tasks to start after plugin initialization
        self.task_queue: asyncio.Queue[TaskItem] = asyncio.Queue()
        self.api = BASEAPI(owner_id=f"{__name__}:QueueManager")
        self.api("libs.api:add")("libs.asynch", "task.add", self._api_task_add)

    # add a task to the asyncio_tasks queue
    def _api_task_add(
        self, task: Awaitable | Callable, name: str, startstring: str = ""
    ) -> TaskItem:
        """Add a task to the asyncio tasks queue.

        This method adds a new task to the task queue for asynchronous execution.
        It creates a TaskItem from the provided coroutine or callable function and
        puts it in the task queue.

        Args:
            task: The coroutine or callable function to be executed.
            name: The name of the task.
            startstring: Additional string to include in the log record when the task
                is created. Defaults to ''.

        Returns:
            TaskItem: The created TaskItem object.

        Raises:
            None

        """
        new_task = TaskItem(task, name, startstring)
        self.task_queue.put_nowait(new_task)
        return new_task

    async def task_check_for_new_tasks(self) -> None:
        """Check for new tasks in the queue and create them.

        This coroutine continuously checks the task queue for new tasks. When a new
        task is found, it creates and starts the task, then logs the current state
        of all tasks. It sleeps for a short duration between checks to prevent
        excessive CPU usage.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        while True:
            task: TaskItem = await self.task_queue.get()

            task.create()

            LogRecord(
                f"Tasks - {asyncio.all_tasks()}", level="debug", sources=[__name__]
            )()

            await asyncio.sleep(0.1)


async def shutdown(signal_: signal.Signals, loop_: asyncio.AbstractEventLoop) -> None:
    """Handle the shutdown process.

    This coroutine handles the shutdown process when a termination signal is received.
    It logs the received signal, initiates the shutdown process for the proxy, cancels
    all outstanding tasks, and stops the event loop.

    Args:
        signal_: The signal that triggered the shutdown.
        loop_: The asyncio event loop to stop.

    Returns:
        None

    Raises:
        None

    """
    api = BASEAPI(owner_id=f"{__name__}:shutdown")
    LogRecord(
        f"shutdown - Received exit signal {signal_}:{signal_.name}",
        level="warning",
        sources=["mudproxy"],
    )()

    api("plugins.core.proxy:shutdown")()

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    LogRecord(
        f"shutdown - Cancelling {len(tasks)} outstanding tasks",
        level="warning",
        sources=["mudproxy"],
    )()
    for item in tasks:
        LogRecord(
            f"shutdown -     {item.get_name()}", level="warning", sources=["mudproxy"]
        )()

    [task.cancel() for task in tasks]

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    if new_exceptions := [
        exc for exc in exceptions if not isinstance(exc, asyncio.CancelledError)
    ]:
        LogRecord(
            f"shutdown - Tasks had Exceptions: {new_exceptions}",
            level="warning",
            sources=["mudproxy"],
        )()
    else:
        LogRecord(
            "shutdown - All tasks cancelled", level="warning", sources=["mudproxy"]
        )()

    loop_.stop()


def run_asynch() -> None:
    """Run the asynchronous event loop.

    This function sets up the asyncio event loop, configures signal handlers for
    graceful shutdown, and starts the event loop to process tasks. It initializes
    the QueueManager and creates a task to check for new tasks in the queue.

    Args:
        None

    Returns:
        None

    Raises:
        None

    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    LogRecord(
        "__main__ - setting up signal handlers", level="info", sources=["mudproxy"]
    )()
    # for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
    for sig in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        LogRecord(
            f"adding signal handler for {sig}:{sig.name}",
            level="info",
            sources=[__name__],
        )()
        # ignore RuntimeWarning about coroutine never awaited
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            task_item: TaskItem = TaskItem(
                func=shutdown(sig, loop), name=f"{sig.name} shutdown handler"
            )
        loop.add_signal_handler(sig, lambda: task_item.create())

    loop.create_task(QUEUEMANAGER.task_check_for_new_tasks(), name="New Task Checker")

    LogRecord("__main__ - run_forever", level="debug", sources=["mudproxy"])()
    loop.run_forever()


QUEUEMANAGER = QueueManager()
