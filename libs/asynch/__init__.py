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
from typing import Callable, Awaitable

from libs.api import API as BASEAPI
from libs.records import LogRecord
from .task_logger import create_task

class TaskItem:
    """
    a class to hold the task to be added to the event loop
    """
    def __init__(self, task: Awaitable | Callable, name: str) -> None:
        self.task = task
        self.name = name

    def start(self) -> None:
        if asyncio.iscoroutine(self.task):
            create_task(self.task, name=self.name)
        elif isinstance(self.task, Callable):
            create_task(self.task(), name=self.name)
        LogRecord(f"TaskItem - Created task {self.name}", level='debug', sources=[__name__])()

class QueueManager:
    def __init__(self) -> None:
        # holds the asyncio tasks to start after plugin initialization
        self.task_queue: asyncio.Queue[TaskItem] = asyncio.Queue()
        self.api = BASEAPI(owner_id=f"{__name__}:QueueManager")
        self.api('libs.api:add')('libs.asynch', 'task.add', self.add_task)

    # add a task to the asyncio_tasks queue
    def add_task(self, task: Awaitable | Callable, name: str) -> None:
        """
        add a task to the asyncio_tasks queue
        """
        self.task_queue.put_nowait(TaskItem(task, name))

    async def task_check_for_new_tasks(self) -> None:
        """
        wait for new tasks to be added to the asyncio_tasks queue and then run them
        """
        while True:
            task: TaskItem = await self.task_queue.get()

            task.start()

            LogRecord(f"Tasks - {asyncio.all_tasks()}", level='debug', sources=[__name__])()

            await asyncio.sleep(.1)

async def shutdown(signal_: signal.Signals, loop_: asyncio.AbstractEventLoop) -> None:
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.
    """
    api = BASEAPI(owner_id=f"{__name__}:shutdown")
    LogRecord(f"shutdown - Received exit signal {signal_.name}", level='warning', sources=['mudproxy'])()

    api('plugins.core.proxy:shutdown')()

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    LogRecord(f"shutdown - Cancelling {len(tasks)} outstanding tasks", level='warning', sources=['mudproxy'])()

    for task in tasks:
        task.cancel()

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    LogRecord(f"shutdown - Exceptions: {exceptions}", level='warning', sources=['mudproxy'])()
    loop_.stop()

def run_asynch() -> None:

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    LogRecord('__main__ - setting up signal handlers', level='debug', sources=['mudproxy'])()
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: create_task(shutdown(sig, loop), name='shutdown'))

    loop.create_task(QUEUEMANAGER.task_check_for_new_tasks(), name='New Task Checker')

    LogRecord('__main__ - run_forever', level='debug', sources=['mudproxy'])()
    loop.run_forever()

QUEUEMANAGER = QueueManager()
