# All Documents

Complete index of all documentation, organized by audience and as a full alphabetical list.

> These lists are auto-generated from document frontmatter.
> Run `python tools/generate_doc_toc.py` to update.

## By Audience

### For Users
<!-- BEGIN:audience=users -->
- [Actions](client/actions.md) - Run commands when a line of MUD output matches a regex, with %1 to %9, %* and %<name> references
- [Aliases](client/aliases.md) - Define short names that expand to longer input, with %1 to %9 and %* arguments
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [Doit Tasks Reference](development/doit-tasks-reference.md) - Complete reference for all doit automation tasks
- [GitHub Repository Settings](development/github-repository-settings.md) - Complete reference for all GitHub repository settings the template expects
- [Keeping Up to Date](template/updates.md) - Stay in sync with improvements to the pyproject-template
- [Loop](client/loop.md) - Run a line a number of times, with the counter in the line, through aliases and variables
- [Mapper](client/mapper.md) - Find rooms, show paths and walk to a room with the mapper plugin, which game plugins feed with rooms and exits
- [Mapper System](claude/mapper_system.md) - How the mapper plugin stores the map, finds paths and walks them, and what a game plugin adapter does
- [Migration Guide](template/migration.md) - Migrate existing Python projects to use this template
- [New Project Setup](template/new-project.md) - Create a new Python project from this template
- [Substitutes](client/substitutes.md) - Rewrite text in MUD output before it reaches the client, keeping colour, with plain or regex matching
- [Template Management](template/manage.md) - Unified interface for creating projects, checking updates, and syncing
- [Template Tools Reference](template/tools-reference.md) - Complete reference for all template tools in tools/pyproject_template/
- [Using This Template](template/index.md) - Overview of using pyproject-template for your Python projects
- [Variables](client/variables.md) - Store named values and use them in the lines you type with %{name} references
- [Web Server](web-server.md) - The web plugin serves pages that plugins publish over a small HTTP server, with its settings, commands, security model, and two ways to reach it remotely over TLS
<!-- END:audience=users -->

