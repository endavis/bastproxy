"""Tests for the room and area data providers of the mapper (#871)."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from bastproxy.plugins.client.mapper.plugin._mapper import MapperPlugin
from bastproxy.plugins.core.web.libs._store import RouteTable

from .conftest import OWNER, Harness


@dataclass
class Providers:
    """The providers the plugin registered and the raises it made."""

    harness: Harness
    routes: RouteTable
    raised: list[str] = field(default_factory=list)

    def snapshot(self, name: str) -> Any:
        route = self.routes.provider(OWNER, name)
        assert route is not None
        assert route.provider is not None
        snapshot: Any = route.provider.snapshot
        return snapshot()

    def take(self) -> list[str]:
        """Return the names raised since the last call and forget them."""
        taken, self.raised = self.raised, []
        return taken


@pytest.fixture
def providers(harness: Harness) -> Providers:
    plugin = harness.plugin
    routes = RouteTable()
    state = Providers(harness, routes)

    def add_route(
        owner: str, subpath: str, handler: Any, title: str, columns: Any, **kw: Any
    ) -> Any:
        return routes.add(owner, subpath, handler, title, columns, **kw)

    def add_provider(owner: str, name: str, snapshot: Any) -> Any:
        return routes.add_provider(owner, name, snapshot, None, "json", None, lambda s: s)

    def changed(owner: str, name: str) -> bool:
        assert owner == OWNER
        state.raised.append(name)
        return True

    plugin.api.table["plugins.core.web:web.route.add"] = add_route
    plugin.api.table["plugins.core.web:web.provider.add"] = add_provider
    plugin.api.table["plugins.core.web:web.provider.changed.raise"] = changed
    MapperPlugin._phook_add_web_routes(plugin)
    MapperPlugin._phook_add_web_providers(plugin)
    return state


def seed(plugin: Any) -> None:
    plugin._api_area_add("ar", "Area One")
    plugin._api_area_add("br", "Area Two")
    plugin._api_room_add(
        {"uid": "1", "name": "Hall", "area": "ar", "terrain": "road", "x": 1, "y": 2, "z": 3}
    )
    plugin._api_room_add({"uid": "2", "name": "Cellar", "area": "ar"})
    plugin._api_room_add({"uid": "3", "name": "Far", "area": "br"})
    plugin._api_exit_add("1", "e", "2")
    plugin._api_exit_add("1", "n", "-1")
    plugin._api_room_flag_add("1", "safe")


def test_both_providers_are_json_and_owned_by_the_plugin(providers: Providers) -> None:
    for name in ("room", "area"):
        route = providers.routes.provider(OWNER, name)
        assert route is not None
        assert route.provider is not None
        assert route.provider.kind == "json"
        assert route.provider.topic == f"client.mapper.{name}"
    assert providers.harness.plugin.web_providers == {"room", "area"}


def test_a_refused_provider_is_never_raised(harness: Harness) -> None:
    plugin = harness.plugin
    raised: list[str] = []
    plugin.api.table["plugins.core.web:web.route.add"] = lambda *_a, **_k: None
    plugin.api.table["plugins.core.web:web.provider.add"] = lambda *_a, **_k: None

    def changed(_owner: str, name: str) -> bool:
        raised.append(name)
        return True

    plugin.api.table["plugins.core.web:web.provider.changed.raise"] = changed
    MapperPlugin._phook_add_web_providers(plugin)
    seed(plugin)
    plugin._api_room_current_set("1")
    assert plugin.web_providers == set()
    assert raised == []


def test_room_is_null_without_a_current_room_or_a_stored_one(providers: Providers) -> None:
    plugin = providers.harness.plugin
    assert providers.snapshot("room") is None
    plugin._api_room_current_set("nope")
    assert providers.snapshot("room") is None
    assert providers.snapshot("area") is None


def test_room_snapshot(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_marker_register("game", lambda r: ["M" + r["uid"]])
    plugin._api_room_current_set("1")
    assert providers.snapshot("room") == {
        "uid": "1",
        "name": "Hall",
        "area": "ar",
        "terrain": "road",
        "x": 1,
        "y": 2,
        "z": 3,
        "flags": ["safe"],
        "markers": ["M1"],
        "exits": [
            {"dir": "e", "touid": "2", "unexplored": False},
            {"dir": "n", "touid": "-1", "unexplored": True},
        ],
    }


def test_a_raising_marker_callback_gives_no_markers(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_marker_register("game", lambda r: 1 / 0)
    plugin._api_room_current_set("1")
    assert providers.snapshot("room")["markers"] == []


def test_area_snapshot_and_url_without_room(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    assert providers.snapshot("area") == {
        "uid": "ar",
        "name": "Area One",
        "url": "/client/mapper/area?uid=ar",
    }


def test_area_is_null_for_a_room_without_an_area(providers: Providers) -> None:
    plugin = providers.harness.plugin
    plugin._api_room_add({"uid": "9", "name": "Void"})
    plugin._api_room_current_set("9")
    assert providers.snapshot("area") is None
    assert providers.snapshot("room")["uid"] == "9"


def test_the_url_quotes_the_area_uid(providers: Providers) -> None:
    plugin = providers.harness.plugin
    plugin._api_room_add({"uid": "9", "name": "Odd", "area": "a b&c"})
    plugin._api_room_current_set("9")
    assert providers.snapshot("area")["url"] == "/client/mapper/area?uid=a%20b%26c"


def test_a_move_in_the_same_area_raises_room_only(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_room_current_set("2")
    assert providers.take() == ["room"]


def test_a_move_to_another_area_raises_both(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_room_current_set("3")
    assert providers.take() == ["room", "area"]


def test_the_same_room_again_raises_room_only(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_room_current_set("1")
    assert providers.take() == ["room"]


def test_set_then_add_on_an_unstored_room(providers: Providers) -> None:
    plugin = providers.harness.plugin
    plugin._api_room_current_set("5")
    assert providers.take() == ["room"]
    plugin._api_room_add({"uid": "5", "name": "New", "area": "ar"})
    assert providers.take() == ["room", "area"]
    assert providers.snapshot("room")["name"] == "New"


def test_writes_to_other_rooms_raise_nothing(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_room_add({"uid": "2", "name": "Renamed", "area": "ar"})
    plugin._api_room_flag_add("2", "x")
    plugin._api_exit_add("2", "w", "1")
    plugin._api_exit_remove("2", "w")
    plugin._api_room_remove("3")
    assert providers.take() == []


def test_writes_to_the_current_room_raise_room(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_room_flag_add("1", "x")
    assert providers.take() == ["room"]
    plugin._api_room_flag_remove("1", "x")
    assert providers.take() == ["room"]
    plugin._api_exit_add("1", "s", "3")
    assert providers.take() == ["room"]
    plugin._api_exit_remove("1", "s")
    assert providers.take() == ["room"]


def test_removing_the_current_room_raises_room_and_area(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_room_remove("1")
    assert providers.take() == ["room", "area"]
    assert providers.snapshot("room") is None


def test_renaming_the_current_area_raises_area_only(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_area_add("br", "Other name")
    assert providers.take() == []
    plugin._api_area_add("ar", "Renamed")
    assert providers.take() == ["area"]
    assert providers.snapshot("area")["name"] == "Renamed"


def test_removing_the_current_area_raises_both(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_area_remove("ar")
    assert providers.take() == ["room", "area"]


def test_a_batch_that_changes_the_map_raises_room(providers: Providers) -> None:
    plugin = providers.harness.plugin
    seed(plugin)
    plugin._api_room_current_set("1")
    providers.take()
    plugin._api_map_batch_add(rooms=[{"uid": "1", "name": "Hall 2", "area": "ar"}])
    assert "room" in providers.take()
    assert providers.snapshot("room")["name"] == "Hall 2"
