---
title: "ADR-0014: Plugins add sqldb databases through database.add with plain-data definitions"
description: A plugin gets a sqldb database from plugins.core.sqldb:database.add with dicts for tables and migrations, instead of subclassing Sqldb and calling postinit.
date: 2026-11-20
audience:
  - contributors
tags:
  - adr
---

# ADR-0014: Plugins add sqldb databases through database.add with plain-data definitions

## Status

Accepted

## Context

A plugin needed a database through `plugins.core.sqldb:baseclass.get`: it subclassed `Sqldb`, added tables in `__init__` and called `postinit()`. The class had to be built inside a function because the sqldb plugin can reload, a plugin could leave out `postinit()`, two plugins naming a database `stats` shared a file by default, and nothing registered the database's APIs or commands in a defined way. Issue #597 replaces the pattern.

## Decision

- `plugins.core.sqldb:database.add(owner_id, name, tables=(), *, version=1, migrations=None, directory=None)` returns a ready `Sqldb`: tables are created and migrations applied, with no `postinit()` from the plugin. The action word is `add` because ADR-0004's closed action list has no `create`.
- Definitions are plain dicts, not TypedDicts or dataclasses. `bastproxy.plugins.core.sqldb.libs` belongs to the sqldb plugin package, which the loader drops from `sys.modules` on unload and reload, and plugins never import other plugins. API calls are untyped, so a TypedDict would add no caller-side checking. The factory validates at runtime and raises `ValueError` for unknown or missing keys, wrong types, duplicate tables, bad names and migration gaps, before any file is made.
- A migration step is a SQL script string, run with `modifyscript`, or a callable taking the database. Table `precreate` and `postcreate` hooks also take the database.
- The default directory is the owner's plugin data directory, so two plugins can name a database `stats`.
- The factory registers the database's `{name}.*` APIs and its `db*` commands under the owner, and tracks it so the owner's unload closes it. Owners declare `PLUGIN_DEPENDENCIES = ["plugins.core.sqldb"]`, so a sqldb reload re-adds their databases.
- `baseclass.get` and subclassing keep working and emit a `DeprecationWarning`.
- Known limitation: the `db*` command names are fixed, so a second database in one plugin replaces the first one's commands. Its `{name}.*` APIs do not collide. Issue #603 tracks it.

## Rationale

One call that takes data cannot forget `postinit()`, needs no subclass-in-a-function workaround, validates before touching disk, and gives every database the same registered APIs and cleanup.

## Related Issues

- Issue #597: Add a sqldb factory API that replaces the dbcreate subclass pattern
- Issue #603: let the sqldb `db*` commands serve more than one database per plugin
- ADR-0004 (API naming grammar)

## Related Documentation

- [Plugin developer guide: Storing data in SQLite](../plugin-developer-guide.md#storing-data-in-sqlite)
