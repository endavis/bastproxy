"""Tests for the API system.

This module tests the API registration and invocation system including:
- Adding APIs to class and instance namespaces
- Retrieving APIs by location
- Checking API existence
- Getting API children
- API overwriting and forcing
- API statistics tracking

Test Classes:
    - `TestAPIBasics`: Tests for basic API operations (add, get, has).
    - `TestAPINamespaces`: Tests for API namespace separation and hierarchy.
    - `TestAPIOverwriting`: Tests for API overwriting and force behavior.

"""

import logging
import sys
from collections.abc import Iterator

import pytest

from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.api._apistats import STATS_MANAGER, APIStatItem
from bastproxy.libs.exceptions import APINotFoundError


@pytest.fixture(autouse=True)
def _isolate_api_state() -> Iterator[None]:
    """Restore the shared class API registry and stats after every test.

    ``API._class_api`` and ``STATS_MANAGER.stats`` are shared state, so the dicts
    are restored in place to keep every existing reference valid.

    """
    class_api_snapshot = dict(API._class_api)
    stats_snapshot = dict(STATS_MANAGER.stats)
    yield
    API._class_api.clear()
    API._class_api.update(class_api_snapshot)
    STATS_MANAGER.stats.clear()
    STATS_MANAGER.stats.update(stats_snapshot)


def helper_function_one() -> str:
    """Helper function one.

    Returns:
        A test string.

    Raises:
        None

    """
    return "function_one"


def helper_function_two() -> str:
    """Helper function two.

    Returns:
        A test string.

    Raises:
        None

    """
    return "function_two"


def helper_function_three() -> str:
    """Helper function three.

    Returns:
        A test string.

    Raises:
        None

    """
    return "function_three"


