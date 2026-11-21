"""Tests for Callback identity (#678)."""

from bastproxy.libs.callback import Callback


def f() -> None:
    """Callback target."""


def g() -> None:
    """Another callback target."""


def test_swapped_name_and_owner_differ() -> None:
    assert Callback("a", "b", f) != Callback("b", "a", f)


def test_equal_identity_is_equal_and_hashes_equal() -> None:
    c1 = Callback("a", "b", f)
    c2 = Callback("a", "b", f)
    assert c1 == c2
    assert hash(c1) == hash(c2)
    assert len({c1, c2}) == 1


def test_different_func_unequal() -> None:
    assert Callback("a", "b", f) != Callback("a", "b", g)


def test_different_owner_unequal() -> None:
    assert Callback("a", "b", f) != Callback("a", "c", f)


def test_equal_to_plain_function() -> None:
    assert Callback("a", "b", f) == f


def test_hash_is_tuple_hash() -> None:
    assert hash(Callback("a", "b", f)) == hash((f, "b", "a"))
