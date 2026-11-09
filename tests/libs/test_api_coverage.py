"""Coverage tests for the API registry display, stats and lookup paths.

This module exercises behaviour of ``bastproxy.libs.api`` that the main API tests
do not reach:
- ``_api_data_get`` precedence (instance, ``base=True``, class fallback, missing)
- ``add_events`` registering the character events through ``event.add``
- ``_api_api_exists`` and ``_api_api_detail_get`` outcomes
- ``format_stats``, ``_stats_overall`` and ``_stats_for_specific_caller`` output
- the list helpers and the formatted API list
- ``APIItem.detail`` and ``APIStatItem``/``StatsManager`` accessors
- cleanup helpers for ``addedin`` bookkeeping and force-override chains

Test Classes:
    - `TestDataGet`: ``_api_data_get`` lookup order.
    - `TestAddEvents`: ``add_events`` registration.
    - `TestExistsAndDetail`: ``_api_api_exists`` and ``_api_api_detail_get``.
    - `TestStatsFormatting`: stats tables for plugin and caller views.
    - `TestListing`: list helpers and the formatted list.
    - `TestCleanupHelpers`: ``addedin`` and override-chain cleanup.
    - `TestAPIItem`: ``APIItem`` detail, repr and stats accessors.
    - `TestStatsManager`: ``StatsManager`` accessors.

"""

import types
from collections.abc import Iterator
from typing import Any

import pytest

from bastproxy.libs.api import API
from bastproxy.libs.api._api import APILOCATION
from bastproxy.libs.api._apiitem import APIItem
from bastproxy.libs.api._apistats import STATS_MANAGER, APIStatItem

TABLE_FORMAT = "plugins.core.utils:table.format"
EVENT_ADD = "plugins.core.events:event.add"


@pytest.fixture(autouse=True)
def _isolate_api_state() -> Iterator[None]:
    """Give each test an empty class registry and restore shared state afterwards.

    ``API._class_api`` and ``STATS_MANAGER.stats`` are shared state, so the dicts
    are emptied for the test and restored in place afterwards to keep every
    existing reference valid.

    """
    class_api_snapshot = dict(API._class_api)
    stats_snapshot = dict(STATS_MANAGER.stats)
    API._class_api.clear()
    STATS_MANAGER.stats.clear()
    yield
    API._class_api.clear()
    API._class_api.update(class_api_snapshot)
    STATS_MANAGER.stats.clear()
    STATS_MANAGER.stats.update(stats_snapshot)


def func_a() -> str:
    """Function A.

    Returns:
        A test string.

    """
    return "a"


def func_b() -> str:
    """Function B.

    Returns:
        A test string.

    """
    return "b"


def func_c() -> str:
    """Function C.

    Returns:
        A test string.

    """
    return "c"


def _register_table_format(
    api: API,
) -> list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]]:
    """Register a fake ``table.format`` API that records its arguments.

    Args:
        api: The API object to register the fake on.

    Returns:
        The list the fake appends each ``(title, data, columns)`` call to.

    """
    calls: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []

    def fake_table_format(
        title: str, data: list[dict[str, Any]], columns: list[dict[str, Any]]
    ) -> list[str]:
        """Record the call and return one line per row.

        Args:
            title: The table title.
            data: The row dicts.
            columns: The column definitions.

        Returns:
            The title followed by ``caller=count`` for each row.

        """
        calls.append((title, data, columns))
        return [title, *(f"{row['caller']}={row['count']}" for row in data)]

    api.add("plugins.core.utils", "table.format", fake_table_format)
    return calls


def _record_calls(full_api_name: str, callers: dict[str, int]) -> None:
    """Record calls in the shared stats manager.

    Args:
        full_api_name: The API the calls are for.
        callers: Mapping of caller id to the number of calls to record.

    """
    for caller, times in callers.items():
        for _ in range(times):
            STATS_MANAGER.add_call(full_api_name, caller)


