---
title: Web System
description: How a plugin publishes a page through the web plugin's web.page.add API
audience:
  - contributors
  - ai-agents
tags:
  - architecture
  - web
---

# Web System

The `plugins.core.web` plugin runs a GET-only HTTP server and stores pages for other plugins. Users read how to turn it on, its settings and its security model in [Web Server](../web-server.md); the design is in [ADR-0022](../decisions/0022-the-web-plugin-serves-token-links-and-session-gated-plugin-routes-over-a-get-only-standard-library-server.md).

Issue #424 lands in three pull requests. This page covers what the first one adds, `web.page.add`. Plugin routes (`web.route.add`), the login session and table pages come in the later ones and will be added here.

## Publishing a page

```python
url = self.api("plugins.core.web:web.page.add")(self.plugin_id, "Record 12", lines)
if not url:
    return CommandResult(True, ["the web server is not enabled (#bp.core.web.set enabled true)"])
return CommandResult(True, [f"Record detail: {url}"])
```

`web.page.add(owner, title, lines) -> str`

| Argument | Meaning |
| :--- | :--- |
| `owner` | Your plugin id. |
| `title` | The page title. It is escaped. |
| `lines` | A list of lines or one string, with `@@` colour codes. |

- The result is the link, built from the `publicurl` setting, or from the bind address and port when it is empty.
- The result is `""` when the web server is not enabled. Check for it and say so; a dead link is worse than a message. Also check `libs.api:api.exists` for `plugins.core.web:web.page.add` when the web plugin may be absent, as record detail does.
- The link is the credential: its token is random and the page lasts an hour. At most 50 pages are held, and the oldest goes first. Do not put a link in a place that other people can read.
- Plugins never import the web plugin; they only call the API.

## What the page contains

The page is rendered once, when it is added. The text goes through `plugins.core.colors:colorcode.to.html`, which HTML-escapes the visible text, turns colour codes into `span` elements with inline colours and drops raw terminal escape sequences (see [colour system](colors_system.md)). The page therefore holds MUD text safely, and has no script. The response carries a strict Content-Security-Policy; see [Security model](../web-server.md#security-model-for-page-links).

## Lifecycle

- The web plugin starts its listener in a queued task (`libs.asynch:task.add`), so connections do not inherit the context of the command or event that started it.
- When the plugin unloads, it closes the listener and aborts the open connections before the base unload hook raises `ev_plugin_unloaded`.
- When the web plugin is reloaded, the stored pages carry over (`attributes_to_save_on_reload`), so links keep working.
