---
title: "ADR-0022: The web plugin serves token links and session-gated plugin routes over a GET-only standard-library server"
description: The web plugin runs a GET-only standard-library HTTP server; plugins publish one-off token links and session-gated routes, tables and one static script.
date: 2026-11-25
audience:
  - contributors
tags:
  - adr
---

# ADR-0022: The web plugin serves token links and session-gated plugin routes over a GET-only standard-library server

## Status

Accepted

## Context

Issue #424: some output is too long for the client, for example a record detail with its updates and children, and plugins such as the mapper and the Aardwolf statistics want to show area maps, database queries and tables. The proxy runs on one asyncio loop and must stay reachable without an SSH tunnel. The decisions were settled with the repo admin in the design comments of the issue. The issue lands in three pull requests:

1. **The server and one-off page links** (this ADR's first implementation): the `plugins.core.web` plugin, its settings, the loopback and TLS rule, certificate reload, the `status` and `reload` commands, the page store with `web.page.add`, `record detail --web`, the final Content-Security-Policy and the documentation.
2. **Routes and sessions:** `web.route.add` and `web.route.remove`, the login link, sessions, `/`, and the HTML, SVG and JSON response kinds.
3. **Tables:** the table response kind with server-side sorting, filtering and paging, and the one static script `/static/table.js`.

This ADR records the whole design so the three parts follow one decision.

## Decision

- **Standard library only.** A minimal GET-only HTTP/1.1 handler on `asyncio.start_server`, with TLS from `ssl.SSLContext`. No dependency is added. `http.server` is not used: it blocks and runs in threads, and the proxy's API, records and plugins are not thread-safe.
- **A core plugin, off by default.** `plugins.core.web` is loaded as every core plugin is (the loader marks them required), and listens only when `enabled` is true. Settings: `enabled`, `port` (9998), `bindaddress` (`127.0.0.1`), `certfile`, `keyfile`, `publicurl`, and with sessions `sessionhours`.
- **The server starts in a queued task.** asyncio's accept callback copies the context current when `start_server` is called, so a server started from a command would give every connection that command's record context. Start and restart go through `libs.asynch:task.add`, which creates the task with a fresh context.
- **Unload order.** An `uninitialize` hook at priority 10 closes the listener, aborts open connections and bumps a generation counter so a queued start exits, before the base hook at 100 raises `ev_plugin_unloaded`.
- **Page links with tokens, not the password.** `plugins.core.web:web.page.add(owner, title, lines) -> url` stores a page in memory (at most 50, one hour, oldest dropped first) behind `/p/<secrets.token_urlsafe(32)>`. The link is the credential. The proxy password is never used over HTTP. The API returns `""` when the server is disabled so callers can say so. Pages are rendered once when added.
- **Plain HTTP only on loopback.** A bind address that is not loopback (`localhost` or an IP literal that is loopback) needs `certfile` and `keyfile`; otherwise the server refuses to start and logs why. There is no override.
- **Certificate reload per connection.** In TLS mode each connection calls `StreamWriter.start_tls` with the context current at that moment, which is rebuilt when either file's modification time changed. A reload that fails keeps the previous context and logs an error. `#bp.core.web.reload` forces a reload.
- **Certificate details from an in-memory handshake.** The standard library has no public decoder for a PEM certificate. `status` runs a TLS handshake between a server and a client `SSLObject` joined by `ssl.MemoryBIO` pairs and reads the client's `getpeercert()`. A verify code of 10 shows `expired`; any other failure shows the file's modification time and `details unavailable`.
- **Request limits.** Head at most 8 KiB, 10 s read timeout, 10 s TLS handshake timeout, at most 32 connections, no body read, `Connection: close`. A method other than GET returns 405 with `Allow: GET`.
- **Output is escaped in its owner.** `colorcode.to.html` HTML-escapes visible text and drops raw SGR sequences (ADR-0008). Escaping before the conversion would break the colour-code tokenizer.
- **Plugin routes (part 2).** `web.route.add(owner, subpath, handler, title, columns=None)`. The path comes from the owner's plugin id: `plugins.` is dropped and dots become slashes, so `plugins.aardwolf.mapper` and `area` is served at `/aardwolf/mapper/area`. A plugin cannot choose a path outside its prefix, the first segments `p`, `login` and `static` are reserved, and the owner must be the caller. `web.route.remove(owner)` and the `ev_plugin_unloaded` event remove a plugin's routes. Handlers are sync or async and return a plain dict (`kind` of `html`, `table`, `svg` or `json`), because plugins do not import plugins. A handler runs under a 30 s timeout (504), an exception is 500, and slow work belongs in `asyncio.to_thread` on a snapshot. GET only.
- **Sessions (part 2).** `#bp.core.web.login` replies with `/login/<token>`, valid once and for 5 minutes. Opening it starts an in-memory session (cap 20, `sessionhours` lifetime) and redirects to `/` with a `bpsession` cookie that is `HttpOnly`, `SameSite=Strict`, `Path=/`, and `Secure` with TLS or an `https://` `publicurl`. Routes and `/` return 401 without a session; unknown paths return 404 either way. `#bp.core.web.logout` ends all sessions. The `/p/<token>` links need no session.
- **Tables (part 3).** The table kind supports `?sort=<col>&dir=asc|desc`, `?f_<col>=<value>`, `?page=` and `?count=`. The plugin checks every column against the columns declared at registration and hands the handler a validated sort, filters and page; an unknown column or a bad value is 400. A database-backed handler binds filter values as parameters, and a column name only selects a fixed SQL fragment.
- **One static script (part 3).** The web plugin serves `/static/table.js`, shipped in the package, in vanilla JS. It sorts and filters in the browser when the result is a single page, uses `textContent` and node moves only, and never `innerHTML`, `eval` or `fetch`. Plugins cannot ship or serve scripts.
- **Handler errors and links (#766).** A handler may return `{"kind": "error", "status": 400 or 404, "message"}`, served as the status page with the message escaped; any other status is 500. A table cell may be `{"text", "href"}`, rendered as a link whose href must be a same-origin absolute path (starts with `/`, not `//`, no backslash, whitespace or control character), else the page is 500. The format is stable, plugins build it as plain data.
- **Content-Security-Policy, from the first part on.** `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'`, with `Referrer-Policy: no-referrer`, `Cache-Control: no-store` and `X-Content-Type-Options: nosniff` on every response. There are no inline scripts and no `eval`; `connect-src` stays `'none'`.

## Rationale

Tokens in the URL give a link that works in any browser and expires, without sending the proxy password over a protocol the proxy may serve in plain text. Refusing plain HTTP off loopback makes the unsafe setup impossible instead of documented. Reloading the certificate on the next connection means a renewal by acme.sh or certbot needs no restart and no signal. Keeping the response kinds as plain dicts and the paths derived from the owner id keep plugins decoupled and keep one plugin from serving another's namespace. Gating routes behind a session that starts from a single-use link lets a client that is already logged in to the proxy open the web pages without a second password. Server-side tables work at any size and without a script; the one core script is a convenience on top.

## Alternatives Considered

- **`http.server` or a framework.** Rejected: `http.server` blocks and uses threads; a framework is a new dependency for GET-only pages.
- **The proxy password over HTTP.** Rejected: it would be exposed on a plain HTTP connection.
- **An override setting for plain HTTP off loopback.** Rejected: a setting that allows it will be set.
- **Decoding the certificate ourselves.** Rejected: custom ASN.1 code to maintain. `ssl._ssl._test_decode_cert` is private.
- **A dependency such as `cryptography` for the certificate expiry.** Rejected: a new dependency is an ask-first decision, and the in-memory handshake needs none.
- **Reloading the certificate on a timer or a signal.** Rejected: a stat per connection is cheap and has no moving parts.
- **Escaping in the web plugin before the colour conversion.** Rejected: `@<` would become `@&lt;`, and the tokenizer would drop `@&`.
- **Plugins serving their own scripts.** Rejected: one audited script keeps the CSP at `script-src 'self'` with no plugin-controlled code.
- **POST handlers.** Rejected for now: anything that changes data is a later design with CSRF protection.

## Consequences

- The web plugin is always loaded, because it is a core plugin; `enabled` decides whether it listens.
- Page links appear in command replies, so in client scrollback and in the record of the command. They expire with the page.
- Pages and sessions are in memory; a restart drops them. A reload of the web plugin carries the pages over.
- A handler that does slow work must use `asyncio.to_thread` on a snapshot; API calls are not thread-safe, so colour conversion and page rendering stay on the loop.
- Parts 2 and 3 add to this plugin without changing the part 1 behaviour: the dispatch order is method check, `/p/<token>`, then (later) static, login, `/`, routes, and 404.
- [ADR-0025](0025-the-web-plugin-serves-pages-and-a-client-websocket-from-one-listener-with-shared-sessions-and-data-providers.md) amends this: data providers sit alongside routes in the same table (issue #840), and the listener later also accepts WebSocket upgrades. Successful files under `/webclient/` (issue #846) carry the ADR-0022 policy plus `connect-src 'self'` and `font-src 'self'`.

## Related Issues

- Issue #424: add an internal web server that plugins extend with pages
- Issue #766: core mapper pages (SVG area map, room lookup)
- Issue #840: data providers sit alongside routes in the same table (ADR-0025)
- endavis/bastproxy-aardwolf#127: Aardwolf mapper pages
- endavis/bastproxy-aardwolf#128: statdb tables and charts

## Related Documentation

- [Web server](../web-server.md)
- [Web system](../claude/web_system.md)
- [Colour system](../claude/colors_system.md)
- [ADR-0025](0025-the-web-plugin-serves-pages-and-a-client-websocket-from-one-listener-with-shared-sessions-and-data-providers.md): extends this design with data providers and a client WebSocket
- [ADR-0004](0004-api-names-are-resource-first-and-cmdq-is-renamed-mudcmds.md)
- [ADR-0008](0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md)
