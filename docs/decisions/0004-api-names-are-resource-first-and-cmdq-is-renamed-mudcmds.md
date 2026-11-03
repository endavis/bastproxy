---
title: "ADR-0004: API names are resource-first and cmdq is renamed mudcmds"
description: API names take the resource-first form resource.action.qualifier with is/has/exists booleans; plugins.core.cmdq becomes plugins.core.mudcmds; every rename lands at once as a breaking change with no aliases.
audience:
  - contributors
tags:
  - adr
  - api
---

# ADR-0004: API names are resource-first and cmdq is renamed mudcmds

## Status

Accepted

## Context

API names had no single rule. Names were verb-first (`get.plugin.info`), resource-first (`client.add`), domain-first (`colorcode.to.html`) or bare verbs (`add`, `reset`), and boolean checks used `is`, `has`, `does` and `can` with no pattern.

- **189 registrations**, measured on `8a12c75`: 173 `@AddAPI` decorators, 2 registered through `libs.api:add` (`libs.asynch:task.add` and `plugins.core.pluginm:save.all.plugins.state`), and 14 that `libs.api` registers on itself in `API.__init__`. One further `@AddAPI(` match is a docstring example in `src/bastproxy/libs/api/_addapi.py`, and the `libs.api:add` calls in the demo `test()` at the end of `src/bastproxy/libs/api/_api.py` are not real APIs, so both are excluded.
- **Forms**, hand-classified by first segment over the 175 names that are not `libs.api` self-registrations: 114 verb-first (`get.*` 43, 17 bare verbs), 49 resource-first, 12 boolean prefix (`is` 6, `can` 3, `has` 2, `does` 1).
- `libs.api` has no alias mechanism, so a renamed API breaks every caller at once.
- No code outside `plugins.core.cmdq` calls `plugins.core.cmdq:*`.
- `info/api_naming_analysis.md` recommended documenting the existing patterns and fixing only the confusing boolean checks. This ADR does not adopt that.

## Decision

The repo admin decided on 2026-11-03:

1. **Format: strict resource-first.** `<resource>.<action>[.<qualifier>]`, for example `timer.add`, `plugin.info.get`, `colorcode.to.html`.
2. **The resource is always named, including when it is the plugin itself.** No bare verbs: `plugins.core.settings:setting.add`.
3. **Booleans:** `<resource>.is.<state>`, `<resource>.has.<thing>`, and `<resource>.exists` for existence checks. No `can.*` or `does.*`.
4. **Misnamed APIs** are listed in the appendix with their new names (reason `misnamed`).
5. **`plugins.core.cmdq` is renamed to `plugins.core.mudcmds`.**
6. **Migration: all at once, as a breaking change.** Each rename PR carries a `BREAKING CHANGE:` footer and a migration table. There are no aliases. Before 1.0 this is a minor version bump.

### Naming grammar

**1. Shape.** A name is `<resource>.<action>[.<qualifier>]`.

- The resource is one or more dotted lowercase words.
- The action is exactly one word from the closed action list below.
- The qualifier is zero or more words.
- To parse a name, take the first segment that is an action word. Everything before it is the resource, which must be non-empty. Everything after it is the qualifier.

**2. Closed action list.** Adding a word means amending this ADR.

- add, remove, get, set, update, list, count
- toggle, start, finish, reset, clear, clean
- load, unload, reload, initialize, save
- register, unregister, raise, send, run, queue
- format, to, strip, escape, dump, center, cap, dedent, verify, match
- select, modify, shutdown, restart
- is, has, exists

No resource word may be an action word. `list`, `format` and `match` are never resources.

**3. Picking the resource.**

- The resource is the singular noun the action acts on or returns: `client.list`, not `clients.list`.
- When the API acts on the owning plugin itself (the BasePlugin APIs), the resource is `plugin` (`plugin.dump`, `plugin.reset`). The exception is when a more specific noun exists (`data.get`, `data.directory.get`).
- Inside a plugin namespace, use the plugin's domain noun. The plugin ID prefix already disambiguates across plugins, so `plugins.core.mudcmds:command.start` and `plugins.core.commands:command.run` can coexist.

