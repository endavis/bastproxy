"""Regression tests for #257: trigger.register forwards keyword args to event.register."""

# Standard Library
from types import SimpleNamespace
from typing import Any

# Project
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin


def _run(**kwargs: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def register_stub(*args: Any, **kw: Any) -> bool:
        calls.append((args, kw))
        return True

    def api(name: str) -> Any:
        assert name == "plugins.core.events:event.register"
        return register_stub

    fake_self = SimpleNamespace(
        triggers={"t_owner_trig": SimpleNamespace(event_name="ev_t_owner_trig")},
        api=api,
    )

    def callback() -> None:
        return None

    register: Any = TriggersPlugin._api_trigger_register
    register(fake_self, "t_owner_trig", callback, **kwargs)
    assert len(calls) == 1
    args, kw = calls[0]
    assert args == ("ev_t_owner_trig", callback)
    return args, kw


def test_prio_reaches_event_register_as_keyword() -> None:
    _, kw = _run(prio=40)
    assert kw == {"prio": 40}


def test_no_kwargs_forwards_nothing_extra() -> None:
    _, kw = _run()
    assert kw == {}
