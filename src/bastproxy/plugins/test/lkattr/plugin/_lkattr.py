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
from libs.records import NetworkDataLine, NetworkData, ProcessDataToMud

class lkAttrPlugin(BasePlugin):
    """
    a plugin to inspect records
    """
    @AddParser(description='test changing a locked attribute')
    def _command_locktest(self):
        """
        List records of a specific type
        """
        testdata = NetworkData('original line')

        testdata[0].lock()
        testdata[0].line = 'changed line'
        testdata.lock()
        testdata.append('appended line')
        testdata.extend(['list line 1', 'list line 2'])
        testdata.insert(1, 'inserted line at index 1')
        testdata[0] = 'straight assignment to index 0'

        tmsg = ["Created:",
                testdata.one_line_summary()]
        return True, tmsg

    @AddParser(description='test splitting a command')
    def _command_splittest(self):
        """
        List records of a specific type
        """
        testdata = NetworkData('command 1|command 2|command 3|command 4|command 5')
        testdata2 = NetworkData('command 1|command 2|command 3|command 4|command 5')

        pd1 = ProcessDataToMud(testdata)
        pd2 = ProcessDataToMud(testdata2)

        pd2.seperate_commands()

        tmsg = [f"pd1: {pd1.uuid}",
                *[line.line for line in pd1.message],
                f"pd2: {pd2.uuid}",
                *[line.line for line in pd2.message]
                ]

        return True, tmsg