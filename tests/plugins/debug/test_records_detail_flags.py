"""The records.detail hide flags are described accurately (#687)."""

import argparse
from typing import Any

import pytest

from bastproxy.plugins.debug.records.plugin._records import RecordPlugin

FLAGS = [
    ("-sd", "--show_data", "show_data"),
    ("-ss", "--show_stack", "show_stack"),
    ("-iu", "--include_updates", "include_updates"),
]
DESTS = [f[2] for f in FLAGS]


def _arguments() -> list[dict[str, Any]]:
    return list(RecordPlugin._command_detail.command_data.arguments)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    for arg in _arguments():
        parser.add_argument(*arg["args"], **arg["kwargs"])
    return parser


def test_defaults_all_true() -> None:
    ns = _parser().parse_args([])
    assert all(getattr(ns, d) is True for d in DESTS)


@pytest.mark.parametrize("flag", [f for short, long, _ in FLAGS for f in (short, long)])
def test_flag_sets_only_its_dest_false(flag: str) -> None:
    dest = next(d for short, long, d in FLAGS if flag in (short, long))
    ns = _parser().parse_args([flag])
    for d in DESTS:
        assert getattr(ns, d) is (d != dest)


@pytest.mark.parametrize("long", [f[1] for f in FLAGS])
def test_help_describes_hiding(long: str) -> None:
    arg = next(a for a in _arguments() if long in a["args"])
    help_text = arg["kwargs"]["help"]
    assert help_text.startswith(("hide", "leave"))
    assert not help_text.startswith(("show", "include"))