**4. Multi-word resources.** A narrowing path, left to right: `client.banned` (the banned subset of clients), `output.header`, `command.current.args`, `plugin.file`. Do not introduce a separate noun like `ban` when the resource is a subset of an existing one.

**5. The qualifier modifies the action, never the object.** It says how, which, for whom or which variant.

- How: `add.by.ip`, `register.by.func`
- For whom: `for.plugin`, `for.owner`, `from.user`
- Filter: `list.loaded`, `list.in.package`
- Variant: `list.formatted`, `toggle.enable`, `raise.all`, `set.view.only`

A noun naming the thing acted on belongs in the resource. That is why `plugin.get.changed.files` becomes `plugin.file.list.changed`, `queue.add.command` becomes `command.queue`, and `{database_name}.get.single.row` becomes `{database_name}.row.get`. A test can check the shape; this rule is enforced in review.

**6. Getters, setters, collections.**

- `.get` returns one item or value.
- `.set` sets a value. `change` is not used: `setting.set`.
- `.update` partially updates an existing item.
- `.list` returns a collection. Unqualified, it means all; a filter goes in the qualifier. `.all` is not used as a resource or action.
- `.list.formatted` and `.format` return display lines.
- `.count` returns a number.
- The setter for a boolean state is `<resource>.<state>.set`, paired with the getter `<resource>.is.<state>`: `plugin.loaded.set` and `plugin.is.loaded`, `client.logged.in.set` and `client.is.logged.in`, `character.active.set` and `character.is.active`.

**7. Booleans.**

- `<resource>.is.<state>`, with at least one state word.
- `<resource>.has.<thing>`.
- `<resource>.exists` as the last segment for existence checks.
- No `can`, `does` or `check`.

**8. Conversions.** `<source>.to.<target>`: `colorcode.to.html`, `timedelta.to.string`, `timelength.to.seconds`.

**9. Bulk cleanup per owner.** `<resource>.remove.for.plugin` or `.for.owner`, matching what the argument is. Events use `event.unregister.for.owner`.

**10. Dynamic names.**

- The placeholder counts as one resource segment: `{database_name}.select`.
- `ssc.{name}` has no action, so it becomes `ssc.{name}.get`.
- A grammar test substitutes a dummy word before parsing.

**11. Names that already follow the grammar are unchanged**, unless they are listed as misnamed. This keeps churn down.

**12. One cross-plugin interface.** `debug/plugins` calls `{plugin}:get.summary.data.for.plugin` and `{plugin}:get.detailed.data.for.plugin` by name on any plugin. These become `summary.get.for.plugin` and `detail.get.for.plugin`, the same name in every plugin that provides them (commands, events).

## Rationale

- One predictable lookup: find the resource, then the verb.
- Listings group by resource, so related APIs sort together.
- A closed action list makes names machine-checkable.
- With no alias mechanism, one break is cheaper than a deprecation layer that would have to be built first.

## Consequences

- **Breaking for user plugins** under `BASTPROXY_HOME/plugins` that call or register APIs by name.
- Each rename PR carries a `BREAKING CHANGE:` footer and an old-to-new table copied from the appendix, and is a minor version bump before 1.0.
- **`plugins.core.settings` `_api_reset` overrides `BasePlugin._api_reset` by Python method name.** Renaming only the string would register the settings method under `plugin.reset`. The settings rename must also rename the method, for example to `_api_setting_reset`. After that, `plugins.core.settings:plugin.reset` exists for the first time.
- **`does.plugin.exist` and `is.plugin.id` have the same body** (a dict lookup in the loader). They keep separate names here; merging them is optional cleanup in the loader follow-up.
- **`plugins.core.pluginm:plugin.state.save` is the base API that saves pluginm itself.** `plugin.state.save.all` saves every plugin. The two read as similar, and the docs must say so.
- **Several descriptions are wrong**: `is.mud.connected` says "get the mud connection", and `has.event` says "return the event". The follow-ups may fix them alongside the names.
- `errors:get` returns all errors, so it becomes `error.list` by rule 6.
- Follow-up issues are filed from #99, one per plugin or small batch, plus one for the `cmdq` rename. The existing test in `tests/plugins/test_api_names_exist.py` catches missed callers in `src`.
- The grammar is a test, `tests/plugins/test_api_name_grammar.py`: a static scan of every registered API name against the closed action list and boolean forms. Names that do not conform yet are in its `LEGACY_NAMES` allowlist, keyed by owner and name, which may only shrink. Each rename PR removes its names from it. Rule 3 and 5 misnames that already parse are tagged `review` there.
- Renaming `plugins.core.cmdq` moves its package and tests, and changes the plugin ID. The follow-up checks whether it persists settings or data under its plugin ID and says how users migrate.

