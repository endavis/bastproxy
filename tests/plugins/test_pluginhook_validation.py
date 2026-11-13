"""RegisterPluginHook and _process_plugin_hook reject unknown hook names (#446)."""

import re
from pathlib import Path

import pytest

from bastproxy.plugins._baseplugin import RegisterPluginHook
from bastproxy.plugins._baseplugin._base import Plugin
from bastproxy.plugins._baseplugin.libs._pluginhooks import (
    VALID_HOOK_NAMES,
    validate_hook_name,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "bastproxy"


def test_valid_hook_names_contents() -> None:
    assert VALID_HOOK_NAMES == ("__init__", "after_load", "save", "uninitialize")


@pytest.mark.parametrize("name", VALID_HOOK_NAMES)
def test_valid_names_register(name: str) -> None:
    @RegisterPluginHook(name, priority=7)
    def func() -> None:
        pass

    assert func.plugin_hooks == {name: 7}


def test_unknown_name_raises_naming_valid_hooks() -> None:
    with pytest.raises(ValueError, match="nope") as exc:
        RegisterPluginHook("nope")
    for name in VALID_HOOK_NAMES:
        assert name in str(exc.value)


def test_initialize_raises_mentioning_after_load() -> None:
    with pytest.raises(ValueError, match="renamed to 'after_load'"):
        RegisterPluginHook("initialize")


def test_validate_hook_name_accepts_valid_and_rejects_other() -> None:
    for name in VALID_HOOK_NAMES:
        validate_hook_name(name)
    with pytest.raises(ValueError, match="bogus"):
        validate_hook_name("bogus")


class _Stub(Plugin):
    def __init__(self) -> None:
        self.plugin_id = "plugins.test.hook_validation_stub"


def test_process_plugin_hook_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="nope"):
        _Stub()._process_plugin_hook("nope")


def test_src_only_registers_valid_hook_names() -> None:
    pattern = re.compile(r"^\s*@RegisterPluginHook\(\s*[\"']([^\"']+)[\"']", re.MULTILINE)
    used = {
        (str(path.relative_to(SRC)), name)
        for path in SRC.rglob("*.py")
        for name in pattern.findall(path.read_text(encoding="utf-8"))
    }
    assert used, "scan found no RegisterPluginHook uses"
    assert [u for u in used if u[1] not in VALID_HOOK_NAMES] == []
