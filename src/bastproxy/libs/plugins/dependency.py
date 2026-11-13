# Project: bastproxy
# Filename: libs/plugins/dependency.py
#
# File Description: class to resolve plugin dependencies
#
# By: Bast
"""Module for resolving plugin dependencies in the bastproxy project.

Plugins declare their dependencies in the package ``__init__.py`` as
``PLUGIN_DEPENDENCIES = ["plugins.core.ssc"]``; the list is stored on
``PluginInfo.dependencies``. This module orders plugins so dependencies come first
and finds the plugins that depend on a given plugin.

The resolver is pure: it does no logging and never exits. Callers log the failures
it returns.

Classes:
    - `DependencyResolution`: the load order and failures `resolve` returns.
    - `PluginDependencyResolver`: orders plugins and finds dependents.
    - `CircularDependencyError`: a dependency cycle, carrying the cycle path.

"""

# Standard Library
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# 3rd Party
# Project
from bastproxy.libs.exceptions import PluginDependencyError

if TYPE_CHECKING:
    from bastproxy.libs.plugins.plugininfo import PluginInfo


class CircularDependencyError(PluginDependencyError):
    """Exception raised when a circular dependency is detected."""

    def __init__(self, cycle: list[str]) -> None:
        """Store the cycle path (first and last entries are the same plugin)."""
        self.cycle = cycle
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle)}")


@dataclass(slots=True)
class DependencyResolution:
    """The outcome of resolving plugin dependencies.

    Attributes:
        order: The plugins that can be loaded, in load order.
        failed: Each failed plugin mapped to the error explaining why.

    """

    order: list[str] = field(default_factory=list)
    failed: dict[str, PluginDependencyError] = field(default_factory=dict)


class PluginDependencyResolver:
    """Resolve plugin dependencies against a set of ``PluginInfo`` objects."""

    def __init__(
        self,
        plugins_info: Mapping[str, "PluginInfo"],
        loaded: Iterable[str] | None = None,
    ) -> None:
        """Initialize the resolver.

        Args:
            plugins_info: Every known plugin, by plugin ID.
            loaded: Plugin IDs that are already loaded; they satisfy a dependency
                and are never added to an order.

        """
        self.plugins_info = plugins_info
        self.loaded: set[str] = set(loaded or [])

    def resolve(self, plugin_ids: Iterable[str]) -> DependencyResolution:
        """Order plugins so that dependencies come before their dependents.

        Dependencies that are not in ``plugin_ids`` and not loaded are pulled into
        the order. Otherwise the input order is kept. A plugin with a missing,
        circular or failing dependency fails, and so does everything depending on it.

        Args:
            plugin_ids: The plugin IDs to order.

        Returns:
            A `DependencyResolution`: ``order`` holds the plugins that can be loaded,
            in load order, and ``failed`` maps each failed plugin to the error
            explaining why.

        """
        result = DependencyResolution()
        order = result.order
        failed = result.failed
        done: set[str] = set()
        stack: list[str] = []

        def visit(plugin_id: str) -> bool:
            if plugin_id in self.loaded:
                return True
            if plugin_id in done:
                return plugin_id not in failed
            if plugin_id in stack:
                cycle = [*stack[stack.index(plugin_id) :], plugin_id]
                error = CircularDependencyError(cycle)
                for member in cycle[:-1]:
                    failed[member] = error
                return False
            if plugin_id not in self.plugins_info:
                failed[plugin_id] = PluginDependencyError(f"plugin {plugin_id} does not exist")
                done.add(plugin_id)
                return False

            stack.append(plugin_id)
            bad: list[str] = []
            for dependency in self.plugins_info[plugin_id].dependencies:
                if not visit(dependency):
                    bad.append(dependency)
            stack.pop()
            done.add(plugin_id)

            if bad:
                failed.setdefault(
                    plugin_id,
                    PluginDependencyError(
                        f"{plugin_id} depends on {', '.join(bad)}, which could not be loaded"
                    ),
                )
                return False
            order.append(plugin_id)
            return True

        for plugin_id in plugin_ids:
            visit(plugin_id)

        return result

    def dependents_of(self, plugin_id: str, candidates: Iterable[str]) -> list[str]:
        """Return the plugins among ``candidates`` that depend on ``plugin_id``.

        The result is the transitive closure, nearest dependents first. It never
        includes ``plugin_id`` itself.

        Args:
            plugin_id: The plugin whose dependents to find.
            candidates: The plugin IDs to search (for example the loaded plugins).

        """
        candidate_list = [c for c in candidates if c in self.plugins_info]
        found: list[str] = []
        frontier = [plugin_id]
        while frontier:
            next_frontier: list[str] = []
            for target in frontier:
                for candidate in candidate_list:
                    if (
                        candidate != plugin_id
                        and candidate not in found
                        and target in self.plugins_info[candidate].dependencies
                    ):
                        found.append(candidate)
                        next_frontier.append(candidate)
            frontier = next_frontier
        return found
