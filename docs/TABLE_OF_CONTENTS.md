# All Documents

Complete index of all documentation, organized by audience and as a full alphabetical list.

> These lists are auto-generated from document frontmatter.
> Run `python tools/generate_doc_toc.py` to update.

## By Audience

### For Users
<!-- BEGIN:audience=users -->
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [Doit Tasks Reference](development/doit-tasks-reference.md) - Complete reference for all doit automation tasks
- [GitHub Repository Settings](development/github-repository-settings.md) - Complete reference for all GitHub repository settings the template expects
- [Keeping Up to Date](template/updates.md) - Stay in sync with improvements to the pyproject-template
- [Migration Guide](template/migration.md) - Migrate existing Python projects to use this template
- [New Project Setup](template/new-project.md) - Create a new Python project from this template
- [Template Management](template/manage.md) - Unified interface for creating projects, checking updates, and syncing
- [Template Tools Reference](template/tools-reference.md) - Complete reference for all template tools in tools/pyproject_template/
- [Using This Template](template/index.md) - Overview of using pyproject-template for your Python projects
<!-- END:audience=users -->

### For Contributors
<!-- BEGIN:audience=contributors -->
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
- [AI Agent Setup Guide](development/AI_SETUP.md) - Configure Claude, Copilot, Codex, and Antigravity for this project
- [AI Agent Token-Efficiency Add-Ons](development/ai/token-efficiency-add-ons.md) - Opt-in catalogue of external tools for reducing token usage in Claude Code sessions
- [AI Architectural Conventions](development/ai/architectural-conventions.md) - Imperative-form architectural rules AI agents must follow when generating code
- [AI Command Blocking](development/ai/command-blocking.md) - Hooks that block dangerous commands from AI agents
- [AI Enforcement Principles](development/ai/enforcement-principles.md) - How we enforce AI agent behavior in code and settings
- [API System](claude/api_system.md) - The central API registry plugins use to publish and call functions
- [Architecture Decision Records](decisions/README.md) - What an ADR is, the two numbering series, the ADR format, and how to create one with doit adr
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [bastproxy System Documentation](claude/README.md) - Index of the bastproxy architecture notes and how the systems fit together
- [CI/CD Testing Guide](development/ci-cd-testing.md) - GitHub Actions pipelines for testing, linting, and coverage
- [Claude Code Statusline](development/ai/statusline.md) - Custom statusline showing git branch, Python version, and project info
- [Command System](claude/command_system.md) - How client commands are parsed, dispatched and documented
- [Cross-Agent Delegation Matrix](development/ai/cross-agent-delegation.md) - Commands that let any supported AI CLI hand a review task to any other; plan and implement are handled by the shared implement-issue skill instead
- [Data Flow](claude/data_flow.md) - How network data moves between MUD servers and clients through the proxy
- [Dependabot Auto-merge](development/dependabot-automerge.md) - How the dependabot auto-merge workflow evaluates, enables, and skips PRs
- [Doit Tasks Reference](development/doit-tasks-reference.md) - Complete reference for all doit automation tasks
- [Event System](claude/event_system.md) - Priority-based event registration and dispatch between plugins
- [Event System Analysis and Findings](claude/event_system_findings.md) - Review findings and recommendations for the event system implementation
- [First 5 Minutes with an AI Agent](development/ai/first-5-minutes.md) - Narrative walkthrough of the AI agent workflow from issue to merge
- [GitHub Repository Settings](development/github-repository-settings.md) - Complete reference for all GitHub repository settings the template expects
- [install_tools Framework](development/install-tools-framework.md) - Reusable framework for installing developer tools from GitHub releases or other URLs into ~/.local/bin
- [LSP Tool and Diagnostic Noise](development/ai/lsp-tool.md) - What the LSP tool gives an AI agent, why pyright diagnostics arrive stale, and the two opt-outs agents can flip on themselves
- [Optional Extensions](development/extensions.md) - Additional tools and extensions for testing, security, and more
- [Per-Stack Rule Files](development/ai/rule-files.md) - How to author, load and mirror the short self-check rule files in .claude/rules/
- [Plugin System](claude/plugin_system.md) - Plugin structure, metadata, loading, reloading and lifecycle
- [Python Project Coding Standards](development/coding-standards.md) - Guidelines for exceptions, typing, structure, testing, and documentation
- [Record System](claude/record_system.md) - Records that track data and operations, their lifecycle and relationships
- [Release Automation & Security](development/release-and-automation.md) - Automated versioning, release management, and security tooling
- [Review Focus Areas](development/ai/review-focus-areas.md) - Checklists for the errors, tests, types and comments focus areas available to every review and adversarial-review surface
- [Ruff Auto-Fix on Edit Hook](development/ai/ruff-fix-hook.md) - PostToolUse hook that runs ruff --fix on edited Python files
- [Settings System](claude/settings_system.md) - Per-plugin settings, persistence and change events
- [Slash Commands and Workflows](development/ai/slash-commands.md) - Reference for the slash commands and dual-agent workflow this project ships with
- [Template Tools Reference](template/tools-reference.md) - Complete reference for all template tools in tools/pyproject_template/
- [Timers System](claude/timers_system.md) - Scheduling recurring and one-shot timers from plugins
- [Tooling Roles and Architectural Boundaries](development/tooling-roles.md) - What each tool is for, who uses it, and where runtime code ends and dev tooling begins
- [Triggers System](claude/triggers_system.md) - Regex matching on MUD output that raises events for plugins to handle
<!-- END:audience=contributors -->

