---
title: "ADR-0023: User plugin packages import under their own name"
description: Each user plugin package folder imports under its own name, unless the name is unusable, installed or already importable.
date: 2026-11-25
audience:
  - contributors
tags:
  - adr
---

# ADR-0023: User plugin packages import under their own name

## Status

Accepted. Supersedes the import-root bullet of [ADR-0002](0002-user-plugins-load-from-bastproxy-homeplugins-under-the-userplugins-import-root.md). The per-plugin user-over-installed rule of [ADR-0013](0013-plugins-are-discovered-from-installed-packages-through-the-bastproxyplugins-entry-point-group.md) is unchanged.

## Context

Every user package imported as `userplugins.<package>`, so a package's own absolute imports (`from mine._libs import x`) failed: the package was not importable as `mine`. Patching an installed package by copying it into `$BASTPROXY_HOME/plugins` hit the same wall. Issue #824.

## Decision

Each top-level package folder in `$BASTPROXY_HOME/plugins` that holds an `__init__.py` takes one of three routes:

1. **Own name.** The folder is registered in `sys.modules` under its own name (`imputils.register_package_root`). Its own `__init__.py` runs, nothing is added to `sys.path` and no meta-path finder is installed. The plugin imports as `<package>.<plugin>`. Plugin IDs stay `plugins.<package>.<plugin>`.
2. **userplugins.** The folder stays under the synthetic `userplugins` root, as before. This applies when the name is not an identifier or is a keyword, when the folder's own `__init__.py` is itself a plugin, when `bastproxy.plugins.<name>` is a bundled package (the per-plugin bundled-collision refusal of ADR-0002 still fires), and when the name matches an installed entry point.
3. **Refused.** The name is already importable (stdlib or third-party), so registering it would shadow that module. The folder is skipped with an error log naming the name and where it resolves.

The installed-name match checks both the entry-point name, which sets the plugin-ID package, and the top-level import name of the entry-point value, which is what the folder would shadow. A folder named like the entry name keeps ADR-0013's per-plugin override and its warning. A folder named like the import name falls back to `userplugins`, so its own-name imports resolve to the installed package and a `plugins/<pkg>/<plugin>` patch keeps working.

A module this loader registered carries the marker attribute `__bastproxy_user_package__` (the folder path). Discovery reruns on every `plugin.list.not.loaded` call; the marker lets a rerun reuse the registration instead of refusing it as an importable name.

Folders without `__init__.py` (namespace style) stay ignored, as before: `pkgutil.walk_packages` never yielded them. Requiring `__init__.py` is kept on purpose.

Each user folder is scanned on its own, because scanning the whole directory would also import every own-name folder as `userplugins.<name>`, running its `__init__` twice under two names.

Breaking change: plugins in own-name folders import as `<package>.<plugin>`, not `userplugins.<package>.<plugin>`. Migration: change `userplugins.<pkg>...` imports to `<pkg>...`.

## Rationale

- A package's own absolute imports work without any `sys.path` edit or finder, so the change stays as small as ADR-0002's synthetic root.
- Refusing importable names protects stdlib and third-party modules from being shadowed by a stray folder.
- Falling back to `userplugins` for installed names keeps ADR-0013's override working and keeps the installed package's modules in charge.

## Alternatives Considered

- Appending the user directory to `sys.path`: any folder would then shadow stdlib and installed modules, and the whole directory becomes an import root.
- Grafting the user directory into `bastproxy.plugins.__path__`: user code would share the bundled namespace and the bundled-collision rules would stop being enforceable by name.
- Accepting namespace-style folders without `__init__.py`: they never worked, and there is no module to run or mark.

## Related Issues

- Issue #824: Import each user plugin package under its own name
- Issue #110: The user-plugin search path can never load a plugin
- Issue #579: Discover plugins from installed packages through entry points

## Related Documentation

- [Plugin system: User Plugins](../claude/plugin_system.md#user-plugins)
