# Project: bastproxy
# Filename: plugins/core/commands/_utils.py
#
# File Description: holds command utilities
#
# By: Bast
"""This plugin hold command utilities.

see info/add_commands.txt for more info
"""
# Standard Library

# 3rd Party

# Project

CANRELOAD = False

commands_at_startup = {}


def set_command_autoadd(func, autoadd):
    if not hasattr(func, "command_data"):
        func.command_data = CommandFuncData()
    func.command_data.command["autoadd"] = autoadd


class CommandFuncData:
    def __init__(self):
        self.command = {"autoadd": True, "kwargs": {}}
        self.argparse = {"kwargs": {"add_help": False}, "args": []}
        self.arguments = []


class AddCommand:
    """a class to decorate a function with command data."""

    def __init__(self, *args, **kwargs):
        self.name = None
        if "name" in kwargs:
            self.name = kwargs["name"]
            del kwargs["name"]
        self.autoadd = True
        if "autoadd" in kwargs:
            self.autoadd = kwargs["autoadd"]
            del kwargs["autoadd"]
        self.command_kwargs = kwargs

    def __call__(self, func):
        if not hasattr(func, "command_data"):
            func.command_data = CommandFuncData()
        func.command_data.command["kwargs"].update(self.command_kwargs)
        if "name" not in func.command_data.command:
            func.command_data.command["name"] = self.name or func.__name__.replace("_command_", " ")
        func.command_data.command["autoadd"] = self.autoadd

        return func


class AddParser:
    """a class to decorate a function with argparse data."""

    def __init__(self, *args, **kwargs):
        self.argparse_args = args
        self.argparse_kwargs = kwargs

    def __call__(self, func):
        if not hasattr(func, "command_data"):
            func.command_data = CommandFuncData()
        func.command_data.argparse["args"] = self.argparse_args
        func.command_data.argparse["kwargs"].update(self.argparse_kwargs)

        return func


class AddArgument:
    """a class to decorate a function with argument data."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, func):
        if not hasattr(func, "command_data"):
            func.command_data = CommandFuncData()

        # insert at 0 because decorators are applied in bottom->top order,
        # so the last decorator applied will be the first
        # make it so the order can be exactly like using an argparse object
        func.command_data.arguments.insert(0, {"args": self.args, "kwargs": self.kwargs})

        return func