## Related Issues

- Issue #99: Decide the API and plugin naming convention
- Issue #160: ADR-0004 grammar test
- Decision: https://github.com/endavis/bastproxy/issues/99#issuecomment-6608133811

## Related Documentation

- [API system: API naming convention](../claude/api_system.md#1-api-naming-convention)
- [Plugin system](../claude/plugin_system.md)
- [CONTRIBUTING: API Naming Conventions](../../CONTRIBUTING.md#api-naming-conventions)
- [Superseded analysis](../../info/api_naming_analysis.md)

## Appendix: Rename table

Plugin rename:

| Current plugin ID | New plugin ID |
|---|---|
| plugins.core.cmdq | plugins.core.mudcmds |

API renames: 189 rows. Reason tags: 122 format (reordered to resource-first, or a bare verb given a resource), 14 boolean (boolean form), 13 misnamed (wrong meaning or shape), 40 unchanged. The tag counts were measured from this table.

| Owner | Current | New | Reason |
|---|---|---|---|
| libs.api | add | api.add | format |
| libs.api | has | api.exists | boolean |
| libs.api | add.apis.for.object | api.add.for.object | format |
| libs.api | remove | api.toplevel.remove | format |
| libs.api | get.children | api.list.in.toplevel | format |
| libs.api | detail | api.detail.get | format |
| libs.api | list | api.list.formatted | format |
| libs.api | list.data | data.list | format |
| libs.api | data.get | data.get | unchanged |
| libs.api | get.function.owner.plugin | function.owner.get | format |
| libs.api | get.caller.owner | caller.owner.get | format |
| libs.api | is.character.active | character.is.active | boolean |
| libs.api | is.character.active:set | character.active.set | format |
| libs.api | stackdump | stack.dump | format |
| libs.asynch | task.add | task.add | unchanged |
| libs.plugins.loader | get.unloaded.plugins.in.memory | plugin.module.list.stale | misnamed |
| libs.plugins.loader | get.not.loaded.plugins | plugin.list.not.loaded | misnamed |
| libs.plugins.loader | get.all.plugins | plugin.list | format |
| libs.plugins.loader | get.plugin.info | plugin.info.get | format |
| libs.plugins.loader | does.plugin.exist | plugin.exists | boolean |
| libs.plugins.loader | plugin.get.changed.files | plugin.file.list.changed | misnamed |
| libs.plugins.loader | plugin.get.invalid.python.files | plugin.file.list.invalid | misnamed |
| libs.plugins.loader | get.loaded.plugins.list | plugin.list.loaded | misnamed |
| libs.plugins.loader | get.packages.list | package.list | format |
| libs.plugins.loader | get.plugins.in.package | plugin.list.in.package | format |
| libs.plugins.loader | get.plugin.instance | plugin.instance.get | format |
| libs.plugins.loader | is.plugin.id | plugin.id.is.valid | boolean |
| libs.plugins.loader | is.plugin.loaded | plugin.is.loaded | boolean |
| libs.plugins.loader | is.plugin.instantiated | plugin.is.instantiated | boolean |
| libs.plugins.loader | load.plugins | plugin.load | format |
| libs.plugins.loader | reload.plugin | plugin.reload | format |
| libs.plugins.loader | set.plugin.is.loaded | plugin.loaded.set | format |
| libs.plugins.loader | unload.plugin | plugin.unload | format |
| libs.plugins.loader | fuzzy.match.plugin.id | plugin.id.match | format |
| libs.plugins.reloadutils | add.cache | cache.add | format |
| libs.plugins.reloadutils | get.plugin.cache | cache.get | format |
| libs.plugins.reloadutils | remove.plugin.cache | cache.remove | format |
| libs.timing | toggle | timing.toggle | format |
| libs.timing | start | timing.start | format |
| libs.timing | finish | timing.finish | format |
| every plugin (BasePlugin) | data.get | data.get | unchanged |
| every plugin (BasePlugin) | data.update | data.update | unchanged |
| every plugin (BasePlugin) | get.data.directory | data.directory.get | format |
| every plugin (BasePlugin) | set.reload | plugin.reloading.set | format |
| every plugin (BasePlugin) | get.plugin.hooks | plugin.hook.list | format |
| every plugin (BasePlugin) | dump | plugin.dump | format |
| every plugin (BasePlugin) | save.state | plugin.state.save | format |
| every plugin (BasePlugin) | reset | plugin.reset | format |
| plugins.core.clients | client.count | client.count | unchanged |
| plugins.core.clients | get.client | client.get | format |
| plugins.core.clients | send.to.client | client.send | format |
| plugins.core.clients | client.banned.add | client.banned.add | unchanged |
| plugins.core.clients | client.banned.add.by.ip | client.banned.add.by.ip | unchanged |
| plugins.core.clients | client.banned.check | client.is.banned | misnamed |
| plugins.core.clients | client.banned.remove | client.banned.remove | unchanged |
| plugins.core.clients | client.is.view.client | client.is.view.client | unchanged |
| plugins.core.clients | client.is.logged.in | client.is.logged.in | unchanged |
| plugins.core.clients | client.logged.in | client.logged.in.set | misnamed |
| plugins.core.clients | client.logged.in.view.only | client.logged.in.set.view.only | misnamed |
| plugins.core.clients | client.add | client.add | unchanged |
| plugins.core.clients | client.remove | client.remove | unchanged |
| plugins.core.clients | get.all.clients | client.list | format |
| plugins.core.clients | get.clients.formatted | client.list.formatted | format |
| plugins.core.cmdq → plugins.core.mudcmds | remove.mud.commands.for.plugin | type.remove.for.plugin | format |
| plugins.core.cmdq → plugins.core.mudcmds | type.remove | type.remove | unchanged |
| plugins.core.cmdq → plugins.core.mudcmds | start | command.start | format |
| plugins.core.cmdq → plugins.core.mudcmds | type.add | type.add | unchanged |
| plugins.core.cmdq → plugins.core.mudcmds | finish | command.finish | format |
| plugins.core.cmdq → plugins.core.mudcmds | queue.add.command | command.queue | misnamed |
| plugins.core.colors | colorcode.to.html | colorcode.to.html | unchanged |
| plugins.core.colors | color.length.difference | color.length.difference.get | misnamed |
| plugins.core.colors | colorcode.is.valid | colorcode.is.valid | unchanged |
| plugins.core.colors | colorcode.to.ansicode | colorcode.to.ansicode | unchanged |
| plugins.core.colors | colorcode.escape | colorcode.escape | unchanged |
| plugins.core.colors | ansicode.to.colorcode | ansicode.to.colorcode | unchanged |
| plugins.core.colors | ansicode.to.string | ansicode.to.string | unchanged |
| plugins.core.colors | ansicode.strip | ansicode.strip | unchanged |
| plugins.core.colors | colorcode.strip | colorcode.strip | unchanged |
| plugins.core.commands | get.command.indent | command.indent.get | format |
| plugins.core.commands | get.command.count | command.count | format |
| plugins.core.commands | get.output.indent | output.indent.get | format |
| plugins.core.commands | format.output.header | output.header.format | format |
| plugins.core.commands | format.output.subheader | output.subheader.format | format |
| plugins.core.commands | format.header | header.format | format |
| plugins.core.commands | get.command.line.length | command.line.length.get | format |
| plugins.core.commands | get.output.line.length | output.line.length.get | format |
| plugins.core.commands | add.command.by.func | command.add.by.func | format |
| plugins.core.commands | get.command.format | command.format | format |
| plugins.core.commands | get.current.command.args | command.current.args.get | format |
| plugins.core.commands | set.current.command | command.current.set | format |
| plugins.core.commands | remove.data.for.plugin | command.remove.for.plugin | format |
| plugins.core.commands | get.command.prefix | command.prefix.get | format |
| plugins.core.commands | command.help.format | command.help.format | unchanged |
| plugins.core.commands | get.commands.for.plugin.data | command.data.get | format |
| plugins.core.commands | run | command.run | format |
| plugins.core.commands | get.summary.data.for.plugin | summary.get.for.plugin | format |
| plugins.core.commands | get.detailed.data.for.plugin | detail.get.for.plugin | format |
| plugins.core.commands | list.commands.formatted | command.list.formatted | format |
| plugins.core.commands | list.plugins.formatted | plugin.list.formatted | format |
| plugins.core.errors | add | error.add | format |
| plugins.core.errors | get | error.list | format |
| plugins.core.errors | clear.all.errors | error.clear | format |
| plugins.core.events | register.event.by.func | event.register.by.func | format |
| plugins.core.events | get.current.event.name | event.current.name.get | format |
| plugins.core.events | get.current.event.record | event.current.record.get | format |
| plugins.core.events | get.event.stack | event.stack.get | format |
| plugins.core.events | add.event | event.add | format |
| plugins.core.events | get.event | event.get | format |
| plugins.core.events | has.event | event.exists | boolean |
| plugins.core.events | is.registered.to.event | event.is.registered | boolean |
| plugins.core.events | register.to.event | event.register | format |
| plugins.core.events | unregister.from.event | event.unregister | format |
| plugins.core.events | remove.events.for.owner | event.unregister.for.owner | format |
| plugins.core.events | get.detailed.data.for.plugin | detail.get.for.plugin | format |
| plugins.core.events | raise.event | event.raise | format |
| plugins.core.events | get.event.detail | event.detail.get | format |
| plugins.core.events | get.summary.data.for.plugin | summary.get.for.plugin | format |
| plugins.core.fuzzy | get.best.match | string.match.best | format |
| plugins.core.fuzzy | get.top.matches | string.match.top | format |
| plugins.core.log | get.level.color | log.level.color.get | format |
| plugins.core.log | can.log.to.console | logger.console.is.enabled | boolean |
| plugins.core.log | can.log.to.file | logger.file.is.enabled | boolean |
| plugins.core.log | can.log.to.client | logger.client.is.enabled | boolean |
| plugins.core.log | set.log.to.client | logger.client.level.set | format |
| plugins.core.log | set.log.to.console | logger.console.level.set | format |
| plugins.core.log | set.log.to.file | logger.file.level.set | format |
| plugins.core.log | clean.types | logger.type.clean | format |
| plugins.core.pluginm | save.all.plugins.state | plugin.state.save.all | format |
| plugins.core.proxy | is.mud.connected | mud.is.connected | boolean |
| plugins.core.proxy | get.mud.connection | mud.connection.get | format |
| plugins.core.proxy | preamble.get | preamble.get | unchanged |
| plugins.core.proxy | preamble.color.get | preamble.color.get | unchanged |
| plugins.core.proxy | shutdown | proxy.shutdown | format |
| plugins.core.proxy | restart | proxy.restart | format |
| plugins.core.settings | add | setting.add | format |
| plugins.core.settings | get | setting.get | format |
| plugins.core.settings | reset | setting.reset | format |
| plugins.core.settings | change | setting.set | format |
| plugins.core.settings | get.setting.info | setting.info.get | format |
| plugins.core.settings | initialize.plugin.settings | setting.initialize.for.plugin | format |
| plugins.core.settings | remove.plugin.settings | setting.remove.for.plugin | format |
| plugins.core.settings | save.plugin | setting.save.for.plugin | format |
| plugins.core.settings | get.all.for.plugin | setting.list | format |
| plugins.core.settings | raise.event.all.settings | setting.event.raise.all | format |
| plugins.core.settings | is.setting.hidden | setting.is.hidden | boolean |
| plugins.core.settings | add.setting.to.map | setting.map.add | format |
| plugins.core.settings | format.setting | setting.format | format |
| plugins.core.settings | get.all.settings.formatted | setting.list.formatted | format |
| plugins.core.settings | change.from.user | setting.set.from.user | format |
| sqldb database object (dynamic) | {database_name}.select | {database_name}.select | unchanged |
| sqldb database object (dynamic) | {database_name}.modify | {database_name}.modify | unchanged |
| sqldb database object (dynamic) | {database_name}.modify.many | {database_name}.modify.many | unchanged |
| sqldb database object (dynamic) | {database_name}.get.single.row | {database_name}.row.get | misnamed |
| plugins.core.sqldb | baseclass | baseclass.get | misnamed |
| ssc object (dynamic) | ssc.{name} | ssc.{name}.get | misnamed |
| plugins.core.ssc | baseclass.get | baseclass.get | unchanged |
| plugins.core.timers | has.timer | timer.exists | boolean |
| plugins.core.timers | get.timer.next.fire | timer.next.fire.get | format |
| plugins.core.timers | add.timer | timer.add | format |
| plugins.core.timers | remove.data.for.plugin | timer.remove.for.plugin | format |
| plugins.core.timers | remove.timer | timer.remove | format |
| plugins.core.timers | toggle.timer | timer.toggle | format |
| plugins.core.triggers | trigger.register | trigger.register | unchanged |
| plugins.core.triggers | trigger.unregister | trigger.unregister | unchanged |
| plugins.core.triggers | trigger.update | trigger.update | unchanged |
| plugins.core.triggers | trigger.add | trigger.add | unchanged |
| plugins.core.triggers | trigger.remove | trigger.remove | unchanged |
| plugins.core.triggers | trigger.get | trigger.get | unchanged |
| plugins.core.triggers | remove.data.for.owner | trigger.remove.for.owner | format |
| plugins.core.triggers | trigger.toggle.enable | trigger.toggle.enable | unchanged |
| plugins.core.triggers | trigger.toggle.omit | trigger.toggle.omit | unchanged |
| plugins.core.triggers | group.toggle.enable | group.toggle.enable | unchanged |
| plugins.core.utils | format.list.into.columns | column.format | format |
| plugins.core.utils | dump.object.as.string | object.dump | format |
| plugins.core.utils | get.keys.from.dict | dict.key.list | format |
| plugins.core.utils | dedent.list.of.strings | string.dedent | format |
| plugins.core.utils | convert.timedelta.to.string | timedelta.to.string | format |
| plugins.core.utils | convert.to.readable.number | number.to.readable | format |
| plugins.core.utils | convert.seconds.to.dhms | seconds.to.dhms | format |
| plugins.core.utils | format.time | timelength.format | format |
| plugins.core.utils | verify.value | value.verify | format |
| plugins.core.utils | center.colored.string | string.center.colored | format |
| plugins.core.utils | check.list.for.match | string.match.in.list | format |
| plugins.core.utils | convert.timelength.to.secs | timelength.to.seconds | format |
| plugins.core.utils | convert.data.to.output.table | table.format | format |
| plugins.core.utils | cap.line | line.cap | format |
| plugins.core.watch | watch.add | watch.add | unchanged |
| plugins.core.watch | watch.remove | watch.remove | unchanged |
| plugins.core.watch | remove.all.data.for.plugin | watch.remove.for.plugin | format |
