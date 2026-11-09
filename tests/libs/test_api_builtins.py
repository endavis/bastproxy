"""Tests for the lazy libs.api built-ins (issue #199).

Test Classes:
    - `TestBuiltinTable`: the fixed table and construction cost.
    - `TestLazyBinding`: lazy, cached, per-object binding.
    - `TestEnumeration`: listing and existence checks see all built-ins.
    - `TestOverrideAndHide`: overriding, deleting and removing built-ins.

"""

from collections.abc import Iterator

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.api._apiitem import APIItem
from bastproxy.libs.api._apistats import STATS_MANAGER
from bastproxy.libs.api._builtins import BUILTIN_APIS
from bastproxy.libs.api._functools import stackdump
from bastproxy.libs.exceptions import APINotFoundError

STACK_DUMP = "libs.api:stack.dump"


@pytest.fixture(autouse=True)
def _isolate_api_state() -> Iterator[None]:
    """Restore the shared class API registry and stats after every test."""
    class_api_snapshot = dict(API._class_api)
    stats_snapshot = dict(STATS_MANAGER.stats)
    yield
    API._class_api.clear()
    API._class_api.update(class_api_snapshot)
    STATS_MANAGER.stats.clear()
    STATS_MANAGER.stats.update(stats_snapshot)


@pytest.fixture
def api() -> API:
    """Return a fresh API object."""
    return API(owner_id="t199")


def _replacement() -> str:
    """Return a marker string."""
    return "replacement"


class TestBuiltinTable:
    """The fixed table and construction."""

    def test_construction_binds_nothing(self, api: API) -> None:
        """A new object has no stored items."""
        assert api._instance_api._items == {}

    def test_table_size_and_prefix(self) -> None:
        """The table holds the 14 libs.api names."""
        assert len(BUILTIN_APIS) == 14
        assert all(key.startswith("libs.api:") for key in BUILTIN_APIS)


class TestLazyBinding:
    """Built-ins bind on first use and are cached."""

    def test_every_name_resolves(self, api: API) -> None:
        """Each name resolves to an instance APIItem bound to the object."""
        for name in BUILTIN_APIS:
            item = api.get(name)
            assert isinstance(item, APIItem)
            assert item.instance is True
            assert item.owner_id == "t199"
            if name == STACK_DUMP:
                assert item.tfunction is stackdump
            else:
                assert item.tfunction.__self__ is api  # type: ignore[attr-defined]
            assert api(name) is not None

    def test_lazy_and_cached(self, api: API) -> None:
        """Only the resolved name is stored, and the item is reused."""
        name = "libs.api:data.list"
        first = api.get(name)
        assert set(api._instance_api._items) == {name}
        assert api.get(name) is first

    def test_per_object_binding(self) -> None:
        """Two objects get different items bound to themselves."""
        one = API(owner_id="one199")
        two = API(owner_id="two199")
        name = "libs.api:data.list"
        item_one = one.get(name)
        item_two = two.get(name)
        assert item_one is not item_two
        assert item_one.tfunction.__self__ is one  # type: ignore[attr-defined]
        assert item_two.tfunction.__self__ is two  # type: ignore[attr-defined]

    def test_stats_recorded(self, api: API) -> None:
        """Calling a built-in records a stat."""
        api("libs.api:data.list")()
        assert "libs.api:data.list" in STATS_MANAGER.stats


class TestEnumeration:
    """Listing and existence checks."""

    def test_len_and_iter_before_and_after_binding(self, api: API) -> None:
        """Bound and unbound built-ins are both counted."""
        assert len(api._instance_api) == 14
        assert set(api._instance_api) == set(BUILTIN_APIS)
        api.get(STACK_DUMP)
        assert len(api._instance_api) == 14
        assert set(api._instance_api) == set(BUILTIN_APIS)

    def test_listings_include_all(self, api: API) -> None:
        """The list APIs show all 14 names."""
        listed = api("libs.api:api.list.in.toplevel")("libs.api")
        assert len(listed) == 14
        assert set(BUILTIN_APIS) <= set(api.get_full_api_list())
        formatted = "\n".join(api("libs.api:api.list.formatted")("libs.api"))
        assert "stack.dump" in formatted
        assert "api.add" in formatted

    def test_exists(self, api: API) -> None:
        """api.exists sees built-ins and rejects unknown names."""
        api.add("libs.plugins.loader", "plugin.id.is.valid", lambda _pid: False)
        assert api("libs.api:api.exists")("libs.api:data.get")
        assert not api("libs.api:api.exists")("libs.api:nope")
        with pytest.raises(APINotFoundError):
            api.get("libs.api:nope")

    def test_detail(self, api: API) -> None:
        """api.detail.get returns the description."""
        detail = api("libs.api:api.detail.get")("libs.api:api.add")
        assert detail
        assert "add a function to the api" in "\n".join(detail)


class TestOverrideAndHide:
    """Overriding, deleting and removing built-ins."""

    def test_override_with_force(self, api: API) -> None:
        """A forced add replaces the built-in."""
        name = "libs.api:data.list"
        assert api.add("libs.api", "data.list", _replacement, instance=True, force=True)
        assert api.get(name).tfunction is _replacement
        assert api("libs.api:data.list")() == "replacement"

    def test_override_without_force(self, api: API) -> None:
        """A different function without force is refused."""
        assert api.add("libs.api", "data.list", _replacement, instance=True) is False
        assert api.get("libs.api:data.list").tfunction is not _replacement

    def test_delete_hides_for_one_object(self, api: API) -> None:
        """Deleting hides a built-in on that object only."""
        other = API(owner_id="other199")
        del api._instance_api[STACK_DUMP]
        assert STACK_DUMP not in api._instance_api
        assert len(api._instance_api) == 13
        with pytest.raises(APINotFoundError):
            api.get(STACK_DUMP)
        assert STACK_DUMP in other._instance_api
        assert other.get(STACK_DUMP) is not None

    def test_delete_unknown_raises(self, api: API) -> None:
        """Deleting an unknown key raises KeyError."""
        with pytest.raises(KeyError):
            del api._instance_api["libs.api:nope"]

    def test_setitem_unhides(self, api: API) -> None:
        """Setting a deleted name makes it visible again."""
        item = api.get(STACK_DUMP)
        del api._instance_api[STACK_DUMP]
        api._instance_api[STACK_DUMP] = item
        assert STACK_DUMP in api._instance_api
        assert api.get(STACK_DUMP) is item

    def test_toplevel_remove(self, api: API) -> None:
        """Removing the toplevel hides every built-in on this object only."""
        other = API(owner_id="other199")
        api("libs.api:api.toplevel.remove")("libs.api")
        assert len(api._instance_api) == 0
        assert not api.get_top_level_api_list("libs.api")
        assert len(other._instance_api) == 14
