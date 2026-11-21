# Project: bastproxy
# Filename: plugins/core/async/_async.py
#
# File Description: a plugin to inspect async internals
#
# By: Bast

# Standard Library
import asyncio
from typing import Any, cast

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddParser, CommandResult


def _task_state(task: "asyncio.Task[Any]") -> str:
    """Return the public state of a task: cancelled, done or pending."""
    if task.cancelled():
        return "cancelled"
    if task.done():
        return "done"
    return "pending"


def _format_stack(task: "asyncio.Task[Any]") -> list[str]:
    """Return one line per stack frame of a task."""
    return [
        f"            {frame.f_code.co_filename}:{frame.f_lineno} {frame.f_code.co_name}"
        for frame in task.get_stack()
    ]


class AsyncPlugin(BasePlugin):
    """a plugin to inspect records."""

    @AddParser(description="get a list of asyncio tasks")
    def _command_tasks(self) -> CommandResult:
        """List records of a specific type."""
        line_length = self.api("plugins.core.commands:output.line.length.get")()
        header_color = self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_header_color"
        )

        tasks = asyncio.all_tasks()
        tmsg = [f"Tasks: {len(tasks)}", header_color + line_length * "-" + "@w"]
        for task in tasks:
            tmsg.extend(
                (
                    f"    {task.get_name():<30}:",
                    f"        {'State':<20} : {_task_state(task)}",
                    f"        {'Coro':<20} : {cast(Any, task.get_coro()).__qualname__}",
                )
            )
            if frames := _format_stack(task):
                tmsg.append(f"        {'Stack':<20} :")
                tmsg.extend(frames)
            else:
                tmsg.append(f"        {'Stack':<20} : none")
        return CommandResult(True, tmsg)