class TestDataGet:
    """Test ``_api_data_get`` lookup order."""

    def test_instance_preferred_over_class(self) -> None:
        """An instance API wins over the class API of the same name."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        api.add("top", "name", func_b, instance=True)
        item = api._api_data_get("top:name")
        assert item is not None
        assert item.tfunction is func_b
        assert item.instance is True

    def test_base_returns_class_api(self) -> None:
        """``base=True`` skips the instance API and returns the class one."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        api.add("top", "name", func_b, instance=True)
        item = api._api_data_get("top:name", base=True)
        assert item is not None
        assert item.tfunction is func_a

    def test_class_fallback(self) -> None:
        """With no instance API the class API is returned."""
        api = API(owner_id="owner")
        api.add("top", "only", func_a)
        item = api._api_data_get("top:only")
        assert item is not None
        assert item.tfunction is func_a

    def test_missing_returns_none(self) -> None:
        """An unknown name returns None, also with ``base=True``."""
        api = API(owner_id="owner")
        assert api._api_data_get("top:missing") is None
        assert api._api_data_get("top:missing", base=True) is None


class TestAddEvents:
    """Test ``add_events`` registration."""

    def test_registers_both_events(self) -> None:
        """Both character events are registered with the libs.api location."""
        api = API(owner_id="owner")
        calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

        def fake_event_add(*args: Any, **kwargs: Any) -> None:
            """Record the call.

            Args:
                *args: Positional arguments.
                **kwargs: Keyword arguments.

            """
            calls.append((args, kwargs))

        api.add("plugins.core.events", "event.add", fake_event_add)
        api.add_events()
        assert [c[0] for c in calls] == [
            ("ev_libs.api_character_active", APILOCATION),
            ("ev_libs.api_character_inactive", APILOCATION),
        ]
        for _, kwargs in calls:
            assert "is_character_active" in kwargs["arg_descriptions"]
        assert "active" in calls[0][1]["description"]
        assert "inactive" in calls[1][1]["description"]

    def test_add_for_object_without_api_functions(self) -> None:
        """An object with no ``_api_`` methods registers nothing."""
        api = API(owner_id="owner")
        api._api_api_add_for_object("top", object())
        assert api.get_top_level_api_list("top:") == []


