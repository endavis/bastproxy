"""Tests that record base classes compare and hash by UUID, not content."""

import pytest

from bastproxy.libs.records.rtypes.base import (
    BaseDictRecord,
    BaseListRecord,
    TrackedUserList,
)


def _make_list_record() -> BaseListRecord:
    return BaseListRecord("same text", track_record=False)


@pytest.mark.parametrize("factory", [_make_list_record])
class TestListRecordEquality:
    def test_same_content_not_equal(self, factory) -> None:
        a, b = factory(), factory()
        assert a.data == b.data
        assert a != b

    def test_same_content_different_hash(self, factory) -> None:
        a, b = factory(), factory()
        assert hash(a) != hash(b)

    def test_hashable_in_set_and_dict(self, factory) -> None:
        a, b = factory(), factory()
        assert len({a, b}) == 2
        assert {a: 1}[a] == 1
        assert a in {a}
        assert b not in {a}

    def test_not_equal_to_plain_list(self, factory) -> None:
        a = factory()
        assert a != list(a.data)
        assert list(a.data) != a

    def test_equal_to_itself(self, factory) -> None:
        a = factory()
        assert a == a
        assert hash(a) == hash(a)


def test_dict_record_uuid_equality() -> None:
    a = BaseDictRecord(data={"k": "v"}, track_record=False)
    b = BaseDictRecord(data={"k": "v"}, track_record=False)
    assert a == a
    assert a != b
    assert hash(a) != hash(b)
    assert len({a, b}) == 2
    assert a != {"k": "v"}


def test_tracked_user_list_uuid_equality() -> None:
    a = TrackedUserList(["x"])
    b = TrackedUserList(["x"])
    assert a == a
    assert a != b
    assert hash(a) != hash(b)
    assert len({a, b}) == 2
    assert a != ["x"]
