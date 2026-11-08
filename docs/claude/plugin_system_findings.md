---
title: Plugin System Analysis and Findings
description: Audit of plugin discovery, loading, unloading, reloading, hooks and BasePlugin patching, with defects and a patterns review
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - plugins
  - review
---

# Plugin System Analysis and Findings

**Date:** 2026-11-03
**Analyzer:** Claude Sonnet 5.5
**Scope:** Plugin discovery, loading, unloading, reloading, plugin hooks and the `BasePlugin`
class (audit issue #104). Compared against [Plugin System](plugin_system.md).

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [How This Was Verified](#how-this-was-verified)
3. [Status of the Known Items](#status-of-the-known-items)
4. [Q1: Does Unload and Reload Leave Anything Behind?](#q1-does-unload-and-reload-leave-anything-behind)
5. [Q2: What Does patch() Do?](#q2-what-does-patch-do)
6. [Q3: Plugin Hooks, Names, Priorities and Order](#q3-plugin-hooks-names-priorities-and-order)
7. [Q4: Where the Docs Disagreed With the Code](#q4-where-the-docs-disagreed-with-the-code)
8. [Q5: Patterns and Anti-Patterns](#q5-patterns-and-anti-patterns)
9. [New Defects](#new-defects)
10. [Other Observations](#other-observations)

---

## Executive Summary

The registries that matter on a clean unload (API, event registrations, commands, settings,
timers, triggers, watches) are all emptied when a *fully loaded* plugin is unloaded, and the
plugin instance is garbage collected when none of its event callbacks has run. The fixes merged
since the issue was written (#95, #96, #97, #100, #111, #117, #119) hold up: a reload loads new
code, command data is cleared, dependencies are ordered.

The gaps are in the paths the happy case does not cover:

- **A failed load left everything the plugin registered before it failed** (PS-1, fixed). The
  loader only runs `uninitialize` for a plugin flagged loaded, and the per-subsystem cleanup rides
  on the `ev_plugin_unloaded` event that `uninitialize` raises. The loader now raises that event
  and removes the APIs itself for a plugin that is not loaded.
- **Two of the subsystem cleanup handlers are broken**: cmdq calls an API that does not exist
  (PS-2) and watch deletes from a dict while iterating it (PS-3). Both only log an error, so
  unload "succeeds" and leaves data behind.
- **`attributes_to_save_on_reload` is unreliable** for any plugin that sets defaults in its own
  `__init__` (PS-4, fixed): the loader now restores them after construction.
- **Metadata parsing is fragile**: one `PLUGIN_VERSION = 1  # note` line in any plugin aborts
  discovery for every plugin (PS-5).
- **`patch()`** (runtime `setattr` onto the base class) has several silent failure modes and one
  user (PS-7). An explicit mixin replaces it with less machinery.
- **No test covers hooks, `patch()` or `BasePlugin`.**

**Key Findings:**

- 12 defects (PS-1 to PS-12), listed under [New Defects](#new-defects); PS-11 widens the
  existing #98.
- The issue's items about reload loading old code, dependencies, command data and the API
  caches are fixed. #94 and #98 remain open, and #98 is wider than described.
- The docs were wrong about the lifecycle order, the save hook, how reload works, where
  `RegisterToEvent` is imported from and the data directory. They are corrected in
  [Plugin System](plugin_system.md).

---

## How This Was Verified

Claims below are tagged **verified** (run against the code, with the output summarised),
**read** (from reading the code, not executed) or **unverified**.

Verification used throwaway scripts that boot the real plugin system in-process (the same steps
as `MudProxy.run` without the listeners and the asyncio loop), then load, unload and reload
bundled plugins and three small user plugins, and snapshot each registry before and after. The
scripts were deleted afterwards; they are not part of the repository.

---

## Status of the Known Items

Every item in the issue's Description, with its current state.

| Item from the issue | Status | Where |
| :--- | :--- | :--- |
| Every plugin imported twice through the `src/plugins` shim, so reload never loads new code | **Fixed** (verified: a changed `CODE_VERSION` constant was picked up by `plugin.reload`) | #95, PR #109 |
| The `src/plugins` shim itself; user plugins load from `BASTPROXY_HOME/plugins` under `userplugins.` | **Fixed** | #110, PR #112 |
| A failed load left some of a plugin's modules in `sys.modules` | **Fixed** for modules, and for registrations by #121 (see PS-1) | #111, PR #113 |
| Dependencies declared but never used | **Fixed** (`PLUGIN_DEPENDENCIES`, `src/bastproxy/libs/plugins/dependency.py`, reload of dependents; `dependency.add` removed) | #97, PR #116 |
| Command data kept after unload | **Fixed** (verified: `command_data` and `commands_list` empty after unload) | #96, PR #115 |
| API `lru_cache`s kept unloaded plugins alive | **Fixed** (verified: instances of the bundled plugins I unloaded were collected) | #100, PR #114 |
| `PLUGIN_REQUIRED` not parsed | **Fixed** | #117, PR #118 |
| Double-quoted name, author and purpose not parsed | **Fixed** | #119, PR #120 |
| `_baseplugin` layout is flat | **Fixed** | #94 |
| Two test plugins use a layout the loader cannot import | **Fixed** (#98): all three affected test plugins moved | #98, see [PS-11](#ps-11-test-plugins-with-an-unloadable-layout) |
| `patch()` copies functions onto `Plugin`; the loader skips patching on reload, so patched functions come from whichever copy loaded first | **Fixed** (#131): replaced by the `Settings` mixin, `patch()` removed | #131, PS-7 |
| 36 `@RegisterPluginHook` uses with priorities: is the order documented and tested? | **Documented now; still untested** | Q3, PS-6 |
| `attributes_to_save_on_reload`, `can_reload_f`, `reload_dependents_f` | **Partly broken** | PS-4, Q1 |
| What other plugins keep pointing at an unloaded plugin | **No stale references found** among bundled plugins (no plugin stores a plugin instance); `Event.current_callback` kept one alive until the fix for #127, see PS-8 | PS-8 |

The "36 uses" figure was a `grep` count that includes one commented-out line in the timers
plugin (a `stats` hook, which is not a hook name the base class processes).

---

## Q1: Does Unload and Reload Leave Anything Behind?

The unload sequence in `src/bastproxy/libs/plugins/loader.py` (`PluginLoader._api_plugin_unload`)
is: refuse if `can_reload_f` is false; run `uninitialize()` **only if the plugin is flagged
loaded**; drop the plugin from the `pluginstoload` setting; delete the instance; delete every
module under the plugin package that does not set `CANRELOAD = False` (keeping a weak reference
to each so stale modules can be listed); set `has_been_reloaded`; reset `runtime_info`.

Almost all registry cleanup is indirect. The base `uninitialize` hook
(`_phook_base_unitialize_hook`, priority 100, in `src/bastproxy/plugins/_baseplugin/_base.py`)
saves state, caches reload attributes, raises `ev_<plugin_id>_unloaded` and `ev_plugin_unloaded`,
and then removes the plugin's APIs. Each subsystem listens to `ev_plugin_unloaded` and removes
what it holds for that plugin.

| Registry | Written by | Removed by | Result |
| :--- | :--- | :--- | :--- |
| API (`API._class_api`) | `libs.api:api.add.for.object`, called from `_phook_base_init_add_apis`, `_phook_base_init` and `_phook_base_post_initialize_setup` | `_phook_base_unitialize_hook` calls `libs.api:api.toplevel.remove` (`API._api_api_toplevel_remove` in `src/bastproxy/libs/api/_api.py`) | Verified clean after unload. Cleaned after a failed load too (PS-1, fixed). |
| Event registrations | `plugins.core.events:event.register`, `RegisterToEvent` | events `_eventcb_plugin_unloaded` calls `event.unregister.for.owner`, which calls `Event.removeowner` | Verified clean after unload, and after a failed load (PS-1, fixed). |
| Event definitions (`ev_<id>_loaded`, `_unloaded`, `_save`, `_savestate`, `ev_<custom>`, `watch_<name>`) | `plugins.core.events:event.add` | **Nothing** | Verified: all stay in the events plugin with `created_by` set to the unloaded plugin. See [Other Observations](#other-observations). |
| Commands | `update_commands_for_plugin` on `ev_plugin_loaded` | commands `_eventcb_plugin_unloaded` calls `command.remove.for.plugin` | Verified clean (#96). |
| Settings | `plugins.core.settings:setting.add`, `setting.initialize.for.plugin` | settings `_eventcb_settings_plugin_unloaded` saves then calls `setting.remove.for.plugin` | Verified clean after unload. After a failed load the handler also runs (it tolerates a plugin with no settings), so the settings and the open `PersistentDict` are closed (PS-1, fixed). |
| Timers | `plugins.core.timers:timer.add` | timers `_eventcb_plugin_unloaded` calls `timer.remove.for.plugin`, which matches timers by owner ID (it used to look the plugin up through `plugin.instance.get`, which fails for a plugin that is not loaded) | Verified clean after unload and after a failed load (PS-1, fixed). |
| Triggers | `plugins.core.triggers:trigger.add` | triggers `_eventcb_plugin_unloaded` calls `trigger.remove.for.owner` | Verified clean after unload. |
| Watches | `plugins.core.watch:watch.add` | watch `_eventcb_plugin_unloaded` calls `watch.remove.for.plugin` | Broken for more than one watch (PS-3). |
| cmdq command types | `plugins.core.cmdq:type.add` | cmdq `_eventcb_plugin_unloaded` calls `remove.mud.commands.for.plugin` | Broken (PS-2). |
| Reload cache | `_phook_base_unitialize_hook` when `is_reloading_f` | `BasePlugin.restore_reload_cache`, called by the loader after construction | Works (PS-4 fixed). |
| `sys.modules` | import | `_api_plugin_unload`, and the failed-load cleanup in `_api_plugin_load` (`plugin_module_names`) | Clean, except modules that set `CANRELOAD = False` stay by design, and `deletemodule` keeps only the bundled `_baseplugin` package (PS-10, fixed). |
| Plugin instance | `_instantiate_single_plugin` | `del runtime_info.plugin_instance` | Collected after unload for the bundled plugins I tried. Stayed reachable through `Event.current_callback` once one of its callbacks had run, fixed in the PR for #127 (PS-8). |

Reload (`PluginLoader._api_plugin_reload`) unloads the plugin and, if `reload_dependents_f` is
set, its loaded dependents (furthest first), then loads them again with one `plugin.load` call.
Verified: a reload picks up edited code, restores the setting `pluginstoload` entry, and the old
instance was collected.

Two limits of reload:

- `plugin.reload` does not set `is_reloading_f` (**read**). Only the `<plugin>:plugin.reloading.set` API
  does, and only the `reload` command (`_command_reload` in the pluginm plugin) calls it.
  Calling `plugin.reload` directly drops `attributes_to_save_on_reload`. The reload probe
  called `plugin.reloading.set` first.
- A plugin whose unload fails part-way is left flagged loaded (**read**). Nothing is
  half-removed, because the failing hook runs before the base hook at priority 100, but the
  plugin keeps running with whatever its earlier `uninitialize` hooks already tore down.

---

## Q2: What Does patch() Do?

`patch(full_import_location, override=False)` in `_patch.py` (removed, in `_baseplugin`)
imports (or finds in `sys.modules`) a module, and for every module attribute that is a
function whose attribute name starts with `_`, runs `setattr(Plugin, func.__name__, func)` on
the **`Plugin` class in `_base.py`** (not on `BasePlugin`). If anything was added after startup
it raises `ev_baseplugin_patched`. The loader calls it in `_import_single_plugin` for the first
`_patch_base.py` found in the plugin package, and skips it when `has_been_reloaded` is set.

Only `_patch_base.py` (removed, in the settings plugin) uses it. It adds the `set` command
(`_command_settings_plugin_set`) and the `initialize` hook `_phook_settings_post_initialize`
(priority 75) to every plugin.

Behaviour, all **verified** with throwaway modules patched onto `Plugin`:

| Case | Result |
| :--- | :--- |
| Two modules patch the same name | The second returns `True` but its function is skipped (a warning is logged). The first module wins silently as far as the caller can tell. |
| `patch(module, override=True)` on a name that already exists | Still skipped: the `hasattr(Plugin, ...)` check runs regardless, so `override` never replaces anything. |
| Patch function named like a method of the `Commands` mixin (`_command_help`) | **Replaces it for every plugin.** `hasattr(Plugin, name)` does not see the mixin because `Commands` is a base of `BasePlugin`, not of `Plugin`. Verified: `BasePlugin._command_help` after the patch comes from the patching module. |
| Attribute name differs from `__name__` | The function is stored under `__name__`, and the underscore filter tests the attribute name. |
| Runtime patch (not at startup) | Raises `ev_baseplugin_patched`; the commands and events plugins re-register every loaded plugin. A probe with the startup flag off did not get past its first patch calls in 40 seconds
with 17 plugins loaded; with the flag on it finished at once. |

On reload (**read**, from the two verified skip rules above): the loader does not patch again
after `has_been_reloaded`, and even if it did, existing names are skipped. The functions on
`Plugin` therefore stay the ones from the first import for the life of the process, with their
`__globals__` pointing at a module that unload removed from `sys.modules`. I did not reload the
settings plugin itself (it takes the proxy down).

Should patching be replaced? **Yes.** The one user needs nothing a mixin cannot do:
`_commands.py` already shows the shape (`class Commands(Protocol)` mixed into `BasePlugin`, and
it already imports from the commands plugin). A `_settings.py` mixin beside it would carry the
`set` command and the `initialize` hook, with no `setattr`, no reload skip, no
`ev_baseplugin_patched` and no ordering dependence on which plugin imported first. That removes
`_patch.py`, `modules_patched`, the `_patch_base.py` discovery in the loader and the two
`ev_baseplugin_patched` handlers. See PS-7.

---

## Q3: Plugin Hooks, Names, Priorities and Order

### How hooks are processed

`RegisterPluginHook(hook_name, priority=50)` stores `{hook_name: priority}` in
`func.plugin_hooks`. `Plugin._process_plugin_hook` (in `_base.py`) calls
`_get_plugin_hook_functions`, which walks `dir(obj)`, keeps names starting with `_phook_`
that are bound methods carrying that hook, groups by priority and runs the groups in ascending
priority.

- **Ties run in alphabetical order of the method name** (it is `dir()` order). The docs said
  "the order they're discovered". Verified: `_phook_base_post_initialize_add_reset_command`
  ran before `_phook_pa_initialize`, both at priority 50.
- The hook name is not validated. `@RegisterPluginHook("stats")` (commented out in the timers
  plugin) or a misspelled `"initialize"` is accepted and never runs.
- The `_phook_` prefix is required to run but not to be registered, and the second lookup,
  `_get_all_plugin_hook_functions` (behind the `plugin.hook.list` API), ignores the prefix and
  loses hooks that share a priority (PS-6).
- A hook that raises in `__init__` fails the plugin; in `initialize` the loader unloads it
  (PS-1 shows what that leaves behind); in `uninitialize` the unload stops and returns `False`.
- The `kwargs` branch of `_process_plugin_hook` (`kwargs = func(**kwargs)`) is dead: every
  caller passes none.

### Hooks the base class registers (in run order)

| Hook | Priority | Method | What it does |
| :--- | ---: | :--- | :--- |
| `__init__` | 1 | `_phook_base_init_add_apis` | Adds the plugin's APIs |
| `__init__` | 75 | `_phook_base_init` | Adds the APIs again |
| `initialize` | 1 | `_phook_base_initialize` | Adds the `_version` setting, registers the disconnect callback, adds `ev_<id>_savestate` |
| `initialize` | 50 | `_phook_base_post_initialize_add_reset_command` | Enables the `reset` command |
| `initialize` | 75 | `_phook_settings_post_initialize` (`Settings` mixin) | `settings:setting.initialize.for.plugin` |
| `initialize` | 90 | `_phook_base_post_initialize_update_version` | Runs `version_functions` for a version bump |
| `initialize` | 91 | `_phook_base_post_initialize_setup` | Adds APIs again, flags the plugin loaded, adds `ev_<id>_loaded`/`_unloaded`, raises the loaded events (not at startup) |
| `uninitialize` | 100 | `_phook_base_unitialize_hook` | Saves, caches reload attributes, raises the unloaded events, removes the APIs |

Everything else in the tree uses the default priority 50, except the log plugin's `__init__`
hook at 99. The orderings that matter and were undocumented:

- A plugin's own `settings:setting.add` calls must happen before priority 75, or they are missed by
  `setting.initialize.for.plugin`.
- Reload attributes are restored by the loader right after construction, so defaults may be set in
  `__init__` or in an `__init__` hook (PS-4, fixed).
- A plugin's `uninitialize` hooks run before the base hook at 100, so they still have their APIs
  and settings.

### Is the order tested?

No. A search of `tests/` finds no test of `RegisterPluginHook`, `_process_plugin_hook`,
`patch()` or `BasePlugin`. The loader, dependency resolver, discovery and failed-load paths do
have tests under `tests/libs/plugins/` and `tests/plugins/`.

Do hooks run correctly again on reload? Yes: they are looked up on the new instance every time.
The one exception is the patched hook, which comes from the first module (Q2).

---

## Q4: Where the Docs Disagreed With the Code

Corrected in [Plugin System](plugin_system.md) in this change:

| Section | Said | Code |
| :--- | :--- | :--- |
| Loading, steps 1 to 2 | `importlib.import_module` of the package, then of the class module | One `imputils.importmodule` of the `.plugin` module, which returns the module if already in `sys.modules`; then `patch()` for `_patch_base.py` |
| Loading, step 6 | `ev_plugin_loaded` is raised when the plugin loads | Raised at the end of `initialize` (hook priority 91), and not at startup |
| Initialization | `initialize` runs "after all plugins are loaded" | Per batch: import all, instantiate all, then `initialize` each in dependency order |
| Saving | `ev_plugin_save` triggers the `save` hook | The `plugin.state.save` API runs the `save` hooks first, then raises `ev_<id>_save` and `ev_plugin_save` |
| Unloading | Separate API removal and event unregistration steps | Both happen through the base `uninitialize` hook and the `ev_plugin_unloaded` handlers; order given in Q1 |
| Reloading, step 4 | `importlib.reload(module)` | Modules are deleted from `sys.modules` and imported again; `importlib.reload` is not used |
| Reloading, step 1 | Setting `attributes_to_save_on_reload` is enough | Only cached when `is_reloading_f` is set (the `reload` command does it) and restored by the loader right after construction (`restore_reload_cache`) |
| Hook ordering | Ties run "in the order they're discovered" | Alphabetical by method name |
| `__init__` hook | "after base initialization" | Runs inside the base `__init__`; the base hooks sit at priority 1 and 75 |
| Metadata | Example with a trailing comment on `PLUGIN_REQUIRED` | Metadata lines are matched one per line; a trailing comment breaks `PLUGIN_VERSION` and hides name, author, purpose and required (PS-5) |
| `PLUGIN_REQUIRED` | Plugin "is required to be loaded" | Required plugins (and every `plugins.core` plugin) are refused by `plugin.unload` and the `unload` command; reload is still allowed (PS-12) |
| Data directory | `data/<plugin_id>/` | `$BASTPROXY_HOME/data/plugins/<plugin_id>` |
| `RegisterToEvent` import | `from bastproxy.libs.events import ...` | `from bastproxy.plugins.core.events import RegisterToEvent` |
| `ev_baseplugin_patched` | "BasePlugin class was reloaded" | Raised when `patch()` adds functions after startup |
| Loader APIs | 11 listed | More exist; the list now matches |
| Key attributes, `PluginInfo`, `PluginRuntimeInfo` | Partial | Missing attributes added |

`docs/claude/event_system.md` repeats the `ev_baseplugin_patched` description; it is not part
of this audit's page and is left for the event system audit.

---

## Q5: Patterns and Anti-Patterns

"Fits" means keep. "Change" means worth an issue. Locations are file and symbol.

| # | Pattern or anti-pattern | Where | Consistent? | Verdict |
| --: | :--- | :--- | :--- | :--- |
| 1 | **Lifecycle hooks by name and priority** (template method plus registry) | `_pluginhooks.py` `RegisterPluginHook`, `_base.py` `_process_plugin_hook` | Yes for processing; not for introspection (PS-6) | **Keep the idea.** Fix: validate hook names, validate the `_phook_` prefix at registration, one lookup function, document tie order, add tests. |
| 2 | **Runtime monkey patching** with `setattr` onto a class | `_patch.py` `patch`, called from `loader.py` `_import_single_plugin` | One user; five silent failure modes (Q2) | **Change** to an explicit mixin (PS-7). Anti-pattern: hidden control flow, order-dependent, reload-unsafe. |
| 3 | **Decorator registration through function attributes** | `RegisterPluginHook` (`plugin_hooks`), `AddAPI` (`api`), `RegisterToEvent` (`event_registration`), `AddCommand` | Yes, four decorators, one mechanism | **Keep.** The attributes live on class-level function objects shared by every instance; `API._api_api_toplevel_remove` mutates `func.api["addedin"]` on them. That is hidden global state. It works, but any new decorator should store data on the instance or a registry, not the shared function. |
| 4 | **Service locator through string API names** (`self.api("plugins.core.events:...")`) | Everywhere; `_base.py` has 22 such calls across five core plugins (events 15, settings 4, commands, proxy and utils 1 each) | Yes | **Keep as the contract, add a guard.** The cost: a typo is a runtime error on a rarely run path. A scan of literal API names against the live registry found three that do not exist (`libs.api:get:caller:owner` in the triggers plugin, `libs.timing:timing.start` and `timing.finish` in cmdq), and the f-string `remove.command.type` in cmdq is a fourth. PS-2 and PS-9 cover the callers; PS-12 added the guard test (`tests/plugins/test_api_names_exist.py`), which found a fourth miss the audit's scan did not list: `errors.clear` in the errors plugin. |
| 5 | **`BasePlugin(Plugin, Commands)` inheritance** with a `typing.Protocol` used as an implementation mixin | `src/bastproxy/plugins/_baseplugin/__init__.py`, `_commands.py` `Commands(Protocol)` | Yes | **Change (small).** `Protocol` is for structural typing; a plain mixin class says what it is and avoids `self: "Plugin"` annotations and `# pyright: ignore` comments. The wider inheritance surface (about 25 attributes, 8 APIs, 8 hooks, name-matched by plugins) is the plugin contract; keep it, do not grow it. New base features should be mixins like `Commands`, not patches. |
| 6 | **Hard dependency of the base class on concrete plugins** (tight coupling) | `_base.py` calls events, settings, commands, proxy and utils APIs; `_commands.py` imports `bastproxy.plugins.core.commands`; `loader.py` and `plugininfo.py` import `bastproxy.plugins._baseplugin` | Yes | **Keep, document.** `libs` importing `plugins` inverts the stated layering (`libs` is the framework). `plugininfo.py` imports `BasePlugin` only for an annotation; `TYPE_CHECKING` removes that edge for free. No dependency injection exists, and adding it here is out of scope. |
| 7 | **Hidden global state** | `_patch.py` `modules_patched` and `API = APIClass(__name__)`; `reloadutils.HELPER`; `API` class-level flags (`startup`, `shutdown`, paths) set from `src/bastproxy/__init__.py` | Yes | **Keep `HELPER` and the API flags** (the architecture relies on them). **Remove `modules_patched`** with `patch()`. |
| 8 | **Import-time side effects** | `src/bastproxy/__init__.py` creates directories, prints two banner lines (the string `last updated ...`) and raises if `BASTPROXY_HOME` is wrong; `reloadutils` instantiates `ReloadHelper` and registers APIs on import; `_patch.py` creates an `API` object on import | Yes | **Change (low).** The environment check and `mkdir` are fine for an application entry point but make `import bastproxy` unusable in tools. The banner `print`s belong in `main`. Not filed separately. |
| 9 | **Catch-all `except`** | `loader.py` in `_instantiate_single_plugin`, `_run_initialize_single_plugin`, `_api_plugin_unload` (two, one an `except Exception` around a dict lookup); `imputils.importmodule`; `plugininfo.check_file_is_valid_python_code`; `_patch.py` `patch` | Mostly justified: each logs with `exc_info` and either exits or unloads | **Keep**, with one change: the dict-lookup `except Exception` in `_api_plugin_unload` should be `except KeyError`. |
| 10 | **Silent failures** | cmdq and watch unload handlers (PS-2, PS-3) log through the events plugin and unload carries on; `patch()` returns `True` when it skipped everything | No | **Change.** `plugin.unload` returns `True` while handlers failed. Handlers should not raise after partially deleting; the loader cannot see their errors today. |
| 11 | **String concatenation for paths** | Loader and `PluginInfo` use `Path` throughout; `plugin_info.data_directory` is a `Path` | Yes | **Fits.** The only string "paths" are import locations, which are not file paths. |
| 12 | **Repeated work in hooks** | `libs.api:api.add.for.object` is called by three base hooks (priority 1, 75 and 91) | n/a | **Keep, document.** 75 picks up objects created by `__init__` hooks below 75 and 91 those created in `initialize`; neither is written down. Not filed separately. |
| 13 | **Magic-string exclusion** | `imputils.deletemodule` skipped any module whose name contained `baseplugin` or `baseconfig` | n/a | **Changed** (PS-10, fixed): exact package prefix match. |
| 14 | **Dead return value** | `update_all_plugin_information` returns `None`; two callers branch on it | n/a | **Change** (PS-9). |

---

## New Defects

### PS-1: A failed load leaves registrations behind

**Status:** fixed in the PR for #121; `plugin.unload` on a plugin that is not loaded raises `ev_plugin_unloaded` and calls `libs.api:api.toplevel.remove` (`_remove_plugin_registrations`), the `can_reload_f` refusal applies only to loaded plugins, and a failing `initialize` clears the loaded flag first. The timers handler matches by owner ID and the settings handler tolerates a plugin with no settings. Still open: `timer.add(plugin_id=...)` calls `plugin.instance.get`, so it fails for a plugin that is still initializing; event definitions created with `event.add` are not removed by a clean unload either.

**Issue:** [#121](https://github.com/endavis/bastproxy/issues/121)
**Location:** `loader.py` `_instantiate_single_plugin`, `_run_initialize_single_plugin`,
`_api_plugin_unload` (skips `uninitialize` unless `is_loaded`); timers
`_api_timer_remove_for_plugin` (needs `plugin.instance.get`, which needs the loaded flag).

**Evidence (verified):** Two throwaway user plugins. `pb` registers a timer, a watch and an
event callback in an `initialize` hook and then raises. `pc` raises in `__init__` after
`super().__init__()`. After `plugin.load` returned both as bad, the registries still held:

```text
plugins.zprobe.pb  api_class (9 APIs), event_regs {'ev_libs.net.mud_muddisconnect': [...],
                   'ev_plugin_loaded': ['_eventcb_x']}, timers ['pb_timer'], watch ['pb_watch'],
                   settings True, events_created_by [...]
plugins.zprobe.pc  api_class (9 APIs)
```

The leftover `_eventcb_x` and the timer callback are bound methods of an instance the loader
has deleted, so the instance stays alive and the timer would fire into it (**read**, I did not
let the timer fire). The settings entry holds the plugin's `PersistentDict`, which
`setting.remove.for.plugin` closes and a failed load never does (**read**). #111 removed the
modules; this is the same cleanup for the registries.

**Fix:** Give the loader one cleanup path that does not depend on `is_loaded`: raise
`ev_plugin_unloaded` for the plugin ID (so every subsystem handler runs) and call
`libs.api:api.toplevel.remove`, from both failure branches, guarded so a handler error does not stop the
rest. Make the timers handler tolerate a plugin with no instance. Add a test with a plugin that
raises in `initialize` after registering a timer.

### PS-2: cmdq unload cleanup raises and leaves command types behind

**Issue:** [#122](https://github.com/endavis/bastproxy/issues/122)
**Location:** `src/bastproxy/plugins/core/cmdq/plugin/_cmdq.py`
`_api_remove_mud_commands_for_plugin`; also `_api_type_add`.

**Evidence (verified):** With an entry in `cmdq.cmds` owned by a plugin, unloading the plugin
logs `AttributeError: plugins.core.cmdq : plugins.core.cmdq:remove.command.type is not in the
api` from the `ev_plugin_unloaded` handler, and the entry is still in `cmds` afterwards. The
API is registered as `type.remove`. Even with the name fixed, the loop deletes from
`self.cmds` while iterating `self.cmds.keys()`. Nothing in the tree calls `type.add`, which
also formats event names from `self.current_command['ctype']` instead of `cmdtype` (fails with
no current command), so the type registry is unused and untested.

**Fix:** Call `type.remove`, iterate over `list(self.cmds)`, fix `type.add` to use `cmdtype`,
and add a test that adds a type, unloads its owner and checks it is gone. Also covers
`libs.timing:timing.start` and `timing.finish`, which cmdq calls and which are not registered.

### PS-3: Watch cleanup raises after removing one watch

**Issue:** [#123](https://github.com/endavis/bastproxy/issues/123)
**Location:** `src/bastproxy/plugins/core/watch/plugin/_watch.py`
`_api_watch_remove_for_plugin`.

**Evidence (verified):** Three watches owned by one plugin, then
`plugins.core.watch:watch.remove.for.plugin`:

```text
watch cleanup raised RuntimeError dictionary changed size during iteration
watches left ['w2', 'w3']
```

The handler iterates `self.watch_data.keys()` while `watch.remove` deletes from it. A plugin
with one watch loses it (the error comes on the next step); a plugin with several keeps all but
the first.

**Fix:** Iterate over `list(self.watch_data)`.

### PS-4: Reload attributes are overwritten by the plugin's own `__init__`

**Status:** fixed in the PR for #124; the loader calls `BasePlugin.restore_reload_cache` right after the constructor returns, so a default set in `__init__` cannot overwrite it.

**Issue:** [#124](https://github.com/endavis/bastproxy/issues/124)
**Location:** `_base.py` `_phook_base_init` (priority 75, restores the cache inside
`Plugin.__init__`).

**Evidence (verified):** A plugin with `self.attributes_to_save_on_reload = ["counter"]` and
`self.counter = 0` after `super().__init__()`: set `counter = 41`, ran `plugin.reloading.set` and
`plugin.reload`; the new instance printed `counter restored 0`. Bundled plugins avoid this by
setting both the list and the defaults in an `__init__` hook below priority 75
(`_phook_init_plugin` in the clients, proxy and commands plugins). The documented example
shows the failing form.

**Fix:** Restore the cache from the loader right after the constructor returns (before
`initialize`), or document hook-only initialisation and raise when `attributes_to_save_on_reload`
is set outside a hook. The loader option removes the trap.

### PS-5: One badly formatted metadata line aborts discovery

**Status:** fixed in the PR for #125; `update_from_init` now reads the five values with `ast`.

**Issue:** [#125](https://github.com/endavis/bastproxy/issues/125)
**Location:** `plugininfo.py` `PluginInfo.update_from_init`, the `VERSIONRE`, `NAMERE`,
`AUTHORRE`, `PURPOSERE` and `REQUIREDRE` patterns.

**Evidence (verified):**

```text
PLUGIN_VERSION = 1  # first        -> ValueError: invalid literal for int() with base 10: '1  # first'
discovery (update_all_plugin_information) raised the same ValueError
PLUGIN_NAME = "x"  # the name      -> name '' and is_plugin False (no error)
PLUGIN_REQUIRED = True  # yes      -> required False (no error)
```

`update_all_plugin_information` has no per-plugin guard, so one user plugin with a comment on
its version line stops discovery for all plugins; at startup that is an uncaught exception
before any plugin loads. The other lines fail quietly.

**Fix:** Read the five values with `ast` the way `_parse_dependencies` already reads
`PLUGIN_DEPENDENCIES` (comments and quoting then do not matter), record a bad value in
`import_errors` for that plugin and carry on.

### PS-6: `plugin.hook.list` drops hooks that share a priority

**Status:** fixed in the PR for #126; both lookups now share `_collect_plugin_hook_functions`.

**Issue:** [#126](https://github.com/endavis/bastproxy/issues/126)
**Location:** `_base.py` `_get_all_plugin_hook_functions` (the `append` is inside the
`if ... not in` block).

**Evidence (verified):** For a plugin with two `initialize` hooks at priority 50,
`plugin.hook.list` listed only `_phook_base_post_initialize_add_reset_command` at 50, while the
real run list (`_get_plugin_hook_functions`) had both. The API is the only way to see hooks
from outside, and the two lookups also disagree on the `_phook_` prefix.

**Fix:** Move the `append` out of the `if`; make both methods one function; add tests for
priority order, tie order and `plugin.hook.list`.

### PS-7: `patch()` has silent failure modes and one user

**Status:** fixed in the PR for #131; the `set` command and the settings `initialize` hook are now the `Settings` mixin on `BasePlugin` (`src/bastproxy/plugins/_baseplugin/libs/_settings.py`). `patch()`, `modules_patched`, the loader's `_patch_base.py` branch, `PluginInfo.has_been_reloaded` and the two `ev_baseplugin_patched` handlers are removed. Breaking for plugins that shipped a `_patch_base.py`.

**Issue:** [#131](https://github.com/endavis/bastproxy/issues/131)
**Location:** `_patch.py` `patch`; `loader.py` `_import_single_plugin`;
`_patch_base.py` (removed, in the settings plugin).

**Evidence (verified):** see the table in Q2: `override=True` never overrides; a second patch
of the same name returns `True` while skipping it; a patch function named `_command_help`
replaced `Commands._command_help` for `BasePlugin`; the runtime path rebroadcasts to every
plugin.

**Fix:** Replace with a `_settings.py` mixin beside `_commands.py` (Q2), then delete `_patch.py`,
the loader's `_patch_base.py` branch, `has_been_reloaded` and the two `ev_baseplugin_patched`
handlers. This is a refactor and needs the settings plugin's tests to pass unchanged.

### PS-8: An unloaded plugin instance stays alive through the last-run callback

**Status:** fixed in the PR for #127; `Event.raise_event` clears `current_callback` and `active_event` after each raise, and `Event.removeowner` clears `current_callback` when it belongs to the removed owner. The dead `current_callback = None` in `ProcessRaisedEvent._exec_once` is removed. The unbounded `raised_events` growth is a separate memory problem, tracked as [#153](https://github.com/endavis/bastproxy/issues/153) (Bug #3 in [Event System Findings](event_system_findings.md)) and is fixed in the PR for #153.

**Issue:** [#127](https://github.com/endavis/bastproxy/issues/127)
**Location:** `src/bastproxy/plugins/core/events/plugin/_event.py` `Event.raise_priority` set
`Event.current_callback` to each callback it ran and nothing cleared it.

**Evidence (verified):** A user plugin with a `RegisterToEvent("ev_plugin_loaded")` callback was
loaded and unloaded; after `gc.collect()` the instance was still alive. The first diagnosis blamed
`raised_events`, but a probe with a real `Event` showed the chain is instance, bound method,
`Callback`, `Event.current_callback`. `raised_events` holds `ProcessRaisedEvent` objects that
reach a callback only through `.event`, so the history does not keep an owner alive. If another
owner's callback ran last the instance was collected. The bundled plugins I unloaded were
collected because none of their callbacks was the last one run on its event.

**Fix:** Clear `current_callback` after each raise and on `removeowner`. Regression tests are in
`tests/plugins/core/events/test_event_unload_retention.py`.

### PS-9: Dead and wrong calls in the loader and the base class

**Status:** fixed in the PR for #128; the missing call and the API name are corrected and the dead loader branches were dropped.

**Issue:** [#128](https://github.com/endavis/bastproxy/issues/128)
**Location:** `_base.py` `_phook_base_post_initialize_setup` (`self.api("plugins.core.proxy:is.mud.connected")`
without `()`); `loader.py` `_api_plugin_list_not_loaded` and `_load_core_and_client_plugins_on_startup`
(branch on the return value of `update_all_plugin_information`, which returns `None`);
triggers `_api_trigger_remove` (`libs.api:get:caller:owner`, colons for dots).

**Evidence (verified):** `is.mud.connected` returned an `APIItem` that is truthy
(`bool(item)` is `True`; calling it returned `False`), so the test reduces to
`is.character.active`. `update_all_plugin_information()` printed `None`. The scan of literal
API names found `libs.api:get:caller:owner`.

**Fix:** Call the API; make `update_all_plugin_information` return the conflict list (or drop
the dead branches); correct the API name. The static name check in PS-12 would have caught the
last one.

### PS-10: Module cleanup ignores `CANRELOAD` in one path and uses a substring skip list in another

**Status:** fixed in the PR for #129; `deletemodule` matches the bundled `_baseplugin` package by prefix and both cleanup paths share `reloadable_plugin_module_names`.

**Issue:** [#129](https://github.com/endavis/bastproxy/issues/129)
**Location:** `imputils.py` `deletemodule`; `loader.py` `_api_plugin_load` (failed-load
cleanup pops every name from `plugin_module_names`) versus `_api_plugin_unload` (honours
`CANRELOAD`).

**Evidence:** `deletemodule` **verified**: a module named `userplugins.mine.mybaseplugin`
returned `False` and stayed in `sys.modules`, while `userplugins.mine.other` was deleted.
The `CANRELOAD` mismatch is **read**, not run.

**Fix:** Match the skip list on the exact package (the bundled `_baseplugin` package) rather
than a substring; make the failed-load cleanup apply the same `CANRELOAD` rule as unload.

### PS-11: Test plugins with an unloadable layout

**Issue:** [#98](https://github.com/endavis/bastproxy/issues/98) (commented)
**Status:** fixed in the PR for #98; all three test plugins now use the `plugin/` layout and a test checks every discovered plugin imports.
**Location:** `src/bastproxy/plugins/test/cmddec`, `.../test/_sqldb`, `.../test/exception`.

**Evidence (verified):** `plugin.load` returned `plugins.test.cmddec` and
`plugins.test._sqldb` as bad: the loader imports `<package>.plugin` and these have `_plugin.py`.
`plugins.test.exception` is a third case not in #98's description: its `__init__.py` is empty
and the metadata is in the `__init__.py` of its `plugin` package, so it is discovered as
`plugins.test.exception.plugin` and fails on `...exception.plugin.plugin`.

**Fix:** Move all three into the two-level layout, and add a test that every discovered plugin
imports.

### PS-12: Nothing stops unloading a required plugin, and nothing checks API names

**Status:** fixed in the PR for #130; `plugin.unload` refuses required plugins (reload and failed-load cleanup pass `allow_required=True`), and a static test checks that literal API names are registered. It found and fixed `errors.clear`.

**Issue:** [#130](https://github.com/endavis/bastproxy/issues/130)
**Location:** `loader.py` `_api_plugin_unload` (checks `can_reload_f` only);
`PluginInfo.is_required` (used for colouring in the pluginm list).

**Evidence (read):** Bundled core plugins with `can_reload_f` left `True` (for example settings,
log, commands, proxy) can be unloaded by the `unload` command. I did not run it: it would
take the proxy down. Separately, the scan of literal API names (verified, three misses, see
Q5 row 4) shows no check ties call sites to registered names.

**Fix:** Either refuse to unload `is_required` plugins or set `can_reload_f` on the core plugins
that cannot survive it. Add a test that parses `self.api("<literal>")` calls under `src` and
checks the names exist after startup (f-string names excluded).

---

## Other Observations

- **Event definitions are never removed on unload** (verified). Every `ev_<id>_*` event, each
  `watch_<name>` event and each custom event stays with `created_by` set to the unloaded
  plugin; `ev_plugin_save` is "created by" whichever plugin loaded first (in my run
  `plugins.core.clients`). A reload re-adds them, so the effect is memory and a stale owner
  field, not wrong behaviour. This is for the event system audit.
- **Discovery leaves parent packages in `sys.modules`** (verified): after failed loads
  `userplugins.zprobe` stayed. Harmless; `plugin_module_names` covers only the plugin package.
- **`PluginInfo.get_file_data` re-parses every file on every call** (verified: 4 parses on the
  first scan, 4 on the second with no change). The cache lookup reads `oldfiles[parent_dir][name]`
  but entries are stored under `["files"]`, so it never hits. It also keys by the parent
  directory's *name* only, so same-named directories in different parents collide, and it skips
  `__init__.py`, so edits there are never reported as changed. It is called on each load, on
  `help` and on `find_file_by_name`. Filed as [#132](https://github.com/endavis/bastproxy/issues/132); not a correctness problem for load. Fixed in #132: the cache now hits, files are keyed by their path relative to the package, and `__init__.py` files are scanned.
- **Unloading a plugin that others depend on is not blocked** (documented, #97). The dependents
  then fail on their next API call to the unloaded plugin. Unverified whether the `unload`
  command warns; it does not appear to.
- **Static scan limits:** the API-name check covered literal names in namespaces of plugins I
  had loaded, not f-string names and not the unloaded debug and test namespaces.

---

**Document Version:** 1.0
**Last Updated:** 2026-11-03