class TestAPIBasics:
    """Test basic API operations."""

    def test_api_instantiation(self) -> None:
        """Test that API instances can be created with an owner_id."""
        api = API(owner_id="test_owner")
        assert api.owner_id == "test_owner"

    def test_api_add_class_level(self) -> None:
        """Test adding a function to the class-level API."""
        api = API(owner_id="test_owner")
        result = api.add("test", "function", helper_function_one, description="Test")
        assert result is True

        # Check that the API exists
        api_item = api.get("test:function")
        assert api_item is not None
        assert api_item.full_api_name == "test:function"
        assert api_item.owner_id == "test_owner"

    def test_api_add_instance_level(self) -> None:
        """Test adding a function to the instance-level API."""
        api = API(owner_id="test_owner")
        result = api.add("test", "function", helper_function_one, instance=True, description="Test")
        assert result is True

        # Check that the API exists at instance level
        api_item = api.get("test:function")
        assert api_item is not None
        assert api_item.instance is True

    def test_api_get_retrieves_function(self) -> None:
        """Test that get() retrieves the correct APIItem."""
        api = API(owner_id="test_owner")
        api.add("test", "function", helper_function_one, description="Test")

        api_item = api.get("test:function")
        assert api_item.tfunction == helper_function_one

    def test_api_call_alias_for_get(self) -> None:
        """Test that __call__ is an alias for get()."""
        api = API(owner_id="test_owner")
        api.add("test", "function", helper_function_one, description="Test")

        # Use the __call__ interface
        api_item = api("test:function")
        assert api_item.tfunction == helper_function_one

    def test_api_has_existing_api(self) -> None:
        """Test that has() returns True for existing APIs."""
        api = API(owner_id="test_owner")
        api.add("test", "function", helper_function_one, description="Test")

        # The built-in has API requires plugin loader APIs which don't exist
        # in tests, so we test the underlying _api_api_exists method is added
        assert api("libs.api:api.exists") is not None

    def test_api_has_nonexistent_api(self) -> None:
        """Test that has() returns False for nonexistent APIs."""
        api = API(owner_id="test_owner")

        # Use the built-in has API
        has_result = api("libs.api:api.exists")("nonexistent:api")
        assert has_result is False

    def test_api_get_raises_attribute_error(self) -> None:
        """Test that get() raises APINotFoundError (an AttributeError) for nonexistent APIs."""
        api = API(owner_id="test_owner")

        with pytest.raises(APINotFoundError, match="nonexistent:api is not in the api"):
            api.get("nonexistent:api")
        with pytest.raises(AttributeError):
            api.get("nonexistent:api")

    def test_api_has_only_swallows_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that _api_api_exists returns False for not-found but propagates other AttributeErrors."""
        api = API(owner_id="test_owner")

        def raise_not_found(_location: str) -> None:
            msg = "missing"
            raise APINotFoundError(msg)

        def raise_attribute_error(_location: str) -> None:
            msg = "unrelated bug"
            raise AttributeError(msg)

        monkeypatch.setattr(api, "get", raise_not_found)
        assert api._api_api_exists("x:y") is False

        monkeypatch.setattr(api, "get", raise_attribute_error)
        with pytest.raises(AttributeError, match="unrelated bug"):
            api._api_api_exists("x:y")


class TestAPINamespaces:
    """Test API namespace separation and hierarchy."""

    def test_api_namespaces_are_separated(self) -> None:
        """Test that different namespaces keep APIs separate."""
        api = API(owner_id="test_owner")
        api.add("namespace1", "function", helper_function_one, description="Test 1")
        api.add("namespace2", "function", helper_function_two, description="Test 2")

        # Each namespace should have its own function
        api_item1 = api.get("namespace1:function")
        api_item2 = api.get("namespace2:function")

        assert api_item1.tfunction == helper_function_one
        assert api_item2.tfunction == helper_function_two

    def test_api_get_children(self) -> None:
        """Test getting all children of a parent API."""
        api = API(owner_id="test_owner")
        api.add("parent", "child1", helper_function_one, description="Child 1")
        api.add("parent", "child2", helper_function_two, description="Child 2")
        api.add("parent", "child3", helper_function_three, description="Child 3")

        # Get children using the built-in API
        children = api("libs.api:api.list.in.toplevel")("parent")

        assert "child1" in children
        assert "child2" in children
        assert "child3" in children
        assert len(children) == 3

    def test_api_get_children_with_colon(self) -> None:
        """Test getting children works with or without trailing colon."""
        api = API(owner_id="test_owner")
        api.add("parent", "child1", helper_function_one, description="Child 1")

        # Should work with or without trailing colon
        children_with_colon = api("libs.api:api.list.in.toplevel")("parent:")
        children_without_colon = api("libs.api:api.list.in.toplevel")("parent")

        assert children_with_colon == children_without_colon


class TestAPIOverwriting:
    """Test API overwriting and force behavior."""

    def test_api_add_duplicate_without_force_fails(self) -> None:
        """Test that adding duplicate API without force=True logs error and returns False.

        Both class and instance APIs return False for a refused duplicate.

        """
        api = API(owner_id="test_owner")
        result1 = api.add("test", "function", helper_function_one, description="Test 1")
        result2 = api.add("test", "function", helper_function_two, description="Test 2")

        assert result1 is True
        assert result2 is False

        # Original function should still be there
        api_item = api.get("test:function")
        assert api_item.tfunction == helper_function_one

    def test_api_add_duplicate_with_force_succeeds(self) -> None:
        """Test that adding duplicate API with force=True overwrites."""
        api = API(owner_id="test_owner")
        result1 = api.add("test", "function", helper_function_one, description="Test 1")
        result2 = api.add("test", "function", helper_function_two, force=True, description="Test 2")

        assert result1 is True
        assert result2 is True  # Should succeed with force=True

        # New function should replace old one
        api_item = api.get("test:function")
        assert api_item.tfunction == helper_function_two

    def test_api_add_same_function_twice_succeeds(self) -> None:
        """Test that adding the same function twice returns True."""
        api = API(owner_id="test_owner")
        result1 = api.add("test", "function", helper_function_one, description="Test")
        result2 = api.add(
            "test", "function", helper_function_one, description="Test"
        )  # Same function

        assert result1 is True
        assert result2 is True  # Should succeed since it's the same function

    def test_api_overwritten_api_reference(self) -> None:
        """Test that overwritten_api stores reference to original API."""
        api = API(owner_id="test_owner")
        api.add("test", "function", helper_function_one, description="Test 1")
        api.add("test", "function", helper_function_two, force=True, description="Test 2")

        # Check that overwritten_api reference exists
        api_item = api.get("test:function")
        assert api_item.overwritten_api is not None
        assert api_item.overwritten_api.tfunction == helper_function_one

    def test_class_duplicate_keeps_first_function_callable(self) -> None:
        """A refused class duplicate leaves the first function registered and callable."""
        api = API(owner_id="test_owner")
        api.add("t194keep", "function", helper_function_one)
        assert api.add("t194keep", "function", helper_function_two) is False

        assert api("t194keep:function")() == helper_function_one()

    def test_class_same_function_readd_returns_true(self) -> None:
        """Re-adding the identical class function returns True."""
        api = API(owner_id="test_owner")
        api.add("t194same", "function", helper_function_one)
        assert api.add("t194same", "function", helper_function_one) is True

    def test_class_force_returns_true_and_overwrites(self) -> None:
        """Force on a class duplicate returns True and the new function is called."""
        api = API(owner_id="test_owner")
        api.add("t194force", "function", helper_function_one)
        assert api.add("t194force", "function", helper_function_two, force=True) is True

        assert api("t194force:function")() == helper_function_two()

    def test_instance_duplicate_returns_false(self) -> None:
        """A refused instance duplicate returns False."""
        api = API(owner_id="test_owner")
        assert api.add("t194", "function", helper_function_one, instance=True) is True
        assert api.add("t194", "function", helper_function_two, instance=True) is False

    def test_class_duplicate_import_error_fallback_logs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without LogRecord, a refused class duplicate logs via logging, not print."""
        api = API(owner_id="test_owner")
        api.add("t194fallback", "function", helper_function_one)
        monkeypatch.setitem(sys.modules, "bastproxy.libs.records", None)

        with caplog.at_level(logging.ERROR):
            result = api.add("t194fallback", "function", helper_function_two)

        assert result is False
        assert "libs.api:api.add - t194fallback:function already exists" in caplog.text
        assert capsys.readouterr().out == ""

    def test_instance_duplicate_import_error_fallback_logs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without LogRecord, a refused instance duplicate logs via logging, not print."""
        api = API(owner_id="test_owner")
        api.add("t194", "function", helper_function_one, instance=True)
        monkeypatch.setitem(sys.modules, "bastproxy.libs.records", None)

        with caplog.at_level(logging.ERROR):
            result = api.add("t194", "function", helper_function_two, instance=True)

        assert result is False
        assert "libs.api:instance - t194:function already exists" in caplog.text
        assert capsys.readouterr().out == ""

    def test_apistats_unknown_caller_import_error_fallback_logs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without LogRecord, an unknown caller warns via logging, not print."""
        item = APIStatItem("test:function")
        monkeypatch.setitem(sys.modules, "bastproxy.libs.records", None)

        with caplog.at_level(logging.WARNING):
            item.add_call("unknown")

        assert "Unknown caller_id for API call: test:function" in caplog.text
        assert capsys.readouterr().out == ""
        assert item.count == 1
        assert item.detailed_calls == {"unknown": 1}


