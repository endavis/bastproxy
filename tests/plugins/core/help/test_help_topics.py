"""Tests for the help plugin's topics and topic command (#420)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.help.plugin._help import HelpPlugin
from bastproxy.plugins.core.help.plugin._topics import (
    TOPICS,
    find_topic,
    render_topic,
)

PREFIX = "!!"


def _stub(name: str = "") -> MagicMock:
    stub = MagicMock()

    def api(api_name: str) -> Any:
        if api_name == "plugins.core.commands:output.header.format":
            return lambda title: [f"== {title} =="]
        if api_name == "plugins.core.commands:command.current.args.get":
            return lambda: {"name": name}
        if api_name == "plugins.core.commands:command.prefix.get":
            return lambda: PREFIX
        return MagicMock()

    stub.api.side_effect = api
    stub._topic_list = lambda prefix: HelpPlugin._topic_list(stub, prefix)
    return stub


def test_topic_names() -> None:
    names = [topic.name for topic in TOPICS]
    assert names == ["connecting", "commands", "settings", "plugins", "core", "status"]
    assert len(set(names)) == len(names)
    for topic in TOPICS:
        assert topic.name == topic.name.lower()
        assert topic.summary
        assert topic.lines


def test_find_topic_exact_case_and_prefix() -> None:
    assert find_topic("settings") is TOPICS[2]
    assert find_topic("Connecting") is TOPICS[0]
    assert find_topic("conn") is TOPICS[0]


@pytest.mark.parametrize("name", ["c", "nope", ""])
def test_find_topic_none(name: str) -> None:
    assert find_topic(name) is None


def test_render_replaces_every_prefix() -> None:
    for topic in TOPICS:
        rendered = render_topic(topic, PREFIX)
        assert not any("{prefix}" in line for line in rendered)
    assert any("{prefix}" in line for topic in TOPICS for line in topic.lines)


def test_rendered_content() -> None:
    connecting = "\n".join(render_topic(TOPICS[0], PREFIX))
    assert "!!.core.proxy.set mudhost" in connecting
    assert "!!.core.proxy.connect" in connecting
    commands = "\n".join(render_topic(TOPICS[1], PREFIX))
    assert "\\#bp" in commands
    assert "#BP: " in commands
    assert "!!.core.proxy.help" in "\n".join(render_topic(TOPICS[4], PREFIX))


def test_command_lists_topics() -> None:
    result = HelpPlugin._command_topic(_stub())
    assert result.success is True
    assert result.message[0] == "== Help Topics =="
    for topic in TOPICS:
        assert any(topic.name in line and topic.summary in line for line in result.message)
    assert result.message[-1] == f"Show a topic with {PREFIX}.core.help.topic <name>"


def test_command_shows_topic() -> None:
    result = HelpPlugin._command_topic(_stub("settings"))
    assert result.success is True
    assert result.message == ["== settings ==", *render_topic(TOPICS[2], PREFIX)]


@pytest.mark.parametrize("name", ["nope", "c"])
def test_command_unknown_or_ambiguous(name: str) -> None:
    result = HelpPlugin._command_topic(_stub(name))
    assert result.success is False
    assert result.message[0].startswith("Unknown topic")
    assert any("connecting" in line for line in result.message)
