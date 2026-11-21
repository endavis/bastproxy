"""The resource command must not depend on os.getloadavg (#691)."""

import os
from typing import Any
from unittest.mock import MagicMock

import psutil
import pytest

from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin


def test_resource_uses_psutil_loadavg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(os, "getloadavg", raising=False)
    monkeypatch.setattr(psutil, "getloadavg", lambda: (1.25, 2.5, 3.75))
    values = {"networkinterfaces": True, "openfiles": True, "ports": True}
    stub = MagicMock()

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: values
        if name == "plugins.core.commands:output.header.format":
            return lambda title: [f"== {title} =="]
        if name == "plugins.core.utils:table.format":
            return lambda title, *_a, **_k: [f"TABLE {title}"]
        return MagicMock()

    stub.api.side_effect = api
    result = ProxyPlugin._command_resource(stub)
    assert result.success is True
    text = "\n".join(result.message)
    assert "1.25" in text
    assert "2.5" in text
    assert "3.75" in text
