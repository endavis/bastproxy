---
title: "ADR-0002: User plugins load from BASTPROXY_HOME/plugins under the userplugins import root"
description: User plugins live in BASTPROXY_HOME/plugins, import as userplugins.<package>.<plugin>, share the plugins.<package>.<plugin> ID namespace, and cannot join bundled packages.
date: 2026-11-02
audience:
  - contributors
tags:
  - adr
  - plugins
---

# ADR-0002: User plugins load from BASTPROXY_HOME/plugins under the userplugins import root

## Status

Accepted

## Context

The loader's user search path was `BASTPROXY_HOME/data/plugins` with import prefix `plugins.`. That folder is also the plugins' data directory, and a plugin tree there could never be imported: the top-level `plugins` package only resolved to the bundled tree through a namespace shim, a top-level `plugins` package next to `src/bastproxy`, and the user folder was not on any import path. Issue #95 split the import location from the plugin ID, which makes a user location with its own import root possible.

## Decision

- User plugins load from `BASTPROXY_HOME/plugins`, separate from the data folder `BASTPROXY_HOME/data/plugins`. The folder is created at startup.
- The folder is registered as the import root `userplugins` by placing a synthetic package module in `sys.modules` (`imputils.register_import_root`). Nothing is added to `sys.path`.
- A user plugin at `plugins/<package>/<plugin>` imports as `userplugins.<package>.<plugin>` and has the plugin ID `plugins.<package>.<plugin>`, the same ID namespace as bundled plugins, so commands, data directories and ID lookups need no change.
- Bundled plugins are searched first. A user plugin whose package matches a bundled package (`core`, `debug`, `test`, ...) is refused with an error log, and the bundled plugin is kept.
- User plugins are two levels deep, `<package>/<plugin>`, like bundled plugins.
- The top-level `plugins` import package (the shim) is removed. This is a breaking change. Migration: change `plugins.` imports to `bastproxy.plugins.`, for example `from bastproxy.plugins._baseplugin import BasePlugin`.

## Rationale

- A folder of its own keeps user code apart from plugin data.
- A synthetic module is the least invasive import mechanism: one `sys.modules` key, no `sys.path` edit, no finder.
- Sharing the `plugins.` ID namespace avoids reworking every consumer that assumes `plugins.<package>.<plugin>`. The cost is possible collisions, which are refused so a user plugin cannot silently join `plugins.core` and become required.
- With the user path no longer using the `plugins.` import prefix, the shim served only one internal caller, which is fixed to import from the plugin's real package location.

## Related Issues

- Issue #110: The user-plugin search path can never load a plugin
- Issue #95: Import plugins under their real package name only

## Related Documentation

- [Plugin system: User Plugins](../claude/plugin_system.md#user-plugins): folder, layout, import root against ID, collision rule
