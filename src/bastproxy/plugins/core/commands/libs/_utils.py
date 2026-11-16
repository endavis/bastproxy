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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

# 3rd Party

# Project

CANRELOAD = False


@dataclass(slots=True)
class CommandResult:
    """What a command function (``_command_*``) returns.

    Attributes:
        success: True if the command worked. False makes the dispatcher append the
            command's help to the output.
        message: output lines shown to the user. A single str is treated as one line.
    """

    success: bool
    message: list[str] | str = field(default_factory=list)


class CommandFuncData:
    def __init__(self) -> None:
        self.command: dict[str, Any] = {"autoadd": True, "kwargs": {}}
        self.argparse: dict[str, Any] = {"kwargs": {"add_help": False}}
        self.arguments: list[dict[str, Any]] = []


class _CommandFunc(Protocol):
    """A callable that carries the ``command_data`` attribute set by the decorators."""

    command_data: CommandFuncData

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


def set_command_autoadd(func: Callable[..., Any], autoadd: bool) -> None:
    target = cast(_CommandFunc, func)
    if not hasattr(func, "command_data"):
        target.command_data = CommandFuncData()
    target.command_data.command["autoadd"] = autoadd


class AddCommand:
    """a class to decorate a function with command data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.name = None
        if "name" in kwargs:
            self.name = kwargs["name"]
            del kwargs["name"]
        self.autoadd = True
        if "autoadd" in kwargs:
            self.autoadd = kwargs["autoadd"]
            del kwargs["autoadd"]
        self.command_kwargs = kwargs

    def __call__(self, func: Callable[..., Any]) -> Any:
        target = cast(_CommandFunc, func)
        if not hasattr(func, "command_data"):
            target.command_data = CommandFuncData()
        target.command_data.command["kwargs"].update(self.command_kwargs)
        if "name" not in target.command_data.command:
            default_name = func.__name__.replace("_command_", " ")
            target.command_data.command["name"] = self.name or default_name
        target.command_data.command["autoadd"] = self.autoadd

        return func


class AddParser:
    """a class to decorate a function with argparse data.

    Only keyword arguments are accepted; they are passed to ``ArgumentParser``.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.argparse_kwargs = kwargs

    def __call__(self, func: Callable[..., Any]) -> Any:
        target = cast(_CommandFunc, func)
        if not hasattr(func, "command_data"):
            target.command_data = CommandFuncData()
        target.command_data.argparse["kwargs"].update(self.argparse_kwargs)

        return func


class AddArgument:
    """a class to decorate a function with argument data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def __call__(self, func: Callable[..., Any]) -> Any:
        target = cast(_CommandFunc, func)
        if not hasattr(func, "command_data"):
            target.command_data = CommandFuncData()

        # insert at 0 because decorators are applied in bottom->top order,
        # so the last decorator applied will be the first
        # make it so the order can be exactly like using an argparse object
        target.command_data.arguments.insert(0, {"args": self.args, "kwargs": self.kwargs})

        return func