class TestAPIInstancePriority:
    """Test instance API priority over class API."""

    def test_instance_api_overrides_class_api(self) -> None:
        """Test that instance API takes priority when both exist with same name."""
        api = API(owner_id="test_owner")

        # Use unique namespace to avoid cross-test contamination
        # Add to class API first
        api.add("testprio", "override", helper_function_one, description="Class API")

        # Verify class API was added
        api_item_before = api.get("testprio:override")
        assert api_item_before.tfunction == helper_function_one
        assert api_item_before.instance is False

        # Now add to instance API with SAME name but different function
        # This should create instance-level override
        result = api.add(
            "testprio",
            "override",
            helper_function_two,
            instance=True,
            force=True,
            description="Instance API",
        )

        assert result is True

        # Instance API should now be returned by default get()
        api_item_after = api.get("testprio:override")
        assert api_item_after.tfunction == helper_function_two
        assert api_item_after.instance is True

        # Can still get class API explicitly
        api_item_class = api.get("testprio:override", get_class=True)
        assert api_item_class.tfunction == helper_function_one
        assert api_item_class.instance is False

    def test_instance_and_class_apis_separate(self) -> None:
        """Test that instance and class APIs are kept in separate namespaces."""
        api = API(owner_id="test_owner")

        # Add to class API
        result1 = api.add("testsep", "classapi", helper_function_one, description="Class")

        # Add to instance API with different name
        result2 = api.add(
            "testsep",
            "instanceapi",
            helper_function_two,
            instance=True,
            description="Inst",
        )

        assert result1 is True
        assert result2 is True

        # Both should exist independently
        class_api_item = api.get("testsep:classapi")
        instance_api_item = api.get("testsep:instanceapi")

        assert class_api_item.tfunction == helper_function_one
        assert class_api_item.instance is False

        assert instance_api_item.tfunction == helper_function_two
        assert instance_api_item.instance is True


