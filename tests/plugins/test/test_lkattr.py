"""Tests that the lkattr locktest reports the refused writes (#43)."""

from bastproxy.plugins.test.lkattr.plugin._lkattr import lkAttrPlugin


def test_locktest_reports_each_refusal() -> None:
    plugin = lkAttrPlugin.__new__(lkAttrPlugin)
    func = lkAttrPlugin._command_locktest
    func = getattr(func, "__wrapped__", func)
    result = func(plugin)
    msg = result.message
    assert result.success
    refused = [line for line in msg if "refused with RuntimeError" in line]
    assert len(refused) == 5
    assert not any("NOT refused" in line for line in msg)
