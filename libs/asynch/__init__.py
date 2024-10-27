# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/asynch/__init__.py
#
# File Description: a module to handle asynchronous tasks
#
#
# By: Bast
# Standard Library
import asyncio
import signal
import functools
import warnings
from typing import Callable, Awaitable, Coroutine, Optional

# 3rd Party

# Project
from libs.api import API as BASEAPI
from libs.records import LogRecord

def _handle_task_result(
    task: asyncio.Task,
    *,
    message: str = '',
) -> None:
    """
    Handle the result of an asyncio task.

    This function retrieves the result of the task and logs any exceptions that occurred.
    If the task was cancelled, it is not logged as an error.
    If an exception occurred, it is logged as an error along with the task name and any provided message.

    Args:
        task (asyncio.Task): The asyncio task to handle.
        message (str, optional): Additional message to include in the log record. Defaults to ''.

    Returns:
        None
    """
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # Task cancellation should not be logged as an error.
    # Add the pylint ignore: we want to handle all exceptions here so that the result of the task
    # is properly logged. There is no point re-raising the exception in this callback.
    except Exception as e:  # pylint: disable=broad-except
        LogRecord(f"exception in task {task.get_name()} {e} {e.args} {message}",
                  level='error', sources=['asyncio'], exc_info=True)()

