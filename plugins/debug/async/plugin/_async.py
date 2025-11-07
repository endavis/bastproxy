# Project: bastproxy
# Filename: plugins/core/async/_async.py
#
# File Description: a plugin to inspect async internals
#
# By: Bast

# Standard Library
import asyncio

# 3rd Party
# Project
from plugins._baseplugin import BasePlugin
from plugins.core.commands import AddParser


class AsyncPlugin(BasePlugin):
    """
    a plugin to inspect records
    """
    @AddParser(description='get a list of asyncio tasks')
    def _command_tasks(self):
        """
        List records of a specific type
        """
        line_length = self.api('plugins.core.commands:get.output.line.length')()
        header_color = self.api('plugins.core.settings:get')('plugins.core.commands', 'output_header_color')

        tasks = asyncio.all_tasks()
        tmsg = [f"Tasks: {len(tasks)}", header_color + line_length * '-' + '@w']
        for task in tasks:
            tmsg.extend(
                (
                    f"    {task.get_name():<30}:",
                    f"        {'State':<20} : {task._state}",
                    f"        {'Coro':<20} : {task.get_coro().__qualname__}",
                    f"        {'Stack':<20} : {task.get_stack()}"
                )
            )
        return True, tmsg
