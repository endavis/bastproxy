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

from libs.api import API as BASEAPI
from libs.records import LogRecord
from .task_logger import create_task

API = BASEAPI(parent_id=__name__)

# holds the asyncio tasks to start after plugin initialization
TASK_QUEUE = asyncio.Queue()


class TaskItem:
    """
    a class to hold the task to be added to the event loop
    """
    def __init__(self, task, name):
        self.task = task
        self.name = name

    def start(self):
        if asyncio.iscoroutine(self.task):
            create_task(self.task, name=self.name)
        else:
            create_task(self.task(), name=self.name)
        LogRecord(f"TaskItem - Created task {self.name}", level='debug', sources=[__name__]).send()

# add a task to the asyncio_tasks queue
def add_task(task, name):
    """
    add a task to the asyncio_tasks queue
    """
    TASK_QUEUE.put_nowait(TaskItem(task, name))

API('libs.api:add')('libs.asynch', 'task:add', add_task)

async def check_for_new_tasks():
    """
    wait for new tasks to be added to the asyncio_tasks queue and then run them
    """
    while True:
        task = await TASK_QUEUE.get()

        task.start()

        LogRecord(f"Tasks - {asyncio.all_tasks()}", level='debug', sources=[__name__]).send()

        await asyncio.sleep(.1)

async def shutdown(signal_, loop_) -> None:
    """
        shutdown coroutine utilized for cleanup on receipt of certain signals.
        Created and added as a handler to the loop in main.
    """
    LogRecord(f"shutdown - Received exit signal {signal_.name}", level='warning', sources=['mudproxy']).send()

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    LogRecord(f"shutdown - Cancelling {len(tasks)} outstanding tasks", level='warning', sources=['mudproxy']).send()

    for task in tasks:
        task.cancel()

    exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    LogRecord(f"shutdown - Exceptions: {exceptions}", level='warning', sources=['mudproxy']).send()
    loop_.stop()


def handle_exceptions(loop_, context) -> None:
    """
        We attach this as the exception handler to the event loop.  Currently we just
        log, as warnings, any exceptions caught.
    """
    msg = context.get('exception', context['message'])
    LogRecord(f"handle_exceptions - Caught exception: {msg} in loop: {loop_}", level='warning', sources=['mudproxy']).send()
    LogRecord(f"handle_exceptions - Caught in task: {asyncio.current_task()}", level='warning', sources=['mudproxy']).send()

def run_asynch():

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    LogRecord('__main__ - setting up signal handlers', level='debug', sources=['mudproxy']).send()
    for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig, lambda: create_task(shutdown(sig, loop), name='shutdown'))

    #loop.set_exception_handler(handle_exceptions)
    loop.create_task(check_for_new_tasks(), name='New Task Checker')

    LogRecord('__main__ - run_forever', level='debug', sources=['mudproxy']).send()
    loop.run_forever()