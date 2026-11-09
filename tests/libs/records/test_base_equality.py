"""Tests that record base classes compare and hash by UUID, not content."""

from bastproxy.libs.records.rtypes.base import BaseDictRecord


def test_dict_record_uuid_equality() -> None:
    a = BaseDictRecord(data={"k": "v"}, track_record=False)
    b = BaseDictRecord(data={"k": "v"}, track_record=False)
    assert a == a
    assert a != b
    assert hash(a) != hash(b)
    assert len({a, b}) == 2
    assert a != {"k": "v"}