class TestExistsAndDetail:
    """Test ``_api_api_exists`` and ``_api_api_detail_get``."""

    @staticmethod
    def _register_loader(api: API, valid: bool, instantiated: bool) -> None:
        """Register fake plugin loader APIs.

        Args:
            api: The API object to register on.
            valid: Value returned by ``plugin.id.is.valid``.
            instantiated: Value returned by ``plugin.is.instantiated``.

        """
        api.add("libs.plugins.loader", "plugin.id.is.valid", lambda _pid: valid)
        api.add("libs.plugins.loader", "plugin.is.instantiated", lambda _pid: instantiated)

    def test_exists_missing(self) -> None:
        """A missing API does not exist."""
        assert API(owner_id="owner")._api_api_exists("top:missing") is False

    def test_exists_falsy_item(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A falsy lookup result does not exist."""
        api = API(owner_id="owner")
        monkeypatch.setattr(api, "get", lambda _loc: None)
        assert api._api_api_exists("top:name") is False

    def test_exists_hidden_when_plugin_not_instantiated(self) -> None:
        """A valid plugin that is not instantiated hides its APIs."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        self._register_loader(api, valid=True, instantiated=False)
        assert api._api_api_exists("top:name") is False

    def test_exists_visible_when_plugin_instantiated(self) -> None:
        """A valid, instantiated plugin exposes its APIs."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        self._register_loader(api, valid=True, instantiated=True)
        assert api._api_api_exists("top:name") is True

    def test_exists_non_plugin_owner(self) -> None:
        """An owner that is not a plugin id counts as existing."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        api.add("libs.plugins.loader", "plugin.id.is.valid", lambda _pid: False)
        assert api._api_api_exists("top:name") is True

    def test_detail_without_colon(self) -> None:
        """A name without ``:`` is reported as a bad format."""
        api = API(owner_id="owner")
        assert api._api_api_detail_get("nocolon") == ["nocolon is not a : api format"]

    def test_detail_not_in_api(self) -> None:
        """An unknown API is reported as missing."""
        api = API(owner_id="owner")
        assert api._api_api_detail_get("top:missing") == ["top:missing is not in the api"]

    def test_detail_class_only(self) -> None:
        """A class-only API shows only the class section."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a, description="Some text")
        out = api._api_api_detail_get("top:name")
        assert out[:2] == ["Class API", "============"]
        assert "Instance API" not in out
        assert any("top:name" in line for line in out)
        assert any("Some text" in line for line in out)

    def test_detail_class_and_instance_with_stats(self) -> None:
        """Both sections and the requested stats tables are shown."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        api.add("top", "name", func_b, instance=True)
        calls = _register_table_format(api)
        _record_calls("top:name", {"plugA:one": 2, "plugB": 1})
        out = api._api_api_detail_get("top:name", stats_by_plugin=True, stats_by_caller="plugA")
        assert "Class API" in out
        assert "Instance API" in out
        assert out.index("Class API") < out.index("Instance API")
        assert "Callers (Total Calls 3)" in out
        assert "plugA=2" in out
        assert "plugB=1" in out
        assert "Stats for plugA (Unique Callers: 1)" in out
        assert "plugA:one=2" in out
        assert len(calls) == 2

    def test_detail_stats_by_caller_matches_prefix_not_substring(self) -> None:
        """Caller keys are selected by prefix, not by substring."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        calls = _register_table_format(api)
        _record_calls("top:name", {"plugA": 1, "plugA.sub": 2, "other.plugA": 4})
        out = api._api_api_detail_get("top:name", stats_by_caller="plugA")
        assert "Stats for plugA (Unique Callers: 2)" in out
        assert "plugA=1" in out
        assert "plugA.sub=2" in out
        assert not any("other.plugA" in line for line in out)
        assert [row["caller"] for row in calls[-1][1]] == ["plugA", "plugA.sub"]

    def test_detail_without_stats_flags_has_no_tables(self) -> None:
        """Stats tables are not built unless requested."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        calls = _register_table_format(api)
        _record_calls("top:name", {"plugA": 1})
        api._api_api_detail_get("top:name")
        assert calls == []

    def test_detail_show_function_code(self) -> None:
        """``show_function_code`` includes the function source."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        out = api._api_api_detail_get("top:name", show_function_code=True)
        assert any("def func_a" in line for line in out)


class TestStatsFormatting:
    """Test the stats tables."""

    def test_format_stats_unknown_api(self) -> None:
        """An unknown API has no stats."""
        assert API(owner_id="owner").format_stats("top:missing", True, "x") == []

    def test_format_stats_no_flags(self) -> None:
        """No flag requested gives no output even with stats recorded."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        _record_calls("top:name", {"plugA": 1})
        assert api.format_stats("top:name", False, "") == []

    def test_stats_overall_sorted_by_plugin(self) -> None:
        """The overall table lists plugin-level counts sorted by caller."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        calls = _register_table_format(api)
        _record_calls("top:name", {"zeta:x": 1, "alpha:y": 2, "alpha:z": 1})
        out = api.format_stats("top:name", True, "")
        assert out == ["", "Callers (Total Calls 4)", "alpha=3", "zeta=1"]
        title, data, columns = calls[0]
        assert title == "Callers (Total Calls 4)"
        assert data == [{"caller": "alpha", "count": 3}, {"caller": "zeta", "count": 1}]
        assert [c["key"] for c in columns] == ["caller", "count"]

    def test_stats_for_specific_caller_filters_prefix(self) -> None:
        """The caller table keeps only detailed callers with the prefix."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        calls = _register_table_format(api)
        _record_calls("top:name", {"alpha:b": 1, "alpha:a": 2, "beta:a": 5})
        out = api.format_stats("top:name", False, "alpha")
        assert out == [
            "",
            "Stats for alpha (Unique Callers: 2)",
            "alpha:a=2",
            "alpha:b=1",
        ]
        assert calls[0][1] == [
            {"caller": "alpha:a", "count": 2},
            {"caller": "alpha:b", "count": 1},
        ]

    def test_stats_for_unmatched_caller(self) -> None:
        """A prefix that matches nothing gives an empty table."""
        api = API(owner_id="owner")
        api.add("top", "name", func_a)
        _register_table_format(api)
        _record_calls("top:name", {"alpha": 1})
        out = api.format_stats("top:name", False, "zzz")
        assert out == ["", "Stats for zzz (Unique Callers: 0)"]


class TestListing:
    """Test the list helpers and the formatted list."""

    @staticmethod
    def _populate(api: API) -> None:
        """Register APIs under two top levels plus an instance API.

        Args:
            api: The API object to register on.

        """
        api.add("alpha", "one", func_a, description="First\nmore")
        api.add("alpha", "two", func_b)
        api.add("beta", "three", func_c, instance=True, description="Third")

    def test_top_level_list(self) -> None:
        """Class and instance APIs under a prefix are listed once each."""
        api = API(owner_id="owner")
        self._populate(api)
        assert sorted(api.get_top_level_api_list("alpha:")) == ["alpha:one", "alpha:two"]
        assert api.get_top_level_api_list("beta:") == ["beta:three"]

    def test_full_list_sorted(self) -> None:
        """The full list is sorted and includes instance APIs."""
        api = API(owner_id="owner")
        self._populate(api)
        full = api.get_full_api_list()
        assert full == sorted(full)
        assert {"alpha:one", "alpha:two", "beta:three"} <= set(full)

    def test_data_list_top_level(self) -> None:
        """Data entries carry names, counts and the joined description."""
        api = API(owner_id="owner")
        self._populate(api)
        _record_calls("alpha:one", {"plugA": 3})
        data = api._api_data_list("alpha:")
        assert [d["full_api_name"] for d in data] == ["alpha:one", "alpha:two"]
        assert data[0] == {
            "toplevel": "alpha",
            "name": "one",
            "full_api_name": "alpha:one",
            "called_count": 3,
            "description": "First more",
        }
        assert data[1]["called_count"] == 0

    def test_data_list_all(self) -> None:
        """Without a top level every API is listed, sorted by name."""
        api = API(owner_id="owner")
        self._populate(api)
        names = [d["full_api_name"] for d in api._api_data_list()]
        assert names == sorted(names)
        assert {"alpha:one", "beta:three"} <= set(names)

    def test_data_list_skips_unresolvable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Names whose data cannot be resolved are left out."""
        api = API(owner_id="owner")
        self._populate(api)
        monkeypatch.setattr(api, "_api_data_get", lambda _name, base=False: None)
        assert api._api_data_list("alpha:") == []

    def test_formatted_list_separates_top_levels(self) -> None:
        """Each top level gets a header and a separator precedes later ones."""
        api = API(owner_id="owner")
        self._populate(api)
        _record_calls("alpha:one", {"plugA": 2})
        out = api._api_api_list_formatted()
        sep = "@B" + "-" * 50 + "@w"
        assert f"@G{'alpha':<10}@w" in out
        assert f"@G{'beta':<10}@w" in out
        alpha_at = out.index(f"@G{'alpha':<10}@w")
        beta_at = out.index(f"@G{'beta':<10}@w")
        assert alpha_at < beta_at
        # the separator before the beta header comes from the "not first" branch
        assert out[beta_at - 1] == sep
        assert any("alpha:one" in line and "called 2 times" in line for line in out)
        assert "        First@w" in out
        assert "        Third@w" in out

    def test_formatted_list_single_top_level(self) -> None:
        """Filtering to one top level gives one header and no extra separator."""
        api = API(owner_id="owner")
        self._populate(api)
        out = api._api_api_list_formatted("alpha:")
        assert out.count(f"@G{'alpha':<10}@w") == 1
        assert not any("beta" in line for line in out)
        assert out.count("@B" + "-" * 50 + "@w") == 1

    def test_formatted_list_empty_description(self) -> None:
        """An API without a description gets a blank description line."""
        api = API(owner_id="owner")
        api.add("gamma", "nodesc", lambda: None)
        out = api._api_api_list_formatted("gamma:")
        assert out[-1] == "        @w"

    def test_formatted_list_skips_unresolvable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Names whose data cannot be resolved only get their headers."""
        api = API(owner_id="owner")
        self._populate(api)
        monkeypatch.setattr(api, "_api_data_get", lambda _name, base=False: None)
        out = api._api_api_list_formatted("alpha:")
        assert out == [f"@G{'alpha':<10}@w", "@B" + "-" * 50 + "@w"]


class TestCleanupHelpers:
    """Test ``addedin`` and override-chain cleanup."""

    def test_discard_addedin_removes_name(self) -> None:
        """A formatted name is removed from the toplevel's addedin list."""

        class Owner:
            """Owner with a formatted API name."""

            def __init__(self) -> None:
                """Set the attribute used in the API name."""
                self.ident = "x"

            def method(self) -> None:
                """Do nothing."""

        owner = Owner()
        bound = owner.method
        meta: dict[str, Any] = {"name": "thing.{ident}", "addedin": {"top": ["thing.x", "keep"]}}
        owner.method.__func__.api = meta  # type: ignore[attr-defined]
        try:
            API._discard_addedin(bound, "top")
        finally:
            del owner.method.__func__.api  # type: ignore[attr-defined]
        assert meta["addedin"]["top"] == ["keep"]

    def test_discard_addedin_unformattable_name_is_ignored(self) -> None:
        """A function without ``__self__`` leaves the list untouched."""

        def plain() -> None:
            """Do nothing."""

        meta: dict[str, Any] = {"name": "thing.{ident}", "addedin": {"top": ["thing.x"]}}
        plain.api = meta  # type: ignore[attr-defined]
        API._discard_addedin(plain, "top")
        assert meta["addedin"]["top"] == ["thing.x"]

    def test_discard_addedin_name_not_listed(self) -> None:
        """A name that is not in the addedin list leaves it untouched."""

        class Owner:
            """Owner with a formatted API name."""

            def __init__(self) -> None:
                """Set the attribute used in the API name."""
                self.ident = "x"

            def method(self) -> None:
                """Do nothing."""

        owner = Owner()
        meta: dict[str, Any] = {"name": "thing.{ident}", "addedin": {"top": ["other"]}}
        owner.method.__func__.api = meta  # type: ignore[attr-defined]
        try:
            API._discard_addedin(owner.method, "top")
        finally:
            del owner.method.__func__.api  # type: ignore[attr-defined]
        assert meta["addedin"]["top"] == ["other"]

    def test_discard_addedin_without_meta(self) -> None:
        """Functions without api metadata or addedin entries are ignored."""
        API._discard_addedin(func_a, "top")

        def tagged() -> None:
            """Do nothing."""

        tagged.api = {"name": "n", "addedin": {}}  # type: ignore[attr-defined]
        API._discard_addedin(tagged, "top")
        assert tagged.api == {"name": "n", "addedin": {}}  # type: ignore[attr-defined]

    def test_prune_ignores_non_dict_addedin(self) -> None:
        """A function whose addedin is not a dict is skipped without error."""

        def odd() -> None:
            """Do nothing."""

        odd.api = {"addedin": "not a dict"}  # type: ignore[attr-defined]
        API(owner_id="owner")._prune_toplevel_leftovers("top", [odd])
        assert odd.api == {"addedin": "not a dict"}  # type: ignore[attr-defined]

    def test_prune_drops_addedin_entry(self) -> None:
        """The removed toplevel's addedin entry is dropped."""

        def tagged() -> None:
            """Do nothing."""

        tagged.api = {"addedin": {"top": ["n"], "other": ["m"]}}  # type: ignore[attr-defined]
        API(owner_id="owner")._prune_toplevel_leftovers("top", [tagged])
        assert tagged.api == {"addedin": {"other": ["m"]}}  # type: ignore[attr-defined]

    def test_override_chain_of_same_owner_is_unwound(self) -> None:
        """A chain of overrides all made by the removed owner leaves nothing behind."""
        mine = API(owner_id="mine")
        mine.add("foreign", "name", func_a)
        mine.add("foreign", "name", func_b, force=True)
        mine.add("foreign", "name", func_c, force=True)
        assert mine._api_data_get("foreign:name").tfunction is func_c  # type: ignore[union-attr]
        mine._api_api_toplevel_remove("mine")
        assert mine._api_data_get("foreign:name") is None

    def test_override_restores_other_owners_api(self) -> None:
        """Overrides by the removed owner are replaced by another owner's API."""
        other = API(owner_id="other")
        other.add("foreign", "name", func_a)
        mine = API(owner_id="mine")
        mine.add("foreign", "name", func_b, force=True)
        mine.add("foreign", "name", func_c, force=True)
        mine._api_api_toplevel_remove("mine")
        restored = mine._api_data_get("foreign:name")
        assert restored is not None
        assert restored.tfunction is func_a
        assert restored.owner_id == "other"


class TestAPIItem:
    """Test ``APIItem`` detail, repr and stats accessors."""

    def test_repr_and_str(self) -> None:
        """Repr and str both name the API, owner and function."""
        item = APIItem("top:name", func_a, "owner")
        expected = f"APIItem(top:name, owner, {func_a})"
        assert repr(item) == expected
        assert str(item) == expected

    def test_stats_property_creates_entry(self) -> None:
        """The stats property returns the manager's item, creating it if needed."""
        item = APIItem("top:name", func_a, "owner")
        stats = item.stats
        assert isinstance(stats, APIStatItem)
        assert STATS_MANAGER.stats["top:name"] is stats
        assert item.count == 0
        STATS_MANAGER.add_call("top:name", "plugA")
        assert item.count == 1

    def test_detail_description_lines(self) -> None:
        """Only the first non-empty line gets the label; blanks are skipped."""
        item = APIItem("top:name", func_a, "owner", description=["", "second", "third"])
        out = item.detail()
        assert "@CDescription@w : second" not in out
        assert f"{'':<13}   second" in out
        assert f"{'':<13}   third" in out
        first = APIItem("top:name", func_a, "owner", description=["first", "next"]).detail()
        assert f"@C{'Description':<11}@w : first" in first
        assert f"{'':<13}   next" in first

    def test_detail_without_docstring(self) -> None:
        """A function without a docstring still produces a signature line."""

        def nodoc() -> None:
            pass

        out = APIItem("top:name", nodoc, "owner", description="x").detail()
        assert any(line.startswith("@Gtop:name@w(") for line in out)
        assert not any("Function A" in line for line in out)

    def test_detail_substitutes_docstring_placeholders(self) -> None:
        """``%(name)s`` placeholders in the docstring are filled in."""

        def templated() -> None:
            """API %(name)s / %(cmdname)s at %(api_location)s."""

        out = APIItem("top:sub:name", templated, "owner", description="x").detail()
        assert "API top / sub:name at top:sub:name." in out

    def test_detail_without_source_file(self) -> None:
        """A function with no resolvable source file gets no definition line."""
        generated = types.FunctionType(
            func_a.__code__.replace(co_filename="<generated>"),
            {"__name__": "generated_nowhere"},
            "generated",
        )
        out = APIItem("top:gen", generated, "owner", description="x").detail()
        assert not any(line.startswith("function defined in") for line in out)

    def test_detail_function_code_escapes_at(self) -> None:
        """Source lines are included with ``@`` doubled."""

        def with_at() -> str:
            return "a@b"

        out = APIItem("top:name", with_at, "owner", description="x").detail(show_function_code=True)
        assert any("a@@b" in line for line in out)

    def test_detail_includes_overwritten_api(self) -> None:
        """An overwritten API is described under an explanatory heading."""
        item = APIItem("top:name", func_b, "newowner", description="x")
        item.overwritten_api = APIItem("top:name", func_a, "oldowner", description="x")
        out = item.detail()
        at = out.index("This API overwrote the following:")
        assert any("oldowner" in line for line in out[at:])

    def test_call_records_stats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calling the item calls the function and counts the call."""
        monkeypatch.setattr("bastproxy.libs.api._apiitem.get_caller_owner_id", lambda: "plugA")
        item = APIItem("top:name", func_a, "owner")
        assert item() == "a"
        assert item.stats.calls_by_caller == {"plugA": 1}


class TestStatsManager:
    """Test ``StatsManager`` accessors."""

    def test_get_all_stats_returns_registry(self) -> None:
        """``get_all_stats`` returns the live stats dict."""
        STATS_MANAGER.add_call("top:name", "plugA")
        assert STATS_MANAGER.get_all_stats() is STATS_MANAGER.stats
        assert STATS_MANAGER.get_all_stats()["top:name"].count == 1

    def test_get_stats_creates_and_reuses(self) -> None:
        """``get_stats`` creates a missing item once and then reuses it."""
        first = STATS_MANAGER.get_stats("top:new")
        assert first.full_api_name == "top:new"
        assert first.count == 0
        assert STATS_MANAGER.get_stats("top:new") is first

    def test_unknown_caller_counts_once_per_dump(self) -> None:
        """Calls with an unknown caller are all counted."""
        stat = APIStatItem("top:name")
        stat.add_call("unknown")
        stat.add_call("unknown")
        assert stat.count == 2
        assert stat.detailed_calls == {"unknown": 2}
