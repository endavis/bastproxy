"""Tests that API helper functions do not keep references to their arguments.

Caching `_api_get_function_owner_plugin` and `get_args` with `lru_cache` kept
bound methods (and so their instances) and functions (and so their modules)
alive after a plugin was unloaded.

Test Classes:
    - `TestOwnerLookup`: Functional and reference tests for the owner lookup.
    - `TestGetArgs`: Functional and reference tests for `get_args`.

"""

import gc
import types
import weakref

from bastproxy.libs.api import API
from bastproxy.libs.api._functools import get_args


class _Plugin:
    """Plugin-like object with a plugin_id."""

    plugin_id = "my_plugin"

    def method(self, first: int, second: str) -> None:
        """Bound method used for lookups.

        Args:
            first: First argument.
            second: Second argument.

        Raises:
            None

        """


def _plain_function(value: int) -> int:
    """Plain function with no owner.

    Args:
        value: A value.

    Returns:
        The value.

    Raises:
        None

    """
    return value


def _make_api() -> API:
    """Create an API instance for tests.

    Returns:
        A new API instance.

    Raises:
        None

    """
    return API(owner_id="test_cache_refs")


class TestOwnerLookup:
    """Tests for `API._api_get_function_owner_plugin`."""

    def test_bound_method_returns_plugin_id(self) -> None:
        """A bound method of an object with plugin_id returns that id."""
        api = _make_api()
        assert api._api_get_function_owner_plugin(_Plugin().method) == "my_plugin"

    def test_plain_function_returns_unknown(self) -> None:
        """A plain function has no owner."""
        api = _make_api()
        assert api._api_get_function_owner_plugin(_plain_function) == "unknown"

    def test_instance_not_kept_alive(self) -> None:
        """The looked-up instance can be garbage collected."""
        api = _make_api()
        obj = _Plugin()
        ref = weakref.ref(obj)
        api._api_get_function_owner_plugin(obj.method)
        del obj
        gc.collect()
        assert ref() is None

    def test_function_from_module_not_kept_alive(self) -> None:
        """A function from a throwaway module can be garbage collected."""
        api = _make_api()
        module = types.ModuleType("throwaway_cache_module")
        exec("def func():\n    return 1\n", module.__dict__)
        func = module.func
        ref = weakref.ref(func)
        api._api_get_function_owner_plugin(func)
        del func, module
        gc.collect()
        assert ref() is None


class TestGetArgs:
    """Tests for `get_args`."""

    def test_excludes_self_and_formats(self) -> None:
        """Self is excluded and arguments are colour formatted."""
        assert get_args(_Plugin().method) == "@Yfirst@w, @Ysecond@w"

    def test_plain_function(self) -> None:
        """A plain function lists its parameters."""
        assert get_args(_plain_function) == "@Yvalue@w"

    def test_instance_not_kept_alive(self) -> None:
        """The instance behind a bound method can be garbage collected."""
        obj = _Plugin()
        ref = weakref.ref(obj)
        get_args(obj.method)
        del obj
        gc.collect()
        assert ref() is None

    def test_function_from_module_not_kept_alive(self) -> None:
        """A function from a throwaway module can be garbage collected."""
        module = types.ModuleType("throwaway_cache_module_args")
        exec("def func(a):\n    return a\n", module.__dict__)
        func = module.func
        ref = weakref.ref(func)
        get_args(func)
        del func, module
        gc.collect()
        assert ref() is None
