# Project: bastproxy
# Filename: libs/context.py
#
# File Description: Context variables for the active record, event stack and command args
#
# By: Bast
"""Context variables that say what the proxy is running right now.

Four things used to live in shared mutable state: the record being executed, the events
being raised, the arguments of the command being run and the client its output goes to. Each is
now a context variable that a
context manager sets for the duration of the work and resets with its token, also when the
work raises. Reading one costs a dictionary lookup and needs no API call.

Asyncio copies the current context into every task. ``fresh_context()`` gives a task a context
with the four variables reset, so a task spawned while a record, event or command is running
does not inherit it. See ``docs/claude/record_system.md``.
"""

# Standard Library
import contextvars
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

__all__ = [
    "active_record",
    "active_records",
    "command_args",
    "event_stack",
    "fresh_context",
    "get_command_args",
    "get_output_client",
    "output_client",
    "output_to_client",
    "raised_event",
    "running_command",
]

# The records being executed, outermost first.
active_records: contextvars.ContextVar[tuple[Any, ...]] = contextvars.ContextVar(
    "bastproxy_active_records", default=()
)
# The names of the events being raised, outermost first.
event_stack: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "bastproxy_event_stack", default=()
)
# The arguments of the command being run, or None when no command is running.
command_args: contextvars.ContextVar[Mapping[str, Any] | None] = contextvars.ContextVar(
    "bastproxy_command_args", default=None
)
# The id of the client whose command is running, or None when there is no single target.
output_client: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "bastproxy_output_client", default=None
)


@contextmanager
def active_record(record: Any) -> Iterator[None]:
    """Mark ``record`` as the innermost active record while the block runs."""
    token = active_records.set((*active_records.get(), record))
    try:
        yield
    finally:
        active_records.reset(token)


@contextmanager
def raised_event(name: str) -> Iterator[None]:
    """Push the event ``name`` on the event stack while the block runs."""
    token = event_stack.set((*event_stack.get(), name))
    try:
        yield
    finally:
        event_stack.reset(token)


@contextmanager
def running_command(args: Mapping[str, Any] | None) -> Iterator[None]:
    """Set the current command's arguments while the block runs."""
    token = command_args.set(args)
    try:
        yield
    finally:
        command_args.reset(token)


@contextmanager
def output_to_client(client_id: str | None) -> Iterator[None]:
    """Set the client that output is formatted for while the block runs."""
    token = output_client.set(client_id)
    try:
        yield
    finally:
        output_client.reset(token)


def get_output_client() -> str | None:
    """Return the id of the client the running command's output goes to, or None."""
    return output_client.get()


def get_command_args() -> Mapping[str, Any]:
    """Return the running command's arguments, or an empty mapping when none is running."""
    args = command_args.get()
    return {} if args is None else args


def fresh_context() -> contextvars.Context:
    """Return a copy of the current context with the four variables reset.

    Pass it as ``context=`` when creating a task so the task starts with no active record,
    no event stack and no command args.
    """
    ctx = contextvars.copy_context()
    ctx.run(active_records.set, ())
    ctx.run(event_stack.set, ())
    ctx.run(command_args.set, None)
    ctx.run(output_client.set, None)
    return ctx
