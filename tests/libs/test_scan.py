# Project: bastproxy
# Filename: tests/libs/test_scan.py
#
# File Description: Tests for the dir() method scanner
#
# By: Bast
"""Unit tests for bastproxy.libs.scan.find_methods."""

import types

import pytest

from bastproxy.libs.scan import find_methods


def _always(_m: types.MethodType) -> bool:
    return True


class _Leaf:
    def _x(self) -> None:
        pass


class _Mid:
    def __init__(self) -> None:
        self._leaf = _Leaf()

    def _y(self) -> None:
        pass


class TestFindMethods:
    """Test suite for find_methods."""

    def test_dunder_names_skipped(self) -> None:
        """A matching dunder-named method is not returned."""

        class C:
            def __x__(self) -> None:
                pass

            def _a(self) -> None:
                pass

        c = C()
        found = find_methods(c, _always)
        assert [m.__name__ for m in found if m.__name__.startswith("_")] == ["_a"]
        assert all(not m.__name__.startswith("__") for m in found)

    def test_attribute_error_skipped(self) -> None:
        """A property raising AttributeError is skipped and the scan continues."""

        class C:
            @property
            def _bad(self) -> int:
                raise AttributeError("nope")

            def _good(self) -> None:
                pass

        found = find_methods(C(), _always)
        assert [m.__name__ for m in found] == ["_good"]

    def test_other_errors_propagate(self) -> None:
        """A property raising ValueError propagates."""

        class C:
            @property
            def _bad(self) -> int:
                raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            find_methods(C(), _always)

    def test_only_bound_methods_reach_predicate(self) -> None:
        """Plain functions, staticmethods and non-callables are never matched."""

        class C:
            def __init__(self) -> None:
                self._plain = lambda: None
                self._number = 5

            @staticmethod
            def _static() -> None:
                pass

            def _real(self) -> None:
                pass

        seen: list[object] = []

        def record(m: types.MethodType) -> bool:
            seen.append(m)
            return True

        found = find_methods(C(), record)
        assert [m.__name__ for m in found] == ["_real"]
        assert all(isinstance(s, types.MethodType) for s in seen)

    def test_dir_order_with_recursion(self) -> None:
        """Results follow dir() order, with recursion spliced in place."""

        class Child:
            def _x(self) -> None:
                pass

        class Base:
            def __init__(self) -> None:
                self._b = Child()

            def _a(self) -> None:
                pass

            def _c(self) -> None:
                pass

        base = Base()

        def pred(m: types.MethodType) -> bool:
            return m.__name__ in {"_a", "_c", "_x"}

        found = find_methods(base, pred, recurse=True)
        assert found == [base._a, base._b._x, base._c]

    def test_no_descent_without_recurse(self) -> None:
        """recurse=False never descends."""
        mid = _Mid()
        found = find_methods(mid, lambda m: m.__name__ == "_x")
        assert found == []

    def test_one_level_only(self) -> None:
        """A grandchild match is not found."""

        class Top:
            def __init__(self) -> None:
                self._mid = _Mid()

        found = find_methods(Top(), lambda m: m.__name__ == "_x", recurse=True)
        assert found == []
        # the child level is reached
        top = Top()
        found = find_methods(top, lambda m: m.__name__ == "_y", recurse=True)
        assert found == [top._mid._y]

    def test_non_matching_methods_are_recursed_into(self) -> None:
        """Non-matching methods are passed to descend_into."""

        class C:
            def _m(self) -> None:
                pass

        c = C()
        seen: list[object] = []

        def descend(attr: object) -> bool:
            seen.append(attr)
            return True

        find_methods(c, lambda m: False, recurse=True, descend_into=descend)
        assert c._m in seen

    def test_descend_into_false_blocks_descent(self) -> None:
        """When descend_into returns false the attribute is not scanned."""
        mid = _Mid()
        found = find_methods(
            mid,
            lambda m: m.__name__ == "_x",
            recurse=True,
            descend_into=lambda attr: False,
        )
        assert found == []
        found = find_methods(
            mid, lambda m: m.__name__ == "_x", recurse=True, descend_into=lambda a: True
        )
        assert len(found) == 1

    def test_name_filter_runs_before_getattr(self) -> None:
        """A name failing the filter is never evaluated."""
        counts = {"skipped": 0, "kept": 0}

        class C:
            @property
            def _skipped(self) -> int:
                counts["skipped"] += 1
                return 1

            @property
            def _phook_kept(self) -> int:
                counts["kept"] += 1
                return 1

        find_methods(C(), _always, name_filter=lambda n: n.startswith("_phook_"))
        assert counts == {"skipped": 0, "kept": 1}

    def test_returns_bound_methods_list(self) -> None:
        """The result is a list of MethodType bound to base."""
        leaf = _Leaf()
        found = find_methods(leaf, _always)
        assert isinstance(found, list)
        assert found
        assert all(isinstance(m, types.MethodType) and m.__self__ is leaf for m in found)
