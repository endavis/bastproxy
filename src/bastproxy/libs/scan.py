# Project: bastproxy
# Filename: libs/scan.py
#
# File Description: one dir() scanner for decorated bound methods
#
# By: Bast
"""Find bound methods on an object by walking ``dir()``.

The API, event, command and plugin hook systems each need the bound methods of
an object that carry a marker. They share this one scanner and keep their own
filter and return shape.

Behaviour:
    - Names starting with ``__`` are skipped.
    - Only ``AttributeError`` from ``getattr`` is swallowed; any other
      exception propagates.
    - Results follow ``dir()`` order.
    - Recursion goes one level only, into every non-matching attribute.

Functions:
    - find_methods: scan an object for bound methods matching a predicate.
"""

import types
from collections.abc import Callable


def find_methods(
    base: object,
    predicate: Callable[[types.MethodType], bool],
    *,
    recurse: bool = False,
    name_filter: Callable[[str], bool] | None = None,
    descend_into: Callable[[object], bool] | None = None,
) -> list[types.MethodType]:
    """Return the bound methods of ``base`` that pass ``predicate``.

    Args:
        base: The object to scan.
        predicate: Called only with bound methods; true keeps the method.
        recurse: Scan every non-matching attribute one level deep.
        name_filter: If set, a ``dir()`` name must pass it before ``getattr``
            is called on it.
        descend_into: If set, an attribute is only recursed into when this
            returns true.

    Returns:
        The matching bound methods in ``dir()`` order.

    """
    found: list[types.MethodType] = []
    for name in dir(base):
        if name.startswith("__"):
            continue
        if name_filter is not None and not name_filter(name):
            continue
        try:
            attr = getattr(base, name)
        except AttributeError:
            continue
        if isinstance(attr, types.MethodType) and predicate(attr):
            found.append(attr)
        elif recurse and (descend_into is None or descend_into(attr)):
            found.extend(find_methods(attr, predicate, recurse=False, name_filter=name_filter))
    return found
