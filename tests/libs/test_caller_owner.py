"""Tests for libs.api:caller.owner.get skipping API frames (#197)."""

from bastproxy.libs.api import API
from bastproxy.libs.timing import TIMING


class _Caller:
    plugin_id = "plugins.probe.caller"

    def __init__(self) -> None:
        self.api = API(owner_id=self.plugin_id)

    def owner(self, ignore: list[str] | None = None) -> str:
        return str(self.api("libs.api:caller.owner.get")(ignore_owner_list=ignore))

    def start_timer(self) -> str:
        return str(self.api("libs.timing:timing.start")("t"))


class _OwnerIdCaller:
    owner_id = "plugins.probe.ownerid"

    def __init__(self) -> None:
        self.api = API(owner_id="plugins.probe.apiowner")

    def owner(self) -> str:
        return str(self.api("libs.api:caller.owner.get")())


def test_timing_start_records_real_caller() -> None:
    uid = _Caller().start_timer()
    try:
        assert TIMING.timing[uid].owner_id == "plugins.probe.caller"
    finally:
        TIMING.timing.pop(uid, None)


def test_caller_owner_get_without_ignore_list() -> None:
    assert _Caller().owner() == "plugins.probe.caller"


def test_caller_owner_get_prefers_object_owner_id() -> None:
    assert _OwnerIdCaller().owner() == "plugins.probe.ownerid"


def test_caller_owner_get_with_ignore_list() -> None:
    class Outer:
        owner_id = "plugins.probe.outer"

        def run(self) -> str:
            return _Caller().owner(["plugins.probe.caller"])

    assert Outer().run() == "plugins.probe.outer"
