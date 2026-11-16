# Project: bastproxy
# Filename: libs/plugins/pluginid.py
#
# File Description: the PluginId value type
#
# By: Bast
"""The ``PluginId`` value type (issue #436).

A plugin ID is a dotted string such as ``plugins.core.commands``. ``PluginId`` is a
``str`` subclass, so it compares, hashes, serializes and formats exactly like the
plain string, and adds the ``package`` and ``plugin`` parts as properties.

``PluginIdMatch`` (in ``loader.py``) is a different thing: a fuzzy-match result
whose fields may be empty, and whose ``plugin`` field holds a full plugin ID.
"""

from __future__ import annotations


class PluginId(str):
    """A validated plugin ID: ``<package>.<plugin>``.

    ``package`` is everything before the last ``.`` and ``plugin`` is everything
    after it. For ``plugins.core.commands`` the package is ``plugins.core`` and the
    plugin is ``commands``.
    """

    __slots__ = ()

    def __new__(cls, value: object) -> PluginId:
        """Create a plugin ID.

        Args:
            value: The dotted plugin ID.

        Raises:
            TypeError: If ``value`` is not a ``str``.
            ValueError: If ``value`` has no ``.`` or an empty package or plugin part.

        """
        if not isinstance(value, str):
            msg = f"plugin id must be a str, not {type(value).__name__}"
            raise TypeError(msg)
        package, sep, plugin = value.rpartition(".")
        if not sep or not package or not plugin:
            msg = f"invalid plugin id {value!r}: expected '<package>.<plugin>'"
            raise ValueError(msg)
        return super().__new__(cls, value)

    @classmethod
    def from_parts(cls, package: str, plugin: str) -> PluginId:
        """Build a plugin ID from its package and plugin parts."""
        return cls(f"{package}.{plugin}")

    @property
    def package(self) -> str:
        """The package: everything before the last ``.``."""
        return self.rpartition(".")[0]

    @property
    def plugin(self) -> str:
        """The plugin name: everything after the last ``.``."""
        return self.rpartition(".")[2]
