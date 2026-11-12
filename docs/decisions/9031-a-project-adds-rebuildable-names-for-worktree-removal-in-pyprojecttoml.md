---
title: "ADR-9031: A project adds rebuildable names for worktree removal in pyproject.toml"
description: doit pr_merge reads extra rebuildable names from [tool.pyproject-template.worktree] in the main checkout's pyproject.toml, rejecting over-broad names
date: 2026-11-09
audience:
  - contributors
tags:
  - adr
---

# ADR-9031: A project adds rebuildable names for worktree removal in pyproject.toml

## Status

Accepted

## Decision

1. **A project adds rebuildable names in its own `pyproject.toml`.** `doit pr_merge` reads `[tool.pyproject-template.worktree].rebuildable`, a list of names, from the main checkout's `pyproject.toml` and adds them to the built-in rebuildable names. They match the same way: `fnmatch` on the last path component. A name can be added, never removed from the built-ins, and the mount check is unchanged.
2. **The namespace is `[tool.pyproject-template.<area>]`.** `[tool.doit]` belongs to pydoit, which turns unknown keys into global doit options, and a task parameter would add a per-run CLI flag for something that describes the project. A table the template owns has neither problem. This is the first project-level `[tool.*]` setting for `tools/doit/`; later ones go in the same place.
3. **Over-broad names are rejected.** A name that is not a non-empty string, holds `/` or `\`, is `.` or `..`, or `fnmatch`-matches `tmp`, `agents`, `checkpoints` or `.envrc.local` is refused. That catches `tmp`, `*`, `t*` and `.envrc*`. A mistake deletes local env files or notes for good (#863), and a documentation warning does not protect a project that never reads it.
4. **A malformed setting keeps the worktree.** Bad TOML, a non-table, a non-list or a rejected name raises `ValueError` naming the file and key. `remove_merged_worktree` catches it, prints it with the manual removal commands, and removes nothing. No file, table or key means no extra names.

## Rationale

The built-in list covers what the template's own tooling rebuilds. A project has its own: an app home directory holding logs or caches under `tmp/` kept the worktree even though a run recreates it (#1238). Editing `_REBUILDABLE_IGNORED` in a downstream copy of `tools/doit/` would conflict on every template sync, so the project states them in its own configuration.

The main checkout's file is read, not the worktree's, so the branch being merged cannot widen what gets deleted.

## Consequences

- A project that sets the list is responsible for the names being rebuildable; the protected names are the only guard.
- The setting is read once per merge and passed down as an argument, with no global state.
- `[tool.pyproject-template.*]` is now where project-level settings for `tools/doit/` go.

## Documentation

- [doit tasks reference — pr_merge](../development/doit-tasks-reference.md#pr_merge)
- [ADR-9022](9022-worktrees-live-in-worktrees-each-with-its-own-environment.md)

Issue: #1238.