### For AI Agents
<!-- BEGIN:audience=ai-agents -->
- [AI Agent Setup Guide](development/AI_SETUP.md) - Configure Claude, Copilot, Codex, and Antigravity for this project
- [AI Agent Sync Checklist](template/ai-sync-checklist.md) - Step-by-step checklist for AI agents synchronizing downstream projects with pyproject-template
- [AI Agent Token-Efficiency Add-Ons](development/ai/token-efficiency-add-ons.md) - Opt-in catalogue of external tools for reducing token usage in Claude Code sessions
- [AI Architectural Conventions](development/ai/architectural-conventions.md) - Imperative-form architectural rules AI agents must follow when generating code
- [AI Command Blocking](development/ai/command-blocking.md) - Hooks that block dangerous commands from AI agents
- [AI Enforcement Principles](development/ai/enforcement-principles.md) - How we enforce AI agent behavior in code and settings
- [API System](claude/api_system.md) - The central API registry plugins use to publish and call functions
- [Architecture Decision Records](decisions/README.md) - What an ADR is, the two numbering series, the ADR format, and how to create one with doit adr
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [bastproxy System Documentation](claude/README.md) - Index of the bastproxy architecture notes and how the systems fit together
- [Claude Code Statusline](development/ai/statusline.md) - Custom statusline showing git branch, Python version, and project info
- [Command System](claude/command_system.md) - How client commands are parsed, dispatched and documented
- [Cross-Agent Delegation Matrix](development/ai/cross-agent-delegation.md) - Commands that let any supported AI CLI hand a review task to any other; plan and implement are handled by the shared implement-issue skill instead
- [Data Flow](claude/data_flow.md) - How network data moves between MUD servers and clients through the proxy
- [Event System](claude/event_system.md) - Priority-based event registration and dispatch between plugins
- [Event System Analysis and Findings](claude/event_system_findings.md) - Review findings and recommendations for the event system implementation
- [First 5 Minutes with an AI Agent](development/ai/first-5-minutes.md) - Narrative walkthrough of the AI agent workflow from issue to merge
- [LSP Tool and Diagnostic Noise](development/ai/lsp-tool.md) - What the LSP tool gives an AI agent, why pyright diagnostics arrive stale, and the two opt-outs agents can flip on themselves
- [Plugin System](claude/plugin_system.md) - Plugin structure, metadata, loading, reloading and lifecycle
- [Record System](claude/record_system.md) - Records that track data and operations, their lifecycle and relationships
- [Review Focus Areas](development/ai/review-focus-areas.md) - Checklists for the errors, tests, types and comments focus areas available to every review and adversarial-review surface
- [Ruff Auto-Fix on Edit Hook](development/ai/ruff-fix-hook.md) - PostToolUse hook that runs ruff --fix on edited Python files
- [Settings System](claude/settings_system.md) - Per-plugin settings, persistence and change events
- [Slash Commands and Workflows](development/ai/slash-commands.md) - Reference for the slash commands and dual-agent workflow this project ships with
- [Timers System](claude/timers_system.md) - Scheduling recurring and one-shot timers from plugins
- [Tooling Roles and Architectural Boundaries](development/tooling-roles.md) - What each tool is for, who uses it, and where runtime code ends and dev tooling begins
- [Triggers System](claude/triggers_system.md) - Regex matching on MUD output that raises events for plugins to handle
<!-- END:audience=ai-agents -->

## Complete Index
<!-- BEGIN:all -->
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
- [AI Agent Setup Guide](development/AI_SETUP.md) - Configure Claude, Copilot, Codex, and Antigravity for this project
- [AI Agent Sync Checklist](template/ai-sync-checklist.md) - Step-by-step checklist for AI agents synchronizing downstream projects with pyproject-template
- [AI Agent Token-Efficiency Add-Ons](development/ai/token-efficiency-add-ons.md) - Opt-in catalogue of external tools for reducing token usage in Claude Code sessions
- [AI Architectural Conventions](development/ai/architectural-conventions.md) - Imperative-form architectural rules AI agents must follow when generating code
- [AI Command Blocking](development/ai/command-blocking.md) - Hooks that block dangerous commands from AI agents
- [AI Enforcement Principles](development/ai/enforcement-principles.md) - How we enforce AI agent behavior in code and settings
- [API System](claude/api_system.md) - The central API registry plugins use to publish and call functions
- [Architecture Decision Records](decisions/README.md) - What an ADR is, the two numbering series, the ADR format, and how to create one with doit adr
- [bastproxy Documentation](index.md) - Overview of bastproxy and an index of its architecture, development and process docs
- [bastproxy System Documentation](claude/README.md) - Index of the bastproxy architecture notes and how the systems fit together
- [CI/CD Testing Guide](development/ci-cd-testing.md) - GitHub Actions pipelines for testing, linting, and coverage
- [Claude Code Statusline](development/ai/statusline.md) - Custom statusline showing git branch, Python version, and project info
- [Command System](claude/command_system.md) - How client commands are parsed, dispatched and documented
- [Consumer Notes](template/consumer-notes.md) - Breaking changes and behaviour changes that arrive when a project syncs from the template.
- [Cross-Agent Delegation Matrix](development/ai/cross-agent-delegation.md) - Commands that let any supported AI CLI hand a review task to any other; plan and implement are handled by the shared implement-issue skill instead
- [Data Flow](claude/data_flow.md) - How network data moves between MUD servers and clients through the proxy
- [Dependabot Auto-merge](development/dependabot-automerge.md) - How the dependabot auto-merge workflow evaluates, enables, and skips PRs
- [Doit Tasks Reference](development/doit-tasks-reference.md) - Complete reference for all doit automation tasks
- [Event System](claude/event_system.md) - Priority-based event registration and dispatch between plugins
- [Event System Analysis and Findings](claude/event_system_findings.md) - Review findings and recommendations for the event system implementation
- [First 5 Minutes with an AI Agent](development/ai/first-5-minutes.md) - Narrative walkthrough of the AI agent workflow from issue to merge
- [GitHub Repository Settings](development/github-repository-settings.md) - Complete reference for all GitHub repository settings the template expects
- [install_tools Framework](development/install-tools-framework.md) - Reusable framework for installing developer tools from GitHub releases or other URLs into ~/.local/bin
- [Keeping Up to Date](template/updates.md) - Stay in sync with improvements to the pyproject-template
- [LSP Tool and Diagnostic Noise](development/ai/lsp-tool.md) - What the LSP tool gives an AI agent, why pyright diagnostics arrive stale, and the two opt-outs agents can flip on themselves
- [Migration Guide](template/migration.md) - Migrate existing Python projects to use this template
- [New Project Setup](template/new-project.md) - Create a new Python project from this template
- [Optional Extensions](development/extensions.md) - Additional tools and extensions for testing, security, and more
- [Per-Stack Rule Files](development/ai/rule-files.md) - How to author, load and mirror the short self-check rule files in .claude/rules/
- [Plugin System](claude/plugin_system.md) - Plugin structure, metadata, loading, reloading and lifecycle
- [Python Project Coding Standards](development/coding-standards.md) - Guidelines for exceptions, typing, structure, testing, and documentation
- [Record System](claude/record_system.md) - Records that track data and operations, their lifecycle and relationships
- [Release Automation & Security](development/release-and-automation.md) - Automated versioning, release management, and security tooling
- [Review Focus Areas](development/ai/review-focus-areas.md) - Checklists for the errors, tests, types and comments focus areas available to every review and adversarial-review surface
- [Ruff Auto-Fix on Edit Hook](development/ai/ruff-fix-hook.md) - PostToolUse hook that runs ruff --fix on edited Python files
- [Settings System](claude/settings_system.md) - Per-plugin settings, persistence and change events
- [Slash Commands and Workflows](development/ai/slash-commands.md) - Reference for the slash commands and dual-agent workflow this project ships with
- [Template Management](template/manage.md) - Unified interface for creating projects, checking updates, and syncing
- [Template Tools Reference](template/tools-reference.md) - Complete reference for all template tools in tools/pyproject_template/
- [Timers System](claude/timers_system.md) - Scheduling recurring and one-shot timers from plugins
- [Tooling Roles and Architectural Boundaries](development/tooling-roles.md) - What each tool is for, who uses it, and where runtime code ends and dev tooling begins
- [Triggers System](claude/triggers_system.md) - Regex matching on MUD output that raises events for plugins to handle
- [Using This Template](template/index.md) - Overview of using pyproject-template for your Python projects
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