class TaskItem:
    """
    Represents an asynchronous task item.

    This class encapsulates a coroutine or callable function and provides methods to create and manage an asyncio task.
    It also handles logging of exceptions that occur during task execution.

    Args:
        func (Awaitable | Callable): The coroutine or callable function to be executed as a task.
        name (str): The name of the task.
        startstring (str, optional): Additional string to include in the log record when the task is created. Defaults to ''.

    Attributes:
        done (bool): Indicates whether the task has completed.
        result: The result of the task, if available.

    Methods:
        create: Creates and starts the asyncio task for the task item.

    Examples:
        task = TaskItem(my_coroutine, 'my_task')
        task.create()
    """

    def __init__(self, func: Awaitable | Callable, name: str, startstring='') -> None:
        """
        Initialize a TaskItem object.

        This constructor sets the attributes of the TaskItem instance based on the provided arguments.
        It also checks if the provided function is a coroutine or callable, and assigns the appropriate coroutine.

        Args:
            func (Awaitable | Callable): The coroutine or callable function to be executed as a task.
            name (str): The name of the task.
            startstring (str, optional): Additional string to include in the log record when the task is created. Defaults to ''.

        Returns:
            None
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
            LogRecord(f"(Task) {self.name} : {func} is not a coroutine or callable", level='error', sources=[__name__])()

    @property
    def done(self):
        """
        Check if the task is done.

        This property returns True if the task has completed, and False otherwise.

        Returns:
            bool: True if the task is done, False otherwise.
        """
        return self.task.done() if self.task else False

    @property
    def result(self):
        """
        Get the result of the task.

        This property returns the result of the task if it has completed, or None if the task is not yet done.

        Returns:
            Any: The result of the task, or None if the task is not done.
        """
        return self.task.result() if self.task else None

    def create(self,
        message: str = '',
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> asyncio.Task:
        '''
        This helper function wraps a ``loop.create_task(coroutine())`` call and ensures there is
        an exception handler added to the resulting task. If the task raises an exception it is logged
        using the provided ``logger``, with additional context provided by ``message``.
        '''
#        self.task = create_task(self.coroutine, message=message, loop=loop, name=self.name)
        LogRecord(f"(Task) (create) {self.name} : {self.startstring}", level='debug', sources=[__name__])()
        if loop is None:
            loop = asyncio.get_running_loop()
        if self.name:
            self.task = loop.create_task(self.coroutine, name=self.name)
        else:
            self.task = loop.create_task(self.coroutine)
        self.task.add_done_callback(
            functools.partial(_handle_task_result, message = message)
        )
        LogRecord(f"(Task) {self.name} : {self.task}", level='debug', sources=[__name__])()
        if self.startstring:
            LogRecord(f"(Task) {self.name} : Created - {self.startstring}", level='debug', sources=[__name__])()
        else:
            LogRecord(f"(Task) {self.name} : Created", level='debug', sources=[__name__])()
        return self.task

class QueueManager:
    """
    Manages the queue of tasks to be executed asynchronously.

    This class provides methods to add tasks to the queue and run them in an asyncio loop.
    It also holds a reference to the asyncio task queue and the BASEAPI instance.

    Attributes:
        task_queue (asyncio.Queue[TaskItem]): The queue of tasks to be executed.
        api (BASEAPI): The BASEAPI instance for API interactions.

    Methods:
        _api_task_add: Add a task to the task queue.
        task_check_for_new_tasks: Wait for new tasks to be added to the task queue and run them.

    Examples:
        queue_manager = QueueManager()
        queue_manager._api_task_add(my_coroutine, 'my_task')
        await queue_manager.task_check_for_new_tasks()
    """
    def __init__(self) -> None:
        """
        Initialize a QueueManager object.

        This constructor initializes the task queue and the BASEAPI instance for managing asynchronous tasks.

        Returns:
            None
        """
        # holds the asyncio tasks to start after plugin initialization
        self.task_queue: asyncio.Queue[TaskItem] = asyncio.Queue()
        self.api = BASEAPI(owner_id=f"{__name__}:QueueManager")
        self.api('libs.api:add')('libs.asynch', 'task.add', self._api_task_add)

    # add a task to the asyncio_tasks queue
    def _api_task_add(self, task: Awaitable | Callable, name: str, startstring='') -> TaskItem:
        """
        Add a task to the task queue.

        This method creates a new TaskItem object with the provided task, name, and startstring.
        The TaskItem is then added to the task queue for execution.

        Args:
            task (Awaitable | Callable): The coroutine or callable function to be executed as a task.
            name (str): The name of the task.
            startstring (str, optional): Additional string to include in the log record when the task is created. Defaults to ''.

        Returns:
            TaskItem: The created TaskItem object.

        Examples:
            queue_manager = QueueManager()
            task = queue_manager._api_task_add(my_coroutine, 'my_task')
        """
        new_task = TaskItem(task, name, startstring)
        self.task_queue.put_nowait(new_task)
        return new_task

    async def task_check_for_new_tasks(self) -> None:
        """
        Wait for new tasks to be added to the task queue and run them.

        This asynchronous function continuously waits for tasks to be added to the task queue.
        Once a task is retrieved, it is created and executed.
        The function also logs the current tasks and sleeps for a short duration before checking for new tasks again.

        Args:
            self: The QueueManager instance.

        Returns:
            None
        """
        while True:
            task: TaskItem = await self.task_queue.get()

            task.create()

            LogRecord(f"Tasks - {asyncio.all_tasks()}", level='debug', sources=[__name__])()

            await asyncio.sleep(.1)

async def shutdown(signal_: signal.Signals, loop_: asyncio.AbstractEventLoop) -> None:
    """
    Handle the shutdown process.

    This asynchronous function is called when a shutdown signal is received.
    It performs the necessary cleanup tasks, cancels outstanding tasks, and stops the event loop.

    Args:
        signal_ (signal.Signals): The shutdown signal received.
        loop_ (asyncio.AbstractEventLoop): The event loop to stop.

    Returns:
        None
    """
    api = BASEAPI(owner_id=f"{__name__}:shutdown")
    LogRecord(f"shutdown - Received exit signal {signal_}:{signal_.name}", level='warning', sources=['mudproxy'])()

    #print(f"{asyncio.current_task():}")
    api('plugins.core.proxy:shutdown')()

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    LogRecord(f"shutdown - Cancelling {len(tasks)} outstanding tasks", level='warning', sources=['mudproxy'])()
    for item in tasks:
        LogRecord(f"shutdown -     {item.get_name()}", level='warning', sources=['mudproxy'])()

    [task.cancel() for task in tasks]

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    if new_exceptions := [
        exc
        for exc in exceptions
        if not isinstance(exc, asyncio.CancelledError)
    ]:
        LogRecord(f"shutdown - Tasks had Exceptions: {new_exceptions}", level='warning', sources=['mudproxy'])()
    else:
        LogRecord(
            "shutdown - All tasks cancelled", level='warning', sources=['mudproxy'])()

    loop_.stop()

def run_asynch() -> None:
    """
    Run the asynchronous event loop.

    This function sets up the event loop, registers signal handlers, and starts the event loop.
    It creates a task to check for new tasks in the task queue and adds signal handlers for shutdown signals.

    Returns:
        None
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    LogRecord('__main__ - setting up signal handlers', level='info', sources=['mudproxy'])()
    #for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
    for sig in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        LogRecord(f"adding signal handler for {sig}:{sig.name}", level='info', sources=[__name__])()
        # ignore RuntimeWarning about coroutine never awaited
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            task_item: TaskItem = TaskItem(func=shutdown(sig, loop), name=f'{sig.name} shutdown handler')
        loop.add_signal_handler(sig, lambda: task_item.create())

    loop.create_task(QUEUEMANAGER.task_check_for_new_tasks(), name='New Task Checker')

    LogRecord('__main__ - run_forever', level='debug', sources=['mudproxy'])()
    loop.run_forever()

QUEUEMANAGER = QueueManager()
