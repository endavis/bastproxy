"""Tests for BasePlugin re-registering on the mud disconnect event (#559)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins._baseplugin import BasePlugin

ACTIVE_EVENT = "ev_libs.api_character_active"


class _Stub(BasePlugin):
    """A BasePlugin that skips __init__ and records event registrations."""

    def __init__(self, prio: int | None) -> None:
        self.plugin_id = "plugins.test.stub"
        self.is_character_active_priority = prio  # type: ignore[assignment]
        self.registered: list[tuple[str, Any, int | None]] = []

        def register(name: str, func: Any, prio: int | None = None, **_k: Any) -> None:
            self.registered.append((name, func, prio))

        self.api = MagicMock(
            side_effect=lambda name: (
                register if name == "plugins.core.events:event.register" else MagicMock()
            )
        )


@pytest.mark.parametrize("prio", [None, 10])
def test_disconnect_reregisters_with_the_plugins_priority(prio: int | None) -> None:
    stub = _Stub(prio)

    stub._eventcb_baseplugin_disconnect()

    assert stub.registered == [
        (ACTIVE_EVENT, stub._eventcb_baseplugin_after_character_is_active, prio)
    ]
