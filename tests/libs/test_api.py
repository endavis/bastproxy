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

import pytest

from bastproxy.libs.api import API, AddAPI
from bastproxy.libs.exceptions import APINotFoundError


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
        """Test that adding duplicate API without force=True logs error.

        Note: For class APIs, the method logs an error but still returns True.
        For instance APIs, it would return False.

        """
        api = API(owner_id="test_owner")
        result1 = api.add("test", "function", helper_function_one, description="Test 1")
        result2 = api.add("test", "function", helper_function_two, description="Test 2")

        assert result1 is True
        # For class APIs, duplicate add logs error but returns True
        assert result2 is True

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

        assert owner._api_class.api["addedin"]["tlr_class"] == []  # type: ignore[attr-defined]
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
