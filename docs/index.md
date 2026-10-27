---
title: bastproxy Documentation
description: Overview of bastproxy and an index of its architecture, development and process docs
audience:
  - users
  - contributors
  - ai-agents
tags:
  - overview
---

# bastproxy Documentation

bastproxy is an extensible MUD (Multi-User Dungeon) proxy built on Python 3.12+ and asyncio. It sits between your MUD client and the MUD server, and adds triggers, logging, a command system and a plugin framework on top of the connection.

## Getting started

Installation, running the proxy and connecting a client are covered in the project [README](../README.md).

bastproxy keeps its data, plugin settings and logs in the directory named by `BASTPROXY_HOME`, which must exist and be writable before the package is imported. `.envrc` defaults it to `~/bastproxy`.

## Architecture

How the proxy works inside, one system per page:

- [System overview](claude/README.md)
- [Data flow](claude/data_flow.md): how bytes move between MUD and clients
- [Plugin system](claude/plugin_system.md), [API system](claude/api_system.md), [Event system](claude/event_system.md)
- [Command system](claude/command_system.md), [Settings system](claude/settings_system.md), [Timers](claude/timers_system.md), [Triggers](claude/triggers_system.md)
- [Record system](claude/record_system.md)

## Contributing

- [Contributing guide](../.github/CONTRIBUTING.md): issue, branch, commit and PR workflow
- [Plugin development](../CONTRIBUTING.md): plugin structure
- [Coding standards](development/coding-standards.md) and [doit tasks](development/doit-tasks-reference.md)
- [CI/CD and testing](development/ci-cd-testing.md), [release and automation](development/release-and-automation.md)
- [Architecture decisions](decisions/README.md)
- [AI agent setup](development/AI_SETUP.md)

## Project template

bastproxy is built on [pyproject-template](https://github.com/endavis/pyproject-template). See [Keeping up to date](template/updates.md) and the [AI sync checklist](template/ai-sync-checklist.md) for how template changes are adopted.

A full, generated index of every page is in the [table of contents](TABLE_OF_CONTENTS.md).