RENAMED_LIBS_API_NAMES: list[tuple[str, str]] = [
    ("add", "api.add"),
    ("has", "api.exists"),
    ("add.apis.for.object", "api.add.for.object"),
    ("remove", "api.toplevel.remove"),
    ("get.children", "api.list.in.toplevel"),
    ("detail", "api.detail.get"),
    ("list", "api.list.formatted"),
    ("list.data", "data.list"),
    ("get.function.owner.plugin", "function.owner.get"),
    ("get.caller.owner", "caller.owner.get"),
    ("is.character.active", "character.is.active"),
    ("is.character.active:set", "character.active.set"),
    ("stackdump", "stack.dump"),
]


class TestLibsApiRenames:
    """Test the ADR-0004 names of the APIs libs.api registers on itself."""

    @pytest.mark.parametrize(("old", "new"), RENAMED_LIBS_API_NAMES)
    def test_new_name_registered_old_name_gone(self, old: str, new: str) -> None:
        """The new name resolves and the old name does not."""
        api = API(owner_id="test_owner")

        assert api.get(f"libs.api:{new}") is not None
        with pytest.raises(APINotFoundError):
            api.get(f"libs.api:{old}")

    def test_character_active_round_trip(self) -> None:
        """character.active.set is read back by character.is.active."""
        api = API(owner_id="test_owner")
        raised: list[str] = []

        def fake_event_raise(event_name: str, **_kwargs: object) -> None:
            raised.append(event_name)

        api.add("plugins.core.events", "event.raise", fake_event_raise, instance=True, force=True)
        original = API.is_character_active
        try:
            api("libs.api:character.active.set")(True)
            assert api("libs.api:character.is.active")() is True
            api("libs.api:character.active.set")(False)
            assert api("libs.api:character.is.active")() is False
        finally:
            API.is_character_active = original

        assert raised == ["ev_libs.api_character_active", "ev_libs.api_character_inactive"]


class _ToplevelRemoveOwner:
    """Object carrying one class API and one instance API for removal tests."""

    def __init__(self) -> None:
        """Initialize the owner."""
        self.label = "owner"

    @AddAPI("toplevel.remove.class", description="class api")
    def _api_class(self) -> str:
        """Class API.

        Returns:
            A test string.

        Raises:
            None

        """
        return "class"

    @AddAPI("toplevel.remove.instance", description="instance api", instance=True)
    def _api_instance(self) -> str:
        """Instance API.

        Returns:
            A test string.

        Raises:
            None

        """
        return "instance"


class TestToplevelRemove:
    """Test api.toplevel.remove cleans up without raising."""

    def test_instance_api_removed_without_error(self) -> None:
        """An instance API is deleted and does not raise ValueError."""
        api = API(owner_id="test_owner")
        owner = _ToplevelRemoveOwner()
        api("libs.api:api.add.for.object")("tlr_instance", owner)
        assert api.get("tlr_instance:toplevel.remove.instance") is not None

        api("libs.api:api.toplevel.remove")("tlr_instance")

        with pytest.raises(APINotFoundError):
            api.get("tlr_instance:toplevel.remove.instance")

    def test_class_api_name_removed_from_addedin(self) -> None:
        """A normal class API is deleted and its name leaves addedin."""
        api = API(owner_id="test_owner")
        owner = _ToplevelRemoveOwner()
        api("libs.api:api.add.for.object")("tlr_class", owner)
        assert owner._api_class.api["addedin"]["tlr_class"] == ["toplevel.remove.class"]  # type: ignore[attr-defined]

        api("libs.api:api.toplevel.remove")("tlr_class")

        # The name leaves addedin, and #196 also prunes the now-empty toplevel entry
        assert "tlr_class" not in owner._api_class.api["addedin"]  # type: ignore[attr-defined]
        with pytest.raises(APINotFoundError):
            api.get("tlr_class:toplevel.remove.class")

    def test_function_without_api_attribute_removed(self) -> None:
        """A class API added by api.add without .api metadata does not raise."""
        api = API(owner_id="test_owner")
        api.add("tlr_plain", "plain.func", helper_function_one)
        assert api.get("tlr_plain:plain.func") is not None

        api("libs.api:api.toplevel.remove")("tlr_plain")

        with pytest.raises(APINotFoundError):
            api.get("tlr_plain:plain.func")


