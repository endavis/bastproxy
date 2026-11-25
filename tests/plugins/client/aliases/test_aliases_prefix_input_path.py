# Project: bastproxy
# Filename: tests/plugins/client/aliases/test_aliases_prefix_input_path.py
#
# File Description: Input-path test for alias prefix matching
#
# By: Bast
"""Input-path test for the alias prefix match (#773)."""

from pathlib import Path

import pytest

from .conftest import StandIns
from .test_aliases_input_path import _type, _wire


@pytest.mark.usefixtures("split_regex")
def test_prefix_alias_dispatches_the_subcommand(plugin_stand_ins: StandIns, tmp_path: Path) -> None:
    """`map.find orc` runs `#bp.client.mapper.find orc` and sends nothing to the MUD."""
    wired = _wire(plugin_stand_ins, tmp_path)
    wired.aliases._api_alias_add("map", "#bp.client.mapper")
    _type("map.find orc")
    assert wired.dispatched == ["#bp.client.mapper.find orc"]
    assert wired.sent == []
    assert wired.history == ["map.find orc"]
