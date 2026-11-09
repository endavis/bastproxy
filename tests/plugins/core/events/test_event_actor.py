"""Tests that an event callback runs under a tracking actor (#43)."""

from pydatatracker.types.actor import current_actor

from bastproxy.libs.callback import Callback
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.events.plugin._event import Event


def test_callback_changes_carry_the_callback_actor() -> None:
    line = NetworkDataLine("a")
    seen: list[str | None] = []

    def callback() -> None:
        seen.append(current_actor.get())
        line.line = "changed"

    event = Event("ev_test43_actor", created_by="test43")
    event.priority_dictionary[50] = {Callback("cb", "plugins.test43", callback): False}
    event.raise_priority(50, False)
    assert seen == ["plugins.test43:cb"]
    assert line.tracking_changes()[-1].actor == "plugins.test43:cb"
    assert current_actor.get() is None