class _Owner:
    """A stand-in plugin with one class API, as the plugin base class registers them."""

    @AddAPI("thing.get", description="Get a thing")
    def _api_thing_get(self) -> str:
        """Get a thing.

        Returns:
            A test string.

        Raises:
            None

        """
        return "thing"


class TestToplevelRemoveLeftovers:
    """Test that removing a top-level API prunes stats, addedin keys and overrides (#196)."""

    @pytest.fixture(autouse=True)
    def _isolated_registries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Give each test copies of the shared class registry and stats, restored afterwards."""
        monkeypatch.setattr(API, "_class_api", dict(API._class_api))
        monkeypatch.setattr(STATS_MANAGER, "stats", dict(STATS_MANAGER.stats))

    def test_stats_pruned_and_reload_starts_at_zero(self) -> None:
        """Removal deletes the toplevel's stats; a reload counts from zero."""
        api = API(owner_id="p.stats")
        owner = _Owner()
        api._api_api_add_for_object("p.stats", owner)
        api("p.stats:thing.get")()
        api("p.stats:thing.get")()
        STATS_MANAGER.add_call("p.other:keep", "x")
        assert STATS_MANAGER.stats["p.stats:thing.get"].count == 2

        api._api_api_toplevel_remove("p.stats")

        assert not [k for k in STATS_MANAGER.stats if k.startswith("p.stats:")]
        assert "p.other:keep" in STATS_MANAGER.stats
        api._api_api_add_for_object("p.stats", owner)
        api("p.stats:thing.get")()
        assert STATS_MANAGER.stats["p.stats:thing.get"].count == 1

    def test_addedin_key_removed(self) -> None:
        """The now-empty addedin entry is deleted, other toplevels' entries stay."""
        api = API(owner_id="p.added")
        owner = _Owner()
        api._api_api_add_for_object("p.added", owner)
        api._api_api_add_for_object("p.added.keep", owner)
        addedin = _Owner._api_thing_get.api["addedin"]  # type: ignore[attr-defined]
        assert "p.added" in addedin

        api._api_api_toplevel_remove("p.added")

        assert "p.added" not in addedin
        assert "p.added.keep" in addedin

    def test_force_override_without_original_is_removed(self) -> None:
        """An entry the removed owner added in another toplevel is deleted."""
        over = API(owner_id="p.over")
        over.add("p.victim", "solo", helper_function_two, force=True, description="over")
        over._api_api_add_for_object("p.over", _Owner())
        keeper = API(owner_id="p.keeper")
        keeper.add("p.victim", "kept", helper_function_one, description="keeper")

        over._api_api_toplevel_remove("p.over")

        assert "p.victim:solo" not in API._class_api
        assert "p.over:thing.get" not in API._class_api
        assert over.get("libs.api:api.add") is not None
        assert API._class_api["p.victim:kept"].tfunction == helper_function_one

    def test_force_override_with_original_is_restored(self) -> None:
        """The overwritten API is put back when the overriding owner is removed."""
        victim = API(owner_id="p.victim2")
        victim.add("p.victim2", "f", helper_function_one, description="victim")
        over = API(owner_id="p.over2")
        over.add("p.victim2", "f", helper_function_two, force=True, description="over")
        assert API._class_api["p.victim2:f"].owner_id == "p.over2"

        over._api_api_toplevel_remove("p.over2")

        restored = API._class_api["p.victim2:f"]
        assert restored.tfunction == helper_function_one
        assert restored.owner_id == "p.victim2"
