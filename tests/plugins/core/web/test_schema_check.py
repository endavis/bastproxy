"""The schema checker used by the socket schema tests."""

from typing import Any

import pytest

from .schema_check import errors, is_valid, load_schema


def ok(schema: dict[str, Any], value: Any) -> bool:
    return is_valid(schema, value)


def test_the_shipped_schema_loads() -> None:
    assert load_schema()["$schema"].endswith("2020-12/schema")


@pytest.mark.parametrize(
    ("kind", "good", "bad"),
    [
        ("object", {}, []),
        ("array", [], {}),
        ("string", "a", 1),
        ("boolean", False, 0),
        ("null", None, 0),
        ("integer", 3, 1.0),
        ("integer", 0, True),
        ("number", 1.5, True),
    ],
)
def test_type(kind: str, good: Any, bad: Any) -> None:
    assert ok({"type": kind}, good)
    assert not ok({"type": kind}, bad)


def test_an_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="unsupported type"):
        errors({"type": "date"}, 1)


def test_const_and_enum_are_type_strict() -> None:
    assert ok({"const": 1}, 1)
    assert not ok({"const": 1}, True)
    assert not ok({"const": 1}, 1.0)
    assert not ok({"const": True}, 1)
    assert ok({"enum": ["a", 2]}, 2)
    assert not ok({"enum": ["a", 2]}, "b")
    assert not ok({"enum": [1]}, True)
    assert not ok({"const": [1]}, [True])
    assert ok({"const": {"a": [1]}}, {"a": [1]})


def test_required_properties_and_additional_properties() -> None:
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "integer"}, "b": {"type": "string"}},
        "additionalProperties": False,
    }
    assert ok(schema, {"a": 1})
    assert ok(schema, {"a": 1, "b": "x"})
    assert errors(schema, {}) == ["needs 'a'"]
    assert not ok(schema, {"a": "x"})
    assert not ok(schema, {"a": 1, "c": 1})
    assert ok({"type": "object", "properties": {}}, {"c": 1})


def test_items() -> None:
    schema = {"type": "array", "items": {"type": "integer"}}
    assert ok(schema, [1, 2])
    assert not ok(schema, [1, "x"])
    assert errors(schema, [1, "x"]) == ["[1] is not of type integer"]


def test_length_boundaries() -> None:
    schema = {"type": "string", "minLength": 2, "maxLength": 3}
    assert [ok(schema, "a" * n) for n in range(5)] == [False, False, True, True, False]


def test_range_boundaries() -> None:
    schema = {"type": "integer", "minimum": 1, "maximum": 3}
    assert [ok(schema, n) for n in range(5)] == [False, True, True, True, False]


def test_one_of_needs_exactly_one_match() -> None:
    schema = {"oneOf": [{"type": "integer"}, {"type": "string"}]}
    assert ok(schema, 1)
    assert not ok(schema, None)
    assert not ok({"oneOf": [{"type": "integer"}, {"minimum": 0}]}, 1)


def test_ref_resolves_local_defs() -> None:
    schema = {"$defs": {"n": {"type": "integer"}}, "type": "array", "items": {"$ref": "#/$defs/n"}}
    assert ok(schema, [1])
    assert not ok(schema, ["x"])


def test_a_bad_ref_raises() -> None:
    with pytest.raises(ValueError, match="only local"):
        errors({"$ref": "http://example.com/x"}, 1)
    with pytest.raises(ValueError, match="unknown"):
        errors({"$ref": "#/$defs/missing", "$defs": {}}, 1)


def test_an_unsupported_keyword_raises() -> None:
    with pytest.raises(ValueError, match="pattern"):
        errors({"type": "string", "pattern": "^a"}, "a")


def test_annotations_are_ignored() -> None:
    schema = {"title": "t", "description": "d", "$comment": "c", "$id": "x", "type": "integer"}
    assert ok(schema, 1)
