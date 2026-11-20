---
title: "ADR-0015: Settings are keyed per plugin and a name index resolves pset"
description: Settings are keyed by plugin and name, so plugins may reuse a name, and a name index resolves a bare pset only when one plugin owns the name.
date: 2026-11-20
audience:
  - contributors
tags:
  - adr
---

# ADR-0015: Settings are keyed per plugin and a name index resolves pset

## Status

Accepted

## Context

Setting values and info were already stored per plugin, but `SettingsPlugin.settings_map` mapped a visible setting name to the one plugin that owned it. When a second plugin added a visible setting with a name already in the map, `setting.add` logged an error and returned before storing anything: `setting.get` returned `None` for that setting and the plugin ran on a missing value. `pset <name>` resolved the plugin through the same map, so the second plugin's setting could not be reached either. Plugins outside core are likely to reuse names such as `enabled`. Issue #609 removes the shared namespace.

## Decision

- Settings are keyed by `(plugin_id, setting_name)` everywhere. `settings_map` stays only as a name index, `dict[str, list[str]]`, listing each visible name's owners in add order. Hidden settings are not indexed.
- `setting.add` never refuses a name another plugin uses. It appends the plugin to the name's owners, without duplicates.
- `setting.map.add` keeps its signature and now appends the owner the same way instead of logging an error and refusing on a conflict. This is a behaviour change, not a breaking one: nothing in the project calls it.
- `setting.remove.for.plugin` removes only the unloading plugin from each name's owners and drops a name when no owner is left.
- `setting.set.from.user` keeps its signature. A name no plugin owns is reported as not existing. With `plugin_id` given (`pset -p <plugin> <name>` and every plugin's own `set` command), it acts on that plugin's setting only. With `plugin_id` empty, a name with one owner resolves as before, and a name with several owners lists them, asks for `-p <plugin>` and changes nothing, also for `--default`.
- `settings list` is unchanged; it already shows each plugin's settings.

## Rationale

The data was already per plugin, so only the name index had to change. Resolving a bare `pset <name>` to a single owner keeps the common case working, and refusing an ambiguous name is safer than choosing an owner. The alternative of prefixing names with the plugin id was rejected: it would rename every setting, its stored key and its `ev_<plugin>_var_<name>_modified` event.

## Related Issues

- Issue #609: give each plugin its own setting names

## Related Documentation

- [Settings system](../claude/settings_system.md)
