"""A small JSON Schema checker for the client socket schema (no schema library is a dependency).

It supports only the keywords the schema uses and raises ``ValueError`` for any other one, so
the schema cannot rely on a constraint this checker would skip.
"""

import importlib.resources
import json
from typing import Any

# keywords that describe the schema and never constrain a value
ANNOTATIONS = frozenset({"$schema", "$id", "$comment", "title", "description", "$defs"})
CONSTRAINTS = frozenset(
    {
        "$ref",
        "oneOf",
        "type",
        "const",
        "enum",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
    }
)


def load_schema() -> dict[str, Any]:
    """The socket schema as shipped in the package."""
    resource = importlib.resources.files("bastproxy.plugins.core.web").joinpath(
        "schema", "socket-v1.schema.json"
    )
    loaded = json.loads(resource.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _same(left: Any, right: Any) -> bool:
    """Json equality: ``True`` is not 1 and ``1.0`` is not 1, at any depth."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _same(a, b) for a, b in zip(left, right, strict=True)
        )
    return bool(left == right)


def _type_ok(kind: str, value: Any) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    msg = f"unsupported type {kind!r}"
    raise ValueError(msg)


def _resolve(root: dict[str, Any], reference: str) -> dict[str, Any]:
    prefix = "#/$defs/"
    if not reference.startswith(prefix):
        msg = f"unsupported $ref {reference!r}: only local #/$defs/ references"
        raise ValueError(msg)
    target = root["$defs"].get(reference[len(prefix) :])
    if not isinstance(target, dict):
        msg = f"unknown $ref {reference!r}"
        raise ValueError(msg)
    return target


def errors(schema: dict[str, Any], value: Any, root: dict[str, Any] | None = None) -> list[str]:
    """The reasons ``value`` does not match ``schema``; empty when it does."""
    root = schema if root is None else root
    unknown = set(schema) - ANNOTATIONS - CONSTRAINTS
    if unknown:
        msg = f"unsupported schema keyword(s): {sorted(unknown)}"
        raise ValueError(msg)
    found: list[str] = []
    if "$ref" in schema:
        found += errors(_resolve(root, schema["$ref"]), value, root)
    if "oneOf" in schema:
        matches = sum(1 for option in schema["oneOf"] if not errors(option, value, root))
        if matches != 1:
            found.append(f"matches {matches} of the oneOf options, not exactly 1")
    if "type" in schema and not _type_ok(schema["type"], value):
        return [*found, f"is not of type {schema['type']}"]
    if "const" in schema and not _same(schema["const"], value):
        found.append(f"is not {schema['const']!r}")
    if "enum" in schema and not any(_same(option, value) for option in schema["enum"]):
        found.append(f"is not one of {schema['enum']!r}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            found.append(f"is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            found.append(f"is longer than {schema['maxLength']}")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            found.append(f"is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            found.append(f"is above {schema['maximum']}")
    if isinstance(value, dict):
        found += _object_errors(schema, value, root)
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            found += [f"[{index}] {e}" for e in errors(schema["items"], item, root)]
    return found


def _object_errors(
    schema: dict[str, Any], value: dict[str, Any], root: dict[str, Any]
) -> list[str]:
    found = [f"needs {name!r}" for name in schema.get("required", []) if name not in value]
    properties: dict[str, Any] = schema.get("properties", {})
    for name, item in value.items():
        if name in properties:
            found += [f".{name} {e}" for e in errors(properties[name], item, root)]
        elif schema.get("additionalProperties") is False:
            found.append(f"has the extra property {name!r}")
    return found


def is_valid(schema: dict[str, Any], value: Any) -> bool:
    """True when ``value`` matches ``schema``."""
    return not errors(schema, value)
