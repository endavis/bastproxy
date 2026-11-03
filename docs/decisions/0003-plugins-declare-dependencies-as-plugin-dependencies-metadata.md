---
title: "ADR-0003: Plugins declare dependencies as PLUGIN_DEPENDENCIES metadata"
description: Plugins declare dependencies as PLUGIN_DEPENDENCIES package metadata read before import; the loader loads and reloads in dependency order and the dependency.add API is removed.
date: 2026-11-03
audience:
  - contributors
tags:
  - adr
---

# ADR-0003: Plugins declare dependencies as PLUGIN_DEPENDENCIES metadata

## Status

Accepted

## Context

Plugin dependencies were declared at runtime through the `dependency.add` API and stored on `BasePlugin.dependencies`, but nothing read them. `PluginDependencyResolver` was never used, load order came only from the core-first startup sequence, and `reload_dependents_f` was never checked. The loader needs a plugin's dependencies before it instantiates the plugin, and `dependency.add` only runs inside an instance.

## Decision

- Plugins declare dependencies as package metadata in `__init__.py`: `PLUGIN_DEPENDENCIES = ["plugins.core.ssc"]`, a list or tuple of full plugin IDs.
- The loader reads the value with `ast.literal_eval` before importing the plugin (no plugin code runs) and stores it on `PluginInfo.dependencies`. An invalid value gives no dependencies and an `import_errors` entry.
- `load.plugins` pulls in unloaded dependencies and imports, instantiates and initializes in dependency order. A missing, circular or failing dependency fails the dependent with a logged error. `exit_on_error` behavior is unchanged.
- `reload.plugin` also reloads the loaded dependents of a plugin whose `reload_dependents_f` is set, all or nothing on `can_reload_f`.
- The `dependency.add` API and `BasePlugin.dependencies` are removed. This is a breaking change for plugins that called `dependency.add`: declare `PLUGIN_DEPENDENCIES` instead.
- Blocking the unload of a plugin that others depend on is out of scope.

## Rationale

- Metadata read before import is the only place the loader can learn dependencies in time, and it matches `PLUGIN_NAME` and the other declarations.
- `ast.literal_eval` never executes code and is independent of the line-based metadata parser.
- Keeping the three load phases but running each in resolved order means a dependency's `initialize()` always runs before its dependent's.

## Related Issues

- Issue #97: Plugin dependencies are declared but never resolved or used on reload
- Decision: https://github.com/endavis/bastproxy/issues/97#issuecomment-6592021871

## Related Documentation

- [Plugin system: Dependencies](../claude/plugin_system.md#dependencies): declaring, resolving and reloading with dependents
