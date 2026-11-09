# Project: bastproxy
# Filename: libs/api/_builtins.py
#
# File Description: the libs.api built-in APIs every API object offers
#
# By: Bast
"""The ``libs.api:`` built-in APIs, resolved from a fixed table (issue #199).

Every ``API`` object offers the same 14 ``libs.api:`` names, and every record builds an
``API``. Building 14 ``APIItem`` objects and binding 14 methods for each object cost about
7.5 microseconds and 5 KB, so the names live in one class-level table instead
(``BUILTIN_APIS``). An object binds a method and builds its ``APIItem`` only when the name
is first resolved, and keeps it for the next call.

``InstanceAPIs`` is the mapping behind ``API._instance_api``. It behaves like the dict it
replaced, so everything that lists, tests or removes APIs sees the built-ins without
knowing about the table.

Classes:
    - `InstanceAPIs`: the per-object instance APIs, with the built-ins resolved lazily.

"""

from collections.abc import Callable, Iterator, MutableMapping
from typing import TYPE_CHECKING

from ._apiitem import APIItem
from ._functools import stackdump

if TYPE_CHECKING:
    from ._api import API

BUILTIN_TOPLEVEL = "libs.api"

# name -> (method name on API, or None for the stackdump function, description)
_BUILTIN_SPECS: tuple[tuple[str, str | None, str], ...] = (
    ("api.add", "add", "add a function to the api"),
    ("api.exists", "_api_api_exists", "check to see if something exists in the api"),
    ("api.add.for.object", "_api_api_add_for_object", "add apis for an object"),
    ("api.toplevel.remove", "_api_api_toplevel_remove", "remove a toplevel api"),
    (
        "api.list.in.toplevel",
        "_api_api_list_in_toplevel",
        "return a list of apis in a toplevel api",
    ),
    ("api.detail.get", "_api_api_detail_get", "return the detail of an api function"),
    (
        "api.list.formatted",
        "_api_api_list_formatted",
        "return a formatted list of functions in an api",
    ),
    ("data.list", "_api_data_list", "return a dict of api data"),
    ("data.get", "_api_data_get", "return the data for an api"),
    (
        "function.owner.get",
        "_api_function_owner_get",
        "get the plugin_id of the plugin that owns the function",
    ),
    ("caller.owner.get", "_api_caller_owner_get", "get the plugin on the top of the frame stack"),
    ("character.is.active", "_api_character_is_active", "returns the is_character_active flag"),
    ("character.active.set", "_api_character_active_set", "set the is_character_active flag"),
    ("stack.dump", None, "return a stackdump"),
)

# full api name -> (method name on API, or None for the stackdump function, description)
BUILTIN_APIS: dict[str, tuple[str | None, str]] = {
    f"{BUILTIN_TOPLEVEL}:{name}": (method, description)
    for name, method, description in _BUILTIN_SPECS
}


class InstanceAPIs(MutableMapping[str, APIItem]):
    """The instance APIs of one ``API`` object, with the ``libs.api:`` built-ins lazy.

    A built-in is bound to the owning ``API`` and wrapped in an ``APIItem`` the first time
    it is read. Setting a name stores it as before, so an override replaces a built-in.
    Deleting a built-in hides it from this object only.
    """

    __slots__ = ("_hidden", "_items", "_owner")

    def __init__(self, owner: "API") -> None:
        """Create the mapping for ``owner``; nothing is bound yet.

        Args:
            owner: The ``API`` object the built-ins are bound to.

        """
        self._owner = owner
        self._items: dict[str, APIItem] = {}
        self._hidden: set[str] | None = None

    def _bind(self, key: str) -> APIItem:
        """Bind a built-in to the owner, store its ``APIItem`` and return it."""
        method, description = BUILTIN_APIS[key]
        tfunction: Callable[..., object] = (
            stackdump if method is None else getattr(self._owner, method)
        )
        item = APIItem(key, tfunction, self._owner.owner_id, description=description)
        item.instance = True
        self._items[key] = item
        return item

    def __getitem__(self, key: str) -> APIItem:
        """Return the item for ``key``, binding a built-in on first use."""
        item = self._items.get(key)
        if item is not None:
            return item
        if key in BUILTIN_APIS and not (self._hidden and key in self._hidden):
            return self._bind(key)
        raise KeyError(key)

    def __setitem__(self, key: str, value: APIItem) -> None:
        """Store ``value`` under ``key``."""
        self._items[key] = value
        if self._hidden:
            self._hidden.discard(key)

    def __delitem__(self, key: str) -> None:
        """Remove ``key``; a built-in is hidden for this object."""
        in_items = key in self._items
        visible_builtin = key in BUILTIN_APIS and not (self._hidden and key in self._hidden)
        if not in_items and not visible_builtin:
            raise KeyError(key)
        self._items.pop(key, None)
        if key in BUILTIN_APIS:
            if self._hidden is None:
                self._hidden = set()
            self._hidden.add(key)

    def __contains__(self, key: object) -> bool:
        """Return whether ``key`` is stored or is a visible built-in."""
        if key in self._items:
            return True
        return key in BUILTIN_APIS and not (self._hidden and key in self._hidden)

    def __iter__(self) -> Iterator[str]:
        """Iterate over the stored keys, then the built-ins not yet bound."""
        hidden = self._hidden
        keys = list(self._items)
        keys.extend(
            k for k in BUILTIN_APIS if k not in self._items and not (hidden and k in hidden)
        )
        return iter(keys)

    def __len__(self) -> int:
        """Return the number of stored keys plus the visible built-ins not yet bound."""
        hidden = self._hidden
        unbound = sum(
            1 for k in BUILTIN_APIS if k not in self._items and not (hidden and k in hidden)
        )
        return len(self._items) + unbound
