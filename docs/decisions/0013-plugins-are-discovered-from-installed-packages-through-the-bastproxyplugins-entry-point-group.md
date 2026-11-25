---
title: "ADR-0013: Plugins are discovered from installed packages through the bastproxy.plugins entry-point group"
description: Installed packages register plugins in the bastproxy.plugins entry-point group; the entry name sets the plugin ID, and bundled beats user beats installed.
date: 2026-11-19
audience:
  - contributors
tags:
  - adr
---

# ADR-0013: Plugins are discovered from installed packages through the bastproxy.plugins entry-point group

## Status

Accepted

## Context

Plugins load from the bundled tree and from `$BASTPROXY_HOME/plugins` (ADR-0002). A plugin package kept in its own repository has to be symlinked or copied into the user folder, where it runs in bastproxy's environment without its own dependencies and is not versioned by its package manager. Issue #579 asks for discovery of installed packages.

## Decision

- A package registers in the `bastproxy.plugins` entry-point group with `name = "package"`. The name must be a valid identifier. The loader reads the group from its own environment, imports each package and adds one search path per entry with source `installed`: the package directory, import prefix `<module>.`, and ID prefix `plugins.<name>.`.
- The entry name, not the module name, sets the package part of the plugin ID, so `bastproxy_aardwolf/connect` under the name `aardwolf` is `plugins.aardwolf.connect`, the same ID as a user-folder copy at `aardwolf/connect`.
- Precedence is bundled, then user, then installed. Collisions are decided per plugin ID: installed against bundled is refused with an error log; installed against user lets the user copy win with a warning; installed against installed lets the first entry name in sort order win with an error.
- A broken entry (name not an identifier, import fails, or the target is not a regular package) is logged as an error and skipped. Startup continues.
- The package must be installed in the same environment as bastproxy.

## Rationale

- Entry points are the standard way for an installed package to advertise itself to another, and they need no configuration file in bastproxy.
- Keeping the `plugins.` ID namespace means commands, data directories and ID lookups need no change.
- Letting the user folder override an installed plugin allows local patches without uninstalling. The warning keeps the override visible.
- Skipping a broken entry keeps one bad package from stopping the proxy.

Note (#824): a user folder whose name matches an installed entry (its name or its import name) stays under the `userplugins` import root, so this per-plugin override is unchanged. See [ADR-0023](0023-user-plugin-packages-import-under-their-own-name.md).

## Related Issues

- Issue #579: Discover plugins from installed packages through entry points
- Issue #110: The user-plugin search path can never load a plugin
- Issue #824: Import each user plugin package under its own name

## Related Documentation

- [Plugin system: Installed Plugin Packages](../claude/plugin_system.md#installed-plugin-packages): entry-point group, ID rule, precedence and collisions
- [Plugin developer guide: Packaging plugins](../plugin-developer-guide.md#packaging-plugins): layout, entry-point snippet and development workflow
