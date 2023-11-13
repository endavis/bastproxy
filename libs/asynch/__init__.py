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
    a class to hold the task to be added to the event loop
    """
    def __init__(self, func: Awaitable | Callable, name: str, startstring='') -> None:
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
        return self.task.done() if self.task else False

    @property
    def result(self):
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
            LogRecord(f"(Task) {self.name} : Created - {self.startstring}", level='info', sources=[__name__])()
        else:
            LogRecord(f"(Task) {self.name} : Created", level='info', sources=[__name__])()
        return self.task

class QueueManager:
    def __init__(self) -> None:
        # holds the asyncio tasks to start after plugin initialization
        self.task_queue: asyncio.Queue[TaskItem] = asyncio.Queue()
        self.api = BASEAPI(owner_id=f"{__name__}:QueueManager")
        self.api('libs.api:add')('libs.asynch', 'task.add', self._api_task_add)

    # add a task to the asyncio_tasks queue
    def _api_task_add(self, task: Awaitable | Callable, name: str, startstring='') -> TaskItem:
        """
        add a task to the asyncio_tasks queue
        """
        new_task = TaskItem(task, name, startstring)
        self.task_queue.put_nowait(new_task)
        return new_task

    async def task_check_for_new_tasks(self) -> None:
        """
        wait for new tasks to be added to the asyncio_tasks queue and then run them
        """
        while True:
            task: TaskItem = await self.task_queue.get()

            task.create()

            LogRecord(f"Tasks - {asyncio.all_tasks()}", level='debug', sources=[__name__])()

            await asyncio.sleep(.1)

async def shutdown(signal_: signal.Signals, loop_: asyncio.AbstractEventLoop) -> None:
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.
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
