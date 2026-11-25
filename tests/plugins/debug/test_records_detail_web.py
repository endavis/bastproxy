"""record detail -w/--web replies with a link (#424)."""

import argparse
from typing import Any

import pytest

from bastproxy.plugins.debug.records.plugin import _records
from bastproxy.plugins.debug.records.plugin._records import RecordPlugin

PAGE_ADD = "plugins.core.web:web.page.add"


class _Record:
    uuid = "u1"

    def get_formatted_details(self, **_kwargs: Any) -> list[str]:
        return ["line one", "line two"]


class _Stub:
    plugin_id = "plugins.debug.records"

    def __init__(self, args: dict[str, Any], url: str, web_loaded: bool = True) -> None:
        self.args = args
        self.url = url
        self.web_loaded = web_loaded
        self.pages: list[tuple[str, str, list[str]]] = []

    def _web_link(self, uid: str, data: list[str]) -> str:
        return RecordPlugin._web_link(self, uid, data)  # type: ignore[arg-type]

    def api(self, name: str) -> Any:
        def call(*args: Any) -> Any:
            if name == "plugins.core.commands:command.current.args.get":
                return self.args
            if name == "libs.api:api.exists":
                return self.web_loaded and args[0] == PAGE_ADD
            if name == PAGE_ADD:
                self.pages.append(args)
                return self.url
            if name == "plugins.core.settings:setting.get":
                return False
            return None

        return call


ARGS = {
    "uid": "r1",
    "update": "",
    "full_children_records": False,
    "include_updates": True,
    "dump": False,
    "web": True,
}


@pytest.fixture(autouse=True)
def _record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_records.RMANAGER, "get_record", lambda _uid: _Record())


def _detail(stub: _Stub) -> list[str]:
    result = RecordPlugin._command_detail(stub)
    return [result.message] if isinstance(result.message, str) else list(result.message)


def test_web_replies_with_the_link_only() -> None:
    stub = _Stub(dict(ARGS), "https://bast.example.net:9998/p/tok")
    assert _detail(stub) == ["Record detail: https://bast.example.net:9998/p/tok"]
    assert stub.pages == [("plugins.debug.records", "Record r1", ["line one", "line two"])]


def test_disabled_server_gives_the_not_enabled_message() -> None:
    message = _detail(_Stub(dict(ARGS), ""))
    assert len(message) == 1
    assert "not enabled" in message[0]


def test_missing_web_plugin_gives_the_not_loaded_message() -> None:
    message = _detail(_Stub(dict(ARGS), "x", web_loaded=False))
    assert message == ["the web plugin is not loaded"]


def test_without_web_the_output_is_shown() -> None:
    stub = _Stub({**ARGS, "web": False}, "x")
    assert _detail(stub) == ["line one", "line two"]
    assert stub.pages == []


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for arg in RecordPlugin._command_detail.command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    return parser


def test_parser_accepts_short_and_long_flags_and_defaults_to_false() -> None:
    assert _parser().parse_args([]).web is False
    assert _parser().parse_args(["-w"]).web is True
    assert _parser().parse_args(["--web"]).web is True
    ns = _parser().parse_args(["-w", "-d"])
    assert ns.web is True
    assert ns.dump is True