### For Contributors
<!-- BEGIN:audience=contributors -->
- [Actions](client/actions.md) - Run commands when a line of MUD output matches a regex, with %1 to %9, %* and %<name> references
- [ADR-0001: Terminate MUD telnet protocols at the proxy](decisions/0001-terminate-mud-telnet-protocols-at-the-proxy.md) - bastproxy terminates GMCP, MSDP, MSSP, MCCP and MXP on each link and re-sends them per client, instead of passing protocol bytes through.
- [ADR-0002: User plugins load from BASTPROXY_HOME/plugins under the userplugins import root](decisions/0002-user-plugins-load-from-bastproxy-homeplugins-under-the-userplugins-import-root.md) - User plugins live in BASTPROXY_HOME/plugins, import as userplugins.<package>.<plugin>, share the plugins.<package>.<plugin> ID namespace, and cannot join bundled packages.
- [ADR-0003: Plugins declare dependencies as PLUGIN_DEPENDENCIES metadata](decisions/0003-plugins-declare-dependencies-as-plugin-dependencies-metadata.md) - Plugins declare dependencies as PLUGIN_DEPENDENCIES package metadata read before import; the loader loads and reloads in dependency order and the dependency.add API is removed.
- [ADR-0004: API names are resource-first and cmdq is renamed mudcmds](decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md) - API names take the resource-first form resource.action.qualifier with is/has/exists booleans; plugins.core.cmdq becomes plugins.core.mudcmds; every rename lands at once as a breaking change with no aliases.
- [ADR-0005: Record tracking: scope, change contents, retention and cost](decisions/0005-record-tracking-scope-change-contents-retention-and-cost.md) - Records track text lines and decoded protocol messages with old value, new value, actor, time and parent; data holders become tracked containers, retention keeps the last N root trees, and capture costs at most 50 us per line created and 20 us per change with stacks off.
- [ADR-0006: Records adapt pydatatracker containers and locked writes raise RuntimeError](decisions/0006-records-adapt-pydatatracker-containers-and-locked-writes-raise-runtimeerror.md) - Records adapt pydatatracker containers through a mixin and a read-only update view; a locked NetworkDataLine or NetworkData raises RuntimeError on writes; the actor comes from a context variable; a benchmark gate caps 75 us per line created and 20 us per change locally and on main, and fails a pull request that is more than 25% slower than its base on the same runner.
- [ADR-0007: Triggers match each trigger's own regex in priority order](decisions/0007-triggers-match-each-triggers-own-regex-in-priority-order.md) - Each trigger matches its own compiled regex, ordered by priority then order added, instead of one combined alternation; stopevaluating stops later triggers, built-ins are raised only with a listener, and the measured per-line and add costs are recorded.
- [ADR-0008: The colors tokenizer is the single definition of the colour-code syntax](decisions/0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md) - The colors plugin has one tokenizer that defines the colour-code syntax, and other plugins reach it only through the colorcode.to.tokens API, never by import.
- [ADR-0009: Display width is measured with wcwidth in one framework helper](decisions/0009-display-width-is-measured-with-wcwidth-in-one-framework-helper.md) - Display width is the wcwidth of visible text, measured in one framework helper that plugins and argp share; control characters count zero and wrapping works on graphemes.
- [ADR-0010: On-prompt triggers defer their events to the next prompt](decisions/0010-on-prompt-triggers-defer-their-events-to-the-next-prompt.md) - A trigger added with on_prompt=True matches its line at once but holds its event until the next GA/EOR prompt line, falling back to immediate firing for a MUD that sends no prompts and to a timeout when the prompt is late.
- [ADR-0011: Plugins wait for MUD output through per-waiter queues on the triggers plugin](decisions/0011-plugins-wait-for-mud-output-through-per-waiter-queues-on-the-triggers-plugin.md) - Plugins wait for MUD output through per-waiter line queues in the triggers plugin, reached through awaitable plugins.core.triggers APIs that always clean up and log instead of raising.
- [ADR-0012: Plugins own telnet options the core does not handle through a generic hook](decisions/0012-plugins-own-telnet-options-the-core-does-not-handle-through-a-generic-hook.md) - A plugin registers a telnet option number and owns its negotiation, events and subnegotiations through a hook on the recording telnet writer, while the core interprets no payload.
- [ADR-0013: Plugins are discovered from installed packages through the bastproxy.plugins entry-point group](decisions/0013-plugins-are-discovered-from-installed-packages-through-the-bastproxyplugins-entry-point-group.md) - Installed packages register plugins in the bastproxy.plugins entry-point group; the entry name sets the plugin ID, and bundled beats user beats installed.
- [ADR-0014: Plugins add sqldb databases through database.add with plain-data definitions](decisions/0014-plugins-add-sqldb-databases-through-databaseadd-with-plain-data-definitions.md) - A plugin gets a sqldb database from plugins.core.sqldb:database.add with dicts for tables and migrations, instead of subclassing Sqldb and calling postinit.
- [ADR-0015: Settings are keyed per plugin and a name index resolves pset](decisions/0015-settings-are-keyed-per-plugin-and-a-name-index-resolves-pset.md) - Settings are keyed by plugin and name, so plugins may reuse a name, and a name index resolves a bare pset only when one plugin owns the name.
- [ADR-0016: User variables expand %{name} references on the input path](decisions/0016-user-variables-expand-name-references-on-the-input-path.md) - User variables are %{name} references expanded in one pass on ev_to_mud_data_modify at priority 60, with an API for aliases, actions and loop.
- [ADR-0017: User aliases expand the first word on the input path at priority 55](decisions/0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md) - Aliases expand the first word of client input at priority 55, in place or by re-sending, with %1-%9 and %* arguments and a depth bound of 10.
- [ADR-0018: User actions substitute trigger groups into commands and escape matched text](decisions/0018-user-actions-substitute-trigger-groups-into-commands-and-escape-matched-text.md) - Actions put trigger groups into commands as %1-%9, %* and %<name>, and escape matched MUD text per part.
- [ADR-0019: User substitutions rewrite MUD lines after triggers and keep colour codes](decisions/0019-user-substitutions-rewrite-mud-lines-after-triggers-and-keep-colour-codes.md) - Substitutions rewrite MUD lines at priority 60, after triggers, rebuilding colour codes token by token.
- [ADR-0020: Client sends made while MUD data is processed follow its lines](decisions/0020-client-sends-made-while-mud-data-is-processed-follow-its-lines.md) - Client sends made while MUD data is processed are held and sent after the data's last line, in the order made.
- [ADR-0021: The mapper owns the map and walking, and game plugins adapt it through callbacks](decisions/0021-the-mapper-owns-the-map-and-walking-and-game-plugins-adapt-it-through-callbacks.md) - The mapper plugin owns the map, pathfinding and walking; game plugins feed it rooms and register requirement and movement callbacks.
- [ADR-0022: The web plugin serves token links and session-gated plugin routes over a GET-only standard-library server](decisions/0022-the-web-plugin-serves-token-links-and-session-gated-plugin-routes-over-a-get-only-standard-library-server.md) - The web plugin runs a GET-only standard-library HTTP server; plugins publish one-off token links and session-gated routes, tables and one static script.
- [ADR-0023: User plugin packages import under their own name](decisions/0023-user-plugin-packages-import-under-their-own-name.md) - Each user plugin package folder imports under its own name, unless the name is unusable, installed or already importable.
- [ADR-0024: Plugins add commands under another plugin's name only when that plugin accepts them](decisions/0024-plugins-add-commands-under-another-plugins-name-only-when-that-plugin-accepts-them.md) - A plugin may add commands under another plugin's name through command.add.for.plugin, only when the host sets accepts_command_extensions_f.
- [ADR-9001: Use uv for package management](decisions/9001-use-uv-for-package-management.md) - Use uv for dependency management, virtual environments and package installation
- [ADR-9002: Use doit for task automation](decisions/9002-use-doit-for-task-automation.md) - Use doit as the task runner for testing, linting, building and other routine operations
- [ADR-9003: Use ruff for linting and formatting](decisions/9003-use-ruff-for-linting-and-formatting.md) - Use ruff as the one tool for linting and formatting, in place of flake8, black and isort
- [ADR-9004: Auto-discover doit tasks from modules](decisions/9004-auto-discover-doit-tasks.md) - Import every task_* function under tools/doit/ automatically instead of listing each one in dodo.py
- [ADR-9005: AI agent command restrictions via hooks](decisions/9005-ai-agent-command-restrictions.md) - Block dangerous commands such as --force, --admin and --no-verify at the tool level, through each AI agent's hooks
- [ADR-9006: Merge-gate workflow requiring ready-to-merge label](decisions/9006-merge-gate-workflow.md) - A merge-gate workflow, enforced by branch protection, keeps a PR from merging until it carries the ready-to-merge label
- [ADR-9007: Use mypy for static type checking](decisions/9007-use-mypy-for-type-checking.md) - Use mypy in strict mode, run by doit check, the pre-commit hooks and CI
- [ADR-9008: PR-based development workflow](decisions/9008-pr-based-development-workflow.md) - Every change goes Issue → Branch → Commit → PR → Merge, and nothing is committed to main directly
- [ADR-9009: Use pre-commit hooks for quality gates](decisions/9009-use-pre-commit-hooks-for-quality-gates.md) - Run quality and safety checks through the pre-commit framework before every commit
- [ADR-9010: Use conventional commits format](decisions/9010-use-conventional-commits-format.md) - Write every commit message, merge commits included, in the Conventional Commits format
- [ADR-9011: Use pytest for testing](decisions/9011-use-pytest-for-testing.md) - Use pytest, with pytest-xdist for parallel runs and pytest-cov for coverage
- [ADR-9012: Use mkdocs with Material theme for documentation](decisions/9012-use-mkdocs-with-material-theme-for-documentation.md) - Build the documentation with MkDocs and the Material theme, and host it on GitHub Pages
- [ADR-9013: Python version support policy with bookend CI strategy](decisions/9013-python-version-support-policy.md) - Support the last three Python versions, testing the oldest and newest on every PR and older ones on demand
- [ADR-9014: Use click for application CLI](decisions/9014-use-click-for-application-cli.md) - Build the package's user-facing command-line interface with click, registered as a console script
- [ADR-9015: install_tools framework: archive extraction and custom URLs](decisions/9015-install-tools-framework-archive-extraction-and-custom-urls.md) - Extend the install_tools framework with archive extraction and custom download URLs, keeping it backward compatible
- [ADR-9016: Unify ADR directories under docs/decisions](decisions/9016-unify-adr-directories.md) - Keep every ADR in docs/decisions/, numbering template decisions 9XXX and project decisions from 0001
- [ADR-9017: Template tooling and its tests are template-owned](decisions/9017-template-tooling-and-its-tests-are-template-owned.md) - A test under tests/template/ is template-owned when its target does not survive configuration
- [ADR-9018: AGENTS.md carries only shared, always-on instructions](decisions/9018-agentsmd-carries-only-shared-always-on-instructions.md) - Content belongs in AGENTS.md only when it holds for every agent and must be in effect at all times
- [ADR-9019: The dangerous-command hook is a guardrail, not a security boundary](decisions/9019-the-dangerous-command-hook-is-a-guardrail-not-a-security-boundary.md) - The dangerous-command hook guards against a non-adversarial agent, not a determined one
- [ADR-9020: A template version is a commit SHA](decisions/9020-a-template-version-is-a-commit-sha.md) - A template version is a commit SHA, not a release tag or a branch name
- [ADR-9021: A PR may target the unmerged branch it builds on](decisions/9021-a-pr-may-target-the-unmerged-branch-it-builds-on.md) - A PR may target the unmerged branch it builds on, but it merges only into main
- [ADR-9022: Worktrees live in worktrees/, each with its own environment](decisions/9022-worktrees-live-in-worktrees-each-with-its-own-environment.md) - A worktree lives in worktrees/<branch>, is created with doit worktree, and has its own environment
- [ADR-9023: Shared workflow skills are written once in .agents/skills/ and generated for Claude](decisions/9023-shared-workflow-skills-live-in-agents-skills-generated-for-claude.md) - Shared workflow skills live once in .agents/skills/ and doit skills_sync generates Claude's copy
- [ADR-9024: One implement-issue skill takes an issue to a green PR](decisions/9024-one-implement-issue-skill-takes-an-issue-to-a-green-pr.md) - One shared implement-issue skill replaces /claude:plan, /claude:implement, /ghi-finalize and the per-agent plan/implement matrix
- [ADR-9025: Delegated agents receive GitHub data from the host and run without network](decisions/9025-delegated-agents-receive-github-data-from-the-host-and-run-without-network.md) - The host fetches GitHub issue/PR data with doit delegation_context and writes it to files, so delegated agent prompts read those instead of calling gh
- [ADR-9026: Doc-scanning tests honor sync-exclude.toml and discover markdown via git](decisions/9026-doc-scanning-tests-honor-sync-excludetoml-and-discover-markdown-via-git.md) - The shipped doc-link and doc-path tests discover markdown via git ls-files instead of rglob, and skip a target excluded in sync-exclude.toml
- [ADR-9027: implement-issue works in a per-issue worktree](decisions/9027-implement-issue-works-in-a-per-issue-worktree.md) - implement-issue always works in a per-issue worktree under worktrees/, so several issues can run at once
- [ADR-9028: implement-issues runs issues in parallel background agents](decisions/9028-implement-issues-runs-issues-in-parallel-background-agents.md) - implement-issues runs implement-issue for several issues at once, one worktree and one nested-capable background agent each, capped at 2 by default
- [ADR-9029: implement-issue host plan and Coder checking budget](decisions/9029-implement-issue-host-plan-and-coder-checking-budget.md) - The implement-issue host may write the plan after posting findings, with a review pass, and the Coder runs a bounded set of checks while Step 5 runs the one full doit check
- [ADR-9030: Cross-agent roles resolve through a per-user config](decisions/9030-cross-agent-roles-resolve-through-a-per-user-config.md) - Cross-agent roles resolve through one doit task reading a layered per-user config, subagent first, with Codex subagents taking a model and effort and Copilot subagent models resolving to the CLI
- [ADR-9031: A project adds rebuildable names for worktree removal in pyproject.toml](decisions/9031-a-project-adds-rebuildable-names-for-worktree-removal-in-pyprojecttoml.md) - doit pr_merge reads extra rebuildable names from [tool.pyproject-template.worktree] in the main checkout's pyproject.toml, rejecting over-broad names
- [Agent Roles and Models](development/ai/agent-roles.md) - How to choose which CLI and model runs each cross-agent role (plan, plan review, code, review, adversarial review) from a per-user config
- [AI Agent Setup Guide](development/AI_SETUP.md) - Configure Claude, Copilot, Codex, and Antigravity for this project
- [AI Agent Token-Efficiency Add-Ons](development/ai/token-efficiency-add-ons.md) - Opt-in catalogue of external tools for reducing token usage in Claude Code sessions
- [AI Architectural Conventions](development/ai/architectural-conventions.md) - Imperative-form architectural rules AI agents must follow when generating code
- [AI Command Blocking](development/ai/command-blocking.md) - Hooks that block dangerous commands from AI agents
- [AI Enforcement Principles](development/ai/enforcement-principles.md) - How we enforce AI agent behavior in code and settings
- [Aliases](client/aliases.md) - Define short names that expand to longer input, with %1 to %9 and %* arguments
- [API System](claude/api_system.md) - The central API registry plugins use to publish and call functions
- [API System Analysis and Findings](claude/api_system_findings.md) - Audit of API registration, removal, call cost, caller tracking and the patterns the API system uses, with defects and a patterns review
- [Architecture Decision Records](decisions/README.md) - What an ADR is, the two numbering series, the ADR format, and how to create one with doit adr
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [bastproxy System Documentation](claude/README.md) - Index of the bastproxy architecture notes and how the systems fit together
- [CI/CD Testing Guide](development/ci-cd-testing.md) - GitHub Actions pipelines for testing, linting, and coverage
- [Claude Code Statusline](development/ai/statusline.md) - Custom statusline showing git branch, Python version, and project info
- [Colour System](claude/colors_system.md) - The colour-code syntax, the one tokenizer that defines it, and how conversion, stripping, validation, html and width are built on it
- [Colour System Analysis and Findings](claude/colors_findings.md) - Audit of the colors plugin - its APIs and callers, the colour-code conversion bugs reproduced on main, why they happen, and the recommended single-tokenizer design
- [Command System](claude/command_system.md) - How client commands are parsed, dispatched and documented
- [Command System Analysis and Findings](claude/command_system_findings.md) - Audit of the commands plugin - how a client line becomes a command, state consistency across add, reload and unload, failure handling, test coverage, docs accuracy and patterns, with defects and a patterns review
- [Cross-Agent Delegation Matrix](development/ai/cross-agent-delegation.md) - Commands that let any supported AI CLI hand a review task to any other; plan and implement are handled by the shared implement-issue skill instead
- [Data Flow](claude/data_flow.md) - How network data moves between MUD servers and clients through the proxy
- [Debugging](development/debugging.md) - Tracing bastproxy's event and plugin flow with hunter, without adding log lines
- [Dependabot Auto-merge](development/dependabot-automerge.md) - How the dependabot auto-merge workflow evaluates, enables, and skips PRs
- [Doit Tasks Reference](development/doit-tasks-reference.md) - Complete reference for all doit automation tasks
- [Event System](claude/event_system.md) - Priority-based event registration and dispatch between plugins
- [Event System Analysis and Findings](claude/event_system_findings.md) - Audit of the event system - the status of the earlier findings, plugin unload, priority ordering and failing callbacks, cost, test coverage, docs accuracy and patterns, with defects and a patterns review
- [First 5 Minutes with an AI Agent](development/ai/first-5-minutes.md) - Narrative walkthrough of the AI agent workflow from issue to merge
- [GitHub Repository Settings](development/github-repository-settings.md) - Complete reference for all GitHub repository settings the template expects
- [install_tools Framework](development/install-tools-framework.md) - Reusable framework for installing developer tools from GitHub releases or other URLs into ~/.local/bin
- [Logging System](claude/logging_system.md) - How bastproxy code logs through standard-library loggers, how thresholds and handlers route messages, and how to migrate from LogRecord
- [Loop](client/loop.md) - Run a line a number of times, with the counter in the line, through aliases and variables
- [LSP Tool and Diagnostic Noise](development/ai/lsp-tool.md) - What the LSP tool gives an AI agent, why pyright diagnostics arrive stale, and the two opt-outs agents can flip on themselves
- [Mapper](client/mapper.md) - Find rooms, show paths and walk to a room with the mapper plugin, which game plugins feed with rooms and exits
- [Mapper System](claude/mapper_system.md) - How the mapper plugin stores the map, finds paths and walks them, and what a game plugin adapter does
- [Network Layer Analysis and Findings](claude/network_system_findings.md) - Audit of the network layer and its use of telnetlib3 - private API, deprecations, reimplemented features, patches, the 5.0.2 release, test coverage, the status of the open network issues and patterns, with defects and a patterns review
- [Optional Extensions](development/extensions.md) - Additional tools and extensions for testing, security, and more
- [Per-Stack Rule Files](development/ai/rule-files.md) - How to author, load and mirror the short self-check rule files in .claude/rules/
- [Plugin Developer Guide](plugin-developer-guide.md) - A task-oriented path for plugin authors, covering communication, plugin structure and reloading, hooks and events, commands and triggers
- [Plugin System](claude/plugin_system.md) - Plugin structure, metadata, loading, reloading and lifecycle
- [Plugin System Analysis and Findings](claude/plugin_system_findings.md) - Audit of plugin discovery, loading, unloading, reloading, hooks and BasePlugin patching, with defects and a patterns review
- [Python Project Coding Standards](development/coding-standards.md) - Guidelines for exceptions, typing, structure, testing, and documentation
- [Record System](claude/record_system.md) - Records that track data and operations, their lifecycle and relationships
- [Record System Analysis and Findings](claude/record_system_findings.md) - Audit of record mutation tracking, the parent/child tree, retention and memory, test coverage, docs accuracy and the patterns the record system uses, with defects and a patterns review
- [Release Automation & Security](development/release-and-automation.md) - Automated versioning, release management, and security tooling
- [Review Focus Areas](development/ai/review-focus-areas.md) - Checklists for the errors, tests, types and comments focus areas available to every review and adversarial-review surface
- [Ruff Auto-Fix on Edit Hook](development/ai/ruff-fix-hook.md) - PostToolUse hook that runs ruff --fix on edited Python files
- [Settings System](claude/settings_system.md) - Per-plugin settings, persistence and change events
- [Slash Commands and Workflows](development/ai/slash-commands.md) - Reference for the slash commands and dual-agent workflow this project ships with
- [SQLite Database System](claude/sqldb_system.md) - How plugins store data in SQLite through the sqldb plugin
- [Substitutes](client/substitutes.md) - Rewrite text in MUD output before it reaches the client, keeping colour, with plain or regex matching
- [Template Tools Reference](template/tools-reference.md) - Complete reference for all template tools in tools/pyproject_template/
- [Timers System](claude/timers_system.md) - Scheduling recurring and one-shot timers from plugins
- [Tooling Roles and Architectural Boundaries](development/tooling-roles.md) - What each tool is for, who uses it, and where runtime code ends and dev tooling begins
- [Triggers System](claude/triggers_system.md) - Regex matching on MUD output that raises events for plugins to handle
- [Triggers System Analysis and Findings](claude/triggers_system_findings.md) - Audit of the triggers plugin - how a MUD line reaches a trigger, state consistency, failure handling, cost, test coverage, docs accuracy, patterns and a design assessment with alternatives measured
- [Utils Plugin](claude/utils_system.md) - The formatting, time and value-conversion APIs of plugins.core.utils
- [Variables](client/variables.md) - Store named values and use them in the lines you type with %{name} references
- [Web Server](web-server.md) - The web plugin serves pages that plugins publish over a small HTTP server, with its settings, commands, security model, and two ways to reach it remotely over TLS
- [Web System](claude/web_system.md) - How a plugin publishes a page through the web plugin's web.page.add API
<!-- END:audience=contributors -->

### For AI Agents
<!-- BEGIN:audience=ai-agents -->
- [Agent Roles and Models](development/ai/agent-roles.md) - How to choose which CLI and model runs each cross-agent role (plan, plan review, code, review, adversarial review) from a per-user config
- [AI Agent Setup Guide](development/AI_SETUP.md) - Configure Claude, Copilot, Codex, and Antigravity for this project
- [AI Agent Sync Checklist](template/ai-sync-checklist.md) - Step-by-step checklist for AI agents synchronizing downstream projects with pyproject-template
- [AI Agent Token-Efficiency Add-Ons](development/ai/token-efficiency-add-ons.md) - Opt-in catalogue of external tools for reducing token usage in Claude Code sessions
- [AI Architectural Conventions](development/ai/architectural-conventions.md) - Imperative-form architectural rules AI agents must follow when generating code
- [AI Command Blocking](development/ai/command-blocking.md) - Hooks that block dangerous commands from AI agents
- [AI Enforcement Principles](development/ai/enforcement-principles.md) - How we enforce AI agent behavior in code and settings
- [API System](claude/api_system.md) - The central API registry plugins use to publish and call functions
- [API System Analysis and Findings](claude/api_system_findings.md) - Audit of API registration, removal, call cost, caller tracking and the patterns the API system uses, with defects and a patterns review
- [Architecture Decision Records](decisions/README.md) - What an ADR is, the two numbering series, the ADR format, and how to create one with doit adr
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [bastproxy System Documentation](claude/README.md) - Index of the bastproxy architecture notes and how the systems fit together
- [Claude Code Statusline](development/ai/statusline.md) - Custom statusline showing git branch, Python version, and project info
- [Colour System](claude/colors_system.md) - The colour-code syntax, the one tokenizer that defines it, and how conversion, stripping, validation, html and width are built on it
- [Colour System Analysis and Findings](claude/colors_findings.md) - Audit of the colors plugin - its APIs and callers, the colour-code conversion bugs reproduced on main, why they happen, and the recommended single-tokenizer design
- [Command System](claude/command_system.md) - How client commands are parsed, dispatched and documented
- [Command System Analysis and Findings](claude/command_system_findings.md) - Audit of the commands plugin - how a client line becomes a command, state consistency across add, reload and unload, failure handling, test coverage, docs accuracy and patterns, with defects and a patterns review
- [Cross-Agent Delegation Matrix](development/ai/cross-agent-delegation.md) - Commands that let any supported AI CLI hand a review task to any other; plan and implement are handled by the shared implement-issue skill instead
- [Data Flow](claude/data_flow.md) - How network data moves between MUD servers and clients through the proxy
- [Debugging](development/debugging.md) - Tracing bastproxy's event and plugin flow with hunter, without adding log lines
- [Event System](claude/event_system.md) - Priority-based event registration and dispatch between plugins
- [Event System Analysis and Findings](claude/event_system_findings.md) - Audit of the event system - the status of the earlier findings, plugin unload, priority ordering and failing callbacks, cost, test coverage, docs accuracy and patterns, with defects and a patterns review
- [First 5 Minutes with an AI Agent](development/ai/first-5-minutes.md) - Narrative walkthrough of the AI agent workflow from issue to merge
- [Logging System](claude/logging_system.md) - How bastproxy code logs through standard-library loggers, how thresholds and handlers route messages, and how to migrate from LogRecord
- [LSP Tool and Diagnostic Noise](development/ai/lsp-tool.md) - What the LSP tool gives an AI agent, why pyright diagnostics arrive stale, and the two opt-outs agents can flip on themselves
- [Network Layer Analysis and Findings](claude/network_system_findings.md) - Audit of the network layer and its use of telnetlib3 - private API, deprecations, reimplemented features, patches, the 5.0.2 release, test coverage, the status of the open network issues and patterns, with defects and a patterns review
- [Plugin System](claude/plugin_system.md) - Plugin structure, metadata, loading, reloading and lifecycle
- [Plugin System Analysis and Findings](claude/plugin_system_findings.md) - Audit of plugin discovery, loading, unloading, reloading, hooks and BasePlugin patching, with defects and a patterns review
- [Record System](claude/record_system.md) - Records that track data and operations, their lifecycle and relationships
- [Record System Analysis and Findings](claude/record_system_findings.md) - Audit of record mutation tracking, the parent/child tree, retention and memory, test coverage, docs accuracy and the patterns the record system uses, with defects and a patterns review
- [Review Focus Areas](development/ai/review-focus-areas.md) - Checklists for the errors, tests, types and comments focus areas available to every review and adversarial-review surface
- [Ruff Auto-Fix on Edit Hook](development/ai/ruff-fix-hook.md) - PostToolUse hook that runs ruff --fix on edited Python files
- [Settings System](claude/settings_system.md) - Per-plugin settings, persistence and change events
- [Slash Commands and Workflows](development/ai/slash-commands.md) - Reference for the slash commands and dual-agent workflow this project ships with
- [SQLite Database System](claude/sqldb_system.md) - How plugins store data in SQLite through the sqldb plugin
- [Timers System](claude/timers_system.md) - Scheduling recurring and one-shot timers from plugins
- [Tooling Roles and Architectural Boundaries](development/tooling-roles.md) - What each tool is for, who uses it, and where runtime code ends and dev tooling begins
- [Triggers System](claude/triggers_system.md) - Regex matching on MUD output that raises events for plugins to handle
- [Triggers System Analysis and Findings](claude/triggers_system_findings.md) - Audit of the triggers plugin - how a MUD line reaches a trigger, state consistency, failure handling, cost, test coverage, docs accuracy, patterns and a design assessment with alternatives measured
- [Utils Plugin](claude/utils_system.md) - The formatting, time and value-conversion APIs of plugins.core.utils
- [Web System](claude/web_system.md) - How a plugin publishes a page through the web plugin's web.page.add API
<!-- END:audience=ai-agents -->

## Complete Index
<!-- BEGIN:all -->
- [Actions](client/actions.md) - Run commands when a line of MUD output matches a regex, with %1 to %9, %* and %<name> references
- [ADR-0001: Terminate MUD telnet protocols at the proxy](decisions/0001-terminate-mud-telnet-protocols-at-the-proxy.md) - bastproxy terminates GMCP, MSDP, MSSP, MCCP and MXP on each link and re-sends them per client, instead of passing protocol bytes through.
- [ADR-0002: User plugins load from BASTPROXY_HOME/plugins under the userplugins import root](decisions/0002-user-plugins-load-from-bastproxy-homeplugins-under-the-userplugins-import-root.md) - User plugins live in BASTPROXY_HOME/plugins, import as userplugins.<package>.<plugin>, share the plugins.<package>.<plugin> ID namespace, and cannot join bundled packages.
- [ADR-0003: Plugins declare dependencies as PLUGIN_DEPENDENCIES metadata](decisions/0003-plugins-declare-dependencies-as-plugin-dependencies-metadata.md) - Plugins declare dependencies as PLUGIN_DEPENDENCIES package metadata read before import; the loader loads and reloads in dependency order and the dependency.add API is removed.
- [ADR-0004: API names are resource-first and cmdq is renamed mudcmds](decisions/0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md) - API names take the resource-first form resource.action.qualifier with is/has/exists booleans; plugins.core.cmdq becomes plugins.core.mudcmds; every rename lands at once as a breaking change with no aliases.
- [ADR-0005: Record tracking: scope, change contents, retention and cost](decisions/0005-record-tracking-scope-change-contents-retention-and-cost.md) - Records track text lines and decoded protocol messages with old value, new value, actor, time and parent; data holders become tracked containers, retention keeps the last N root trees, and capture costs at most 50 us per line created and 20 us per change with stacks off.
- [ADR-0006: Records adapt pydatatracker containers and locked writes raise RuntimeError](decisions/0006-records-adapt-pydatatracker-containers-and-locked-writes-raise-runtimeerror.md) - Records adapt pydatatracker containers through a mixin and a read-only update view; a locked NetworkDataLine or NetworkData raises RuntimeError on writes; the actor comes from a context variable; a benchmark gate caps 75 us per line created and 20 us per change locally and on main, and fails a pull request that is more than 25% slower than its base on the same runner.
- [ADR-0007: Triggers match each trigger's own regex in priority order](decisions/0007-triggers-match-each-triggers-own-regex-in-priority-order.md) - Each trigger matches its own compiled regex, ordered by priority then order added, instead of one combined alternation; stopevaluating stops later triggers, built-ins are raised only with a listener, and the measured per-line and add costs are recorded.
- [ADR-0008: The colors tokenizer is the single definition of the colour-code syntax](decisions/0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md) - The colors plugin has one tokenizer that defines the colour-code syntax, and other plugins reach it only through the colorcode.to.tokens API, never by import.
- [ADR-0009: Display width is measured with wcwidth in one framework helper](decisions/0009-display-width-is-measured-with-wcwidth-in-one-framework-helper.md) - Display width is the wcwidth of visible text, measured in one framework helper that plugins and argp share; control characters count zero and wrapping works on graphemes.
- [ADR-0010: On-prompt triggers defer their events to the next prompt](decisions/0010-on-prompt-triggers-defer-their-events-to-the-next-prompt.md) - A trigger added with on_prompt=True matches its line at once but holds its event until the next GA/EOR prompt line, falling back to immediate firing for a MUD that sends no prompts and to a timeout when the prompt is late.
- [ADR-0011: Plugins wait for MUD output through per-waiter queues on the triggers plugin](decisions/0011-plugins-wait-for-mud-output-through-per-waiter-queues-on-the-triggers-plugin.md) - Plugins wait for MUD output through per-waiter line queues in the triggers plugin, reached through awaitable plugins.core.triggers APIs that always clean up and log instead of raising.
- [ADR-0012: Plugins own telnet options the core does not handle through a generic hook](decisions/0012-plugins-own-telnet-options-the-core-does-not-handle-through-a-generic-hook.md) - A plugin registers a telnet option number and owns its negotiation, events and subnegotiations through a hook on the recording telnet writer, while the core interprets no payload.
- [ADR-0013: Plugins are discovered from installed packages through the bastproxy.plugins entry-point group](decisions/0013-plugins-are-discovered-from-installed-packages-through-the-bastproxyplugins-entry-point-group.md) - Installed packages register plugins in the bastproxy.plugins entry-point group; the entry name sets the plugin ID, and bundled beats user beats installed.
- [ADR-0014: Plugins add sqldb databases through database.add with plain-data definitions](decisions/0014-plugins-add-sqldb-databases-through-databaseadd-with-plain-data-definitions.md) - A plugin gets a sqldb database from plugins.core.sqldb:database.add with dicts for tables and migrations, instead of subclassing Sqldb and calling postinit.
- [ADR-0015: Settings are keyed per plugin and a name index resolves pset](decisions/0015-settings-are-keyed-per-plugin-and-a-name-index-resolves-pset.md) - Settings are keyed by plugin and name, so plugins may reuse a name, and a name index resolves a bare pset only when one plugin owns the name.
- [ADR-0016: User variables expand %{name} references on the input path](decisions/0016-user-variables-expand-name-references-on-the-input-path.md) - User variables are %{name} references expanded in one pass on ev_to_mud_data_modify at priority 60, with an API for aliases, actions and loop.
- [ADR-0017: User aliases expand the first word on the input path at priority 55](decisions/0017-user-aliases-expand-the-first-word-on-the-input-path-at-priority-55.md) - Aliases expand the first word of client input at priority 55, in place or by re-sending, with %1-%9 and %* arguments and a depth bound of 10.
- [ADR-0018: User actions substitute trigger groups into commands and escape matched text](decisions/0018-user-actions-substitute-trigger-groups-into-commands-and-escape-matched-text.md) - Actions put trigger groups into commands as %1-%9, %* and %<name>, and escape matched MUD text per part.
- [ADR-0019: User substitutions rewrite MUD lines after triggers and keep colour codes](decisions/0019-user-substitutions-rewrite-mud-lines-after-triggers-and-keep-colour-codes.md) - Substitutions rewrite MUD lines at priority 60, after triggers, rebuilding colour codes token by token.
- [ADR-0020: Client sends made while MUD data is processed follow its lines](decisions/0020-client-sends-made-while-mud-data-is-processed-follow-its-lines.md) - Client sends made while MUD data is processed are held and sent after the data's last line, in the order made.
- [ADR-0021: The mapper owns the map and walking, and game plugins adapt it through callbacks](decisions/0021-the-mapper-owns-the-map-and-walking-and-game-plugins-adapt-it-through-callbacks.md) - The mapper plugin owns the map, pathfinding and walking; game plugins feed it rooms and register requirement and movement callbacks.
- [ADR-0022: The web plugin serves token links and session-gated plugin routes over a GET-only standard-library server](decisions/0022-the-web-plugin-serves-token-links-and-session-gated-plugin-routes-over-a-get-only-standard-library-server.md) - The web plugin runs a GET-only standard-library HTTP server; plugins publish one-off token links and session-gated routes, tables and one static script.
- [ADR-0023: User plugin packages import under their own name](decisions/0023-user-plugin-packages-import-under-their-own-name.md) - Each user plugin package folder imports under its own name, unless the name is unusable, installed or already importable.
- [ADR-0024: Plugins add commands under another plugin's name only when that plugin accepts them](decisions/0024-plugins-add-commands-under-another-plugins-name-only-when-that-plugin-accepts-them.md) - A plugin may add commands under another plugin's name through command.add.for.plugin, only when the host sets accepts_command_extensions_f.
- [ADR-9001: Use uv for package management](decisions/9001-use-uv-for-package-management.md) - Use uv for dependency management, virtual environments and package installation
- [ADR-9002: Use doit for task automation](decisions/9002-use-doit-for-task-automation.md) - Use doit as the task runner for testing, linting, building and other routine operations
- [ADR-9003: Use ruff for linting and formatting](decisions/9003-use-ruff-for-linting-and-formatting.md) - Use ruff as the one tool for linting and formatting, in place of flake8, black and isort
- [ADR-9004: Auto-discover doit tasks from modules](decisions/9004-auto-discover-doit-tasks.md) - Import every task_* function under tools/doit/ automatically instead of listing each one in dodo.py
- [ADR-9005: AI agent command restrictions via hooks](decisions/9005-ai-agent-command-restrictions.md) - Block dangerous commands such as --force, --admin and --no-verify at the tool level, through each AI agent's hooks
- [ADR-9006: Merge-gate workflow requiring ready-to-merge label](decisions/9006-merge-gate-workflow.md) - A merge-gate workflow, enforced by branch protection, keeps a PR from merging until it carries the ready-to-merge label
- [ADR-9007: Use mypy for static type checking](decisions/9007-use-mypy-for-type-checking.md) - Use mypy in strict mode, run by doit check, the pre-commit hooks and CI
- [ADR-9008: PR-based development workflow](decisions/9008-pr-based-development-workflow.md) - Every change goes Issue → Branch → Commit → PR → Merge, and nothing is committed to main directly
- [ADR-9009: Use pre-commit hooks for quality gates](decisions/9009-use-pre-commit-hooks-for-quality-gates.md) - Run quality and safety checks through the pre-commit framework before every commit
- [ADR-9010: Use conventional commits format](decisions/9010-use-conventional-commits-format.md) - Write every commit message, merge commits included, in the Conventional Commits format
- [ADR-9011: Use pytest for testing](decisions/9011-use-pytest-for-testing.md) - Use pytest, with pytest-xdist for parallel runs and pytest-cov for coverage
- [ADR-9012: Use mkdocs with Material theme for documentation](decisions/9012-use-mkdocs-with-material-theme-for-documentation.md) - Build the documentation with MkDocs and the Material theme, and host it on GitHub Pages
- [ADR-9013: Python version support policy with bookend CI strategy](decisions/9013-python-version-support-policy.md) - Support the last three Python versions, testing the oldest and newest on every PR and older ones on demand
- [ADR-9014: Use click for application CLI](decisions/9014-use-click-for-application-cli.md) - Build the package's user-facing command-line interface with click, registered as a console script
- [ADR-9015: install_tools framework: archive extraction and custom URLs](decisions/9015-install-tools-framework-archive-extraction-and-custom-urls.md) - Extend the install_tools framework with archive extraction and custom download URLs, keeping it backward compatible
- [ADR-9016: Unify ADR directories under docs/decisions](decisions/9016-unify-adr-directories.md) - Keep every ADR in docs/decisions/, numbering template decisions 9XXX and project decisions from 0001
- [ADR-9017: Template tooling and its tests are template-owned](decisions/9017-template-tooling-and-its-tests-are-template-owned.md) - A test under tests/template/ is template-owned when its target does not survive configuration
- [ADR-9018: AGENTS.md carries only shared, always-on instructions](decisions/9018-agentsmd-carries-only-shared-always-on-instructions.md) - Content belongs in AGENTS.md only when it holds for every agent and must be in effect at all times
- [ADR-9019: The dangerous-command hook is a guardrail, not a security boundary](decisions/9019-the-dangerous-command-hook-is-a-guardrail-not-a-security-boundary.md) - The dangerous-command hook guards against a non-adversarial agent, not a determined one
- [ADR-9020: A template version is a commit SHA](decisions/9020-a-template-version-is-a-commit-sha.md) - A template version is a commit SHA, not a release tag or a branch name
- [ADR-9021: A PR may target the unmerged branch it builds on](decisions/9021-a-pr-may-target-the-unmerged-branch-it-builds-on.md) - A PR may target the unmerged branch it builds on, but it merges only into main
- [ADR-9022: Worktrees live in worktrees/, each with its own environment](decisions/9022-worktrees-live-in-worktrees-each-with-its-own-environment.md) - A worktree lives in worktrees/<branch>, is created with doit worktree, and has its own environment
- [ADR-9023: Shared workflow skills are written once in .agents/skills/ and generated for Claude](decisions/9023-shared-workflow-skills-live-in-agents-skills-generated-for-claude.md) - Shared workflow skills live once in .agents/skills/ and doit skills_sync generates Claude's copy
- [ADR-9024: One implement-issue skill takes an issue to a green PR](decisions/9024-one-implement-issue-skill-takes-an-issue-to-a-green-pr.md) - One shared implement-issue skill replaces /claude:plan, /claude:implement, /ghi-finalize and the per-agent plan/implement matrix
- [ADR-9025: Delegated agents receive GitHub data from the host and run without network](decisions/9025-delegated-agents-receive-github-data-from-the-host-and-run-without-network.md) - The host fetches GitHub issue/PR data with doit delegation_context and writes it to files, so delegated agent prompts read those instead of calling gh
- [ADR-9026: Doc-scanning tests honor sync-exclude.toml and discover markdown via git](decisions/9026-doc-scanning-tests-honor-sync-excludetoml-and-discover-markdown-via-git.md) - The shipped doc-link and doc-path tests discover markdown via git ls-files instead of rglob, and skip a target excluded in sync-exclude.toml
- [ADR-9027: implement-issue works in a per-issue worktree](decisions/9027-implement-issue-works-in-a-per-issue-worktree.md) - implement-issue always works in a per-issue worktree under worktrees/, so several issues can run at once
- [ADR-9028: implement-issues runs issues in parallel background agents](decisions/9028-implement-issues-runs-issues-in-parallel-background-agents.md) - implement-issues runs implement-issue for several issues at once, one worktree and one nested-capable background agent each, capped at 2 by default
- [ADR-9029: implement-issue host plan and Coder checking budget](decisions/9029-implement-issue-host-plan-and-coder-checking-budget.md) - The implement-issue host may write the plan after posting findings, with a review pass, and the Coder runs a bounded set of checks while Step 5 runs the one full doit check
- [ADR-9030: Cross-agent roles resolve through a per-user config](decisions/9030-cross-agent-roles-resolve-through-a-per-user-config.md) - Cross-agent roles resolve through one doit task reading a layered per-user config, subagent first, with Codex subagents taking a model and effort and Copilot subagent models resolving to the CLI
- [ADR-9031: A project adds rebuildable names for worktree removal in pyproject.toml](decisions/9031-a-project-adds-rebuildable-names-for-worktree-removal-in-pyprojecttoml.md) - doit pr_merge reads extra rebuildable names from [tool.pyproject-template.worktree] in the main checkout's pyproject.toml, rejecting over-broad names
- [Agent Roles and Models](development/ai/agent-roles.md) - How to choose which CLI and model runs each cross-agent role (plan, plan review, code, review, adversarial review) from a per-user config
- [AI Agent Setup Guide](development/AI_SETUP.md) - Configure Claude, Copilot, Codex, and Antigravity for this project
- [AI Agent Sync Checklist](template/ai-sync-checklist.md) - Step-by-step checklist for AI agents synchronizing downstream projects with pyproject-template
- [AI Agent Token-Efficiency Add-Ons](development/ai/token-efficiency-add-ons.md) - Opt-in catalogue of external tools for reducing token usage in Claude Code sessions
- [AI Architectural Conventions](development/ai/architectural-conventions.md) - Imperative-form architectural rules AI agents must follow when generating code
- [AI Command Blocking](development/ai/command-blocking.md) - Hooks that block dangerous commands from AI agents
- [AI Enforcement Principles](development/ai/enforcement-principles.md) - How we enforce AI agent behavior in code and settings
- [Aliases](client/aliases.md) - Define short names that expand to longer input, with %1 to %9 and %* arguments
- [API System](claude/api_system.md) - The central API registry plugins use to publish and call functions
- [API System Analysis and Findings](claude/api_system_findings.md) - Audit of API registration, removal, call cost, caller tracking and the patterns the API system uses, with defects and a patterns review
- [Architecture Decision Records](decisions/README.md) - What an ADR is, the two numbering series, the ADR format, and how to create one with doit adr
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [bastproxy System Documentation](claude/README.md) - Index of the bastproxy architecture notes and how the systems fit together
- [CI/CD Testing Guide](development/ci-cd-testing.md) - GitHub Actions pipelines for testing, linting, and coverage
- [Claude Code Statusline](development/ai/statusline.md) - Custom statusline showing git branch, Python version, and project info
- [Colour System](claude/colors_system.md) - The colour-code syntax, the one tokenizer that defines it, and how conversion, stripping, validation, html and width are built on it
- [Colour System Analysis and Findings](claude/colors_findings.md) - Audit of the colors plugin - its APIs and callers, the colour-code conversion bugs reproduced on main, why they happen, and the recommended single-tokenizer design
- [Command System](claude/command_system.md) - How client commands are parsed, dispatched and documented
- [Command System Analysis and Findings](claude/command_system_findings.md) - Audit of the commands plugin - how a client line becomes a command, state consistency across add, reload and unload, failure handling, test coverage, docs accuracy and patterns, with defects and a patterns review
- [Consumer Notes](template/consumer-notes.md) - Breaking changes and behaviour changes that arrive when a project syncs from the template.
- [Cross-Agent Delegation Matrix](development/ai/cross-agent-delegation.md) - Commands that let any supported AI CLI hand a review task to any other; plan and implement are handled by the shared implement-issue skill instead
- [Data Flow](claude/data_flow.md) - How network data moves between MUD servers and clients through the proxy
- [Debugging](development/debugging.md) - Tracing bastproxy's event and plugin flow with hunter, without adding log lines
- [Dependabot Auto-merge](development/dependabot-automerge.md) - How the dependabot auto-merge workflow evaluates, enables, and skips PRs
- [Doit Tasks Reference](development/doit-tasks-reference.md) - Complete reference for all doit automation tasks
- [Event System](claude/event_system.md) - Priority-based event registration and dispatch between plugins
- [Event System Analysis and Findings](claude/event_system_findings.md) - Audit of the event system - the status of the earlier findings, plugin unload, priority ordering and failing callbacks, cost, test coverage, docs accuracy and patterns, with defects and a patterns review
- [First 5 Minutes with an AI Agent](development/ai/first-5-minutes.md) - Narrative walkthrough of the AI agent workflow from issue to merge
- [GitHub Repository Settings](development/github-repository-settings.md) - Complete reference for all GitHub repository settings the template expects
- [install_tools Framework](development/install-tools-framework.md) - Reusable framework for installing developer tools from GitHub releases or other URLs into ~/.local/bin
- [Keeping Up to Date](template/updates.md) - Stay in sync with improvements to the pyproject-template
- [Logging System](claude/logging_system.md) - How bastproxy code logs through standard-library loggers, how thresholds and handlers route messages, and how to migrate from LogRecord
- [Loop](client/loop.md) - Run a line a number of times, with the counter in the line, through aliases and variables
- [LSP Tool and Diagnostic Noise](development/ai/lsp-tool.md) - What the LSP tool gives an AI agent, why pyright diagnostics arrive stale, and the two opt-outs agents can flip on themselves
- [Mapper](client/mapper.md) - Find rooms, show paths and walk to a room with the mapper plugin, which game plugins feed with rooms and exits
- [Mapper System](claude/mapper_system.md) - How the mapper plugin stores the map, finds paths and walks them, and what a game plugin adapter does
- [Migration Guide](template/migration.md) - Migrate existing Python projects to use this template
- [Network Layer Analysis and Findings](claude/network_system_findings.md) - Audit of the network layer and its use of telnetlib3 - private API, deprecations, reimplemented features, patches, the 5.0.2 release, test coverage, the status of the open network issues and patterns, with defects and a patterns review
- [New Project Setup](template/new-project.md) - Create a new Python project from this template
- [Optional Extensions](development/extensions.md) - Additional tools and extensions for testing, security, and more
- [Per-Stack Rule Files](development/ai/rule-files.md) - How to author, load and mirror the short self-check rule files in .claude/rules/
- [Plugin Developer Guide](plugin-developer-guide.md) - A task-oriented path for plugin authors, covering communication, plugin structure and reloading, hooks and events, commands and triggers
- [Plugin System](claude/plugin_system.md) - Plugin structure, metadata, loading, reloading and lifecycle
- [Plugin System Analysis and Findings](claude/plugin_system_findings.md) - Audit of plugin discovery, loading, unloading, reloading, hooks and BasePlugin patching, with defects and a patterns review
- [Python Project Coding Standards](development/coding-standards.md) - Guidelines for exceptions, typing, structure, testing, and documentation
- [Record System](claude/record_system.md) - Records that track data and operations, their lifecycle and relationships
- [Record System Analysis and Findings](claude/record_system_findings.md) - Audit of record mutation tracking, the parent/child tree, retention and memory, test coverage, docs accuracy and the patterns the record system uses, with defects and a patterns review
- [Release Automation & Security](development/release-and-automation.md) - Automated versioning, release management, and security tooling
- [Review Focus Areas](development/ai/review-focus-areas.md) - Checklists for the errors, tests, types and comments focus areas available to every review and adversarial-review surface
- [Ruff Auto-Fix on Edit Hook](development/ai/ruff-fix-hook.md) - PostToolUse hook that runs ruff --fix on edited Python files
- [Settings System](claude/settings_system.md) - Per-plugin settings, persistence and change events
- [Slash Commands and Workflows](development/ai/slash-commands.md) - Reference for the slash commands and dual-agent workflow this project ships with
- [SQLite Database System](claude/sqldb_system.md) - How plugins store data in SQLite through the sqldb plugin
- [Substitutes](client/substitutes.md) - Rewrite text in MUD output before it reaches the client, keeping colour, with plain or regex matching
- [Template Management](template/manage.md) - Unified interface for creating projects, checking updates, and syncing
- [Template Tools Reference](template/tools-reference.md) - Complete reference for all template tools in tools/pyproject_template/
- [Timers System](claude/timers_system.md) - Scheduling recurring and one-shot timers from plugins
- [Tooling Roles and Architectural Boundaries](development/tooling-roles.md) - What each tool is for, who uses it, and where runtime code ends and dev tooling begins
- [Triggers System](claude/triggers_system.md) - Regex matching on MUD output that raises events for plugins to handle
- [Triggers System Analysis and Findings](claude/triggers_system_findings.md) - Audit of the triggers plugin - how a MUD line reaches a trigger, state consistency, failure handling, cost, test coverage, docs accuracy, patterns and a design assessment with alternatives measured
- [Using This Template](template/index.md) - Overview of using pyproject-template for your Python projects
- [Utils Plugin](claude/utils_system.md) - The formatting, time and value-conversion APIs of plugins.core.utils
- [Variables](client/variables.md) - Store named values and use them in the lines you type with %{name} references
- [Web Server](web-server.md) - The web plugin serves pages that plugins publish over a small HTTP server, with its settings, commands, security model, and two ways to reach it remotely over TLS
- [Web System](claude/web_system.md) - How a plugin publishes a page through the web plugin's web.page.add API
<!-- END:all -->

---

## Contributing to Documentation

When adding new documentation:

1. Add frontmatter with `title`, `description`, `audience`, and `tags`:
   ```yaml
   ---
   title: My New Guide
   description: Short description for the index
   audience:
     - users
     - contributors
   tags:
     - setup
     - getting-started
   ---
   ```

2. Place the file in the appropriate directory

3. Run `python tools/generate_doc_toc.py` to update this index

4. The pre-commit hook will also run automatically on commit
