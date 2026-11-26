---
title: "ADR-0024: Plugins add commands under another plugin's name only when that plugin accepts them"
description: A plugin may add commands under another plugin's name through command.add.for.plugin, only when the host sets accepts_command_extensions_f.
date: 2026-11-26
audience:
  - contributors
tags:
  - adr
---

# ADR-0024: Plugins add commands under another plugin's name only when that plugin accepts them

## Status

Accepted

## Context

Issue #834: the Aardwolf mapper adapter registers its commands under `#bp.aardwolf.mapper.*`, while the mapper's own commands live under `#bp.client.mapper.*` ([ADR-0021](0021-the-mapper-owns-the-map-and-walking-and-game-plugins-adapt-it-through-callbacks.md)). A user has to know which of the two plugins holds a command. A command has always sat under the plugin whose code runs it, so `CommandClass.plugin_id` meant both "where it lives" and "whose code it is".

## Decision

- **A general core API.** `plugins.core.commands:command.add.for.plugin(host_id, func)` adds a bound `_command_` method under another plugin's name. The owner is taken from `func.__self__.plugin_id`, as in `command.add.by.func`, so a caller cannot claim a different owner. There is no mapper-only wrapper.
- **The host opts in.** `BasePlugin.accepts_command_extensions_f` is False by default and the mapper sets it to True. The call is refused and logged when the host is not loaded, has not opted in, or is the owner.
- **Host and owner are separate.** `CommandClass.plugin_id` stays the host: it drives `full_cmd`, `prog`, storage and lookup. `CommandClass.owner_id` defaults to `plugin_id` and is the plugin whose function runs. It drives the log targets, the tracking actor, the `CmdArgsRecord` owner and the command's `api` owner, so the adapter's `self`, settings and logging stay its own.
- **Help.** An extension's group is forced to the owner id, so the host's help lists it in a section named after the owner. Its parser epilog reads `Added by <owner>`, and the `detail` command shows an `Owner` row when the owner differs. An extension is never the host's default command.
- **Clashes.** A name the host already has under a different owner is refused with a WARNING naming both owners. The same owner adding the same name replaces it.
- **Reload and unload.** The commands plugin keeps a registry of accepted extensions (host, name, owner, function), saved across its own reload. A host reload re-adds them, and the host's own commands win a clash. An owner unload removes its commands from every host and keeps their counts and error stats for a re-add.
- **Old names stay.** The adapter's methods keep `autoadd=True`, so they still register under its own namespace as well. Deprecating those names belongs to the adapter's own follow-up.

## Rationale

Splitting host from owner changes only the places that mean one or the other, and a command with no owner argument behaves as before. A flag on the host keeps the mapper game-neutral ([ADR-0021](0021-the-mapper-owns-the-map-and-walking-and-game-plugins-adapt-it-through-callbacks.md)): it never names a game plugin. A registry in the commands plugin lets reloads and unloads of either side stay consistent without either plugin knowing the other's lifecycle.

## Alternatives Considered

- **A mapper-only API.** Rejected: it would need the same core hooks for help, unload and reload, so it only adds a layer.
- **An explicit owner argument.** Rejected: it could disagree with the function's plugin.
- **An allow-list in the host.** Rejected: the mapper would have to name game plugins.
- **Running the command under the host's id.** Rejected: the adapter's logging, tracking actor and error attribution would point at the mapper.
- **Client aliases or a help cross-reference.** Rejected: they do not put the command under the host's name.

## Consequences

- Every command carries an `owner_id`, equal to its `plugin_id` unless it is an extension.
- A command can show up in the host's list while its code and errors belong to another plugin.
- The `ev_plugins.core.commands_args_modify` event args do not carry the owner.

## Related Issues

- Issue #834: let a game adapter add its commands under the core mapper's namespace

## Related Documentation

- [Command system: Commands Added Under Another Plugin](../claude/command_system.md#commands-added-under-another-plugin-834)
- [Mapper system](../claude/mapper_system.md)
- [ADR-0021](0021-the-mapper-owns-the-map-and-walking-and-game-plugins-adapt-it-through-callbacks.md)
