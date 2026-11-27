---
title: "ADR-0025: The web plugin serves pages and a client WebSocket from one listener, with shared sessions and data providers"
description: The web plugin keeps one listener for pages and a client WebSocket, shares sessions, and serves registered data providers as pages and live topics.
date: 2026-11-27
audience:
  - contributors
tags:
  - adr
---

# ADR-0025: The web plugin serves pages and a client WebSocket from one listener, with shared sessions and data providers

## Status

Proposed

## Context

The proxy already parses everything a graphical client needs: MUD output as records, and plugin state such as the campaign mobs left, the current room and the statistics. Telnet clients get only text and GMCP, so a graphical client has to parse both again. The repo admin wants a browser client, in its own repository, with a main window, a mapper and movable panes for quests, campaigns and stats. It should talk to the proxy directly.

ADR-0022 built the web plugin: a GET-only HTTP server on `asyncio.start_server`, one-time token links, session-gated plugin routes and server-rendered tables. Its standard-library rule was decided for GET-only pages. It does not cover a long-lived browser connection.

Open-source web MUD clients (MUDPortal, oiMUD, Mudslinger and others) all parse telnet and GMCP in the browser. Their UI could be reused but their protocol layer could not, so the client will be a new TypeScript project. This ADR covers the proxy side.

## Decision

- **One listener, two transports.** The web plugin keeps one port, one `asyncio.start_server`, the same loopback-or-TLS rule, the same certificate reload and the same connection limits. A GET with `Upgrade: websocket` on the socket path goes to the WebSocket side. Every other request takes the ADR-0022 path unchanged.
- **WebSocket handling by the `websockets` library, sans-I/O.** The web plugin reads the upgrade request itself and checks the session and the Origin. It then drives `websockets.server.ServerProtocol` (`receive_data`, `data_to_send`, `events_received`) over the stream it already owns. The library does the RFC 6455 work: masking, fragments, control frames, UTF-8 checks, close codes and the `max_size` limit. Adding the dependency is the repo admin's decision and goes through the add-dependency skill.
- **One session store.** The `bpsession` cookie from `#bp.core.web.login` admits both pages and the socket. The upgrade also requires an `Origin` matching `publicurl`, or the listener's own origin when `publicurl` is unset. This blocks cross-site WebSocket hijacking, which `SameSite=Strict` alone does not cover. `#bp.core.web.logout` ends sessions and closes their sockets. The proxy password is still never sent over HTTP.
- **Data providers: a plugin registers once and both transports serve it.** `web.provider.add(owner, name, snapshot, columns=None, kind="json", event=None)`:
  - The name comes from the owner, the way route paths do. `plugins.aardwolf.cp` with `mobsleft` is the topic `aardwolf.cp.mobsleft` and the page `/aardwolf/cp/mobsleft`.
  - `snapshot()` returns plain data (rows, or a JSON-safe dict), because plugins do not import plugins.
  - `event` names the event that means the data changed. A plugin can instead call `web.provider.changed.raise(owner, name)`.
  - HTTP renders the snapshot with the existing kinds (`table`, `json`). A route handler stays possible for pages that are not providers.
  - The owner check, the reserved names and the removal on `ev_plugin_unloaded` are shared with routes.
- **Colour as spans.** `colorcode.to.spans(text)` builds on `colorcode.to.tokens` (ADR-0008) and returns `[{"text", "fg", "bg", "bold"}]`. `colorcode.to.html` becomes spans to escaped HTML. Pages and the client then cannot disagree about colour, and escaping stays in one place. The browser never parses ANSI or `@` codes.
- **The socket protocol is JSON text frames with a version.** Every message is `{"v": 1, "type": ...}`.
  - Server to client: `hello` (protocol version, proxy version, a connection id; the session id stays HttpOnly and is never sent), `output` (one line as spans, with `prompt` and one `record` string, the line's id), `snapshot` and `update` (topic, data), `result` (call id, status, reply), `error`.
  - Client to server: `input` (text for the to-MUD pipeline, one line per text line), `cols` (the window width and height, like telnet NAWS), `subscribe` and `unsubscribe` (topic), `call` (id, command, arguments).
  - An unknown `type` gets an `error`, never a disconnect. A client that needs a newer `v` closes with a message.
- **Socket limits and close codes.** A message is at most 64 KiB (close 1009), the send queue holds 256 messages (close 1008), and binary frames are refused (close 1003). The output queue of a socket holds 5000 lines and one more closes it with 1008 (reason `output queue full`). The proxy pings every 20 seconds and closes with 1011 after 40 seconds of silence. A logout, or a session that is no longer valid, closes with 4001. A shutdown or unload closes with 1001. Sockets count against the connection cap.
- **A web client is a proxy client.** Each socket is registered through `plugins.core.clients` like a telnet client. It receives the MUD output stream after the same per-client steps, and its `input` goes through the same to-MUD pipeline. View-only is honoured: `#bp.core.web.viewlogin` gives a link that starts a view-only session, every socket of that session is view-only, and its `input` is answered with `error` code `view_only`. It appears in the clients list with its type, `websocket`.
- **Command calls with structured replies.** `call` runs a `#bp` command, or an API a plugin exposes for the client, and returns its reply as data in `result`. The socket does not need to parse command text.
- **The client bundle is served by the proxy.** A `clientdir` setting points at the built client. Files under it are served at `/webclient/`, behind the session. Only successful file responses there carry the ADR-0022 policy plus `connect-src 'self'` and `font-src 'self'`. Every other page keeps the ADR-0022 CSP, where `default-src 'none'` already blocks connections. Plugins still cannot ship scripts.
- **Pages stay scriptless.** Live data goes to the client. Existing pages keep server rendering and `table.js` only.

## Rationale

One listener keeps one port, one TLS setup and one login, and the upgrade check reuses code already reviewed. A WebSocket parser faces the network and is long-lived. A tested library is safer than our own, and its sans-I/O layer lets the web plugin keep ownership of the socket. Registering data once, as a provider, gives every piece of live client data a page for free, and keeps the two views from drifting. Spans put colour handling and escaping in one function. Treating a web client as a proxy client means triggers, gags, view-only and the clients list behave the same for every client.

## Alternatives Considered

- **A WebSocket written by hand on the standard library.** Rejected: we would own the RFC 6455 handling and its edge cases on a network-facing parser.
- **The `websockets` asyncio server on its own port.** Rejected: a second port, a second TLS setup and a second auth check.
- **Live pages over the socket.** Rejected for now: every page would need scripts and a wider CSP. A page can opt in later.
- **Custom GMCP packages to telnet clients as the client protocol.** Rejected: a browser cannot speak telnet. A `bastproxy.*` GMCP namespace for telnet clients may come later, built on the same providers.
- **The proxy password in the browser.** Rejected: ADR-0022 keeps the password off HTTP. The one-time login link already gives a browser a session.
- **The client hosted separately.** Rejected: a cross-origin socket needs an Origin allowlist and a `SameSite=None` cookie.
- **Forking an existing web MUD client.** Rejected: their core is the telnet and GMCP layer this design removes. MUDPortal (MIT) remains a reference for windows and mapper rendering.

## Consequences

- `websockets` becomes a runtime dependency, once the repo admin approves it.
- ADR-0022 is amended: the listener also accepts WebSocket upgrades, `/webclient/` has its own CSP, and providers sit alongside routes.
- Snapshots run on the loop. A slow snapshot works on a copy with `asyncio.to_thread`, as route handlers do.
- Output to a web client is held back by its socket. The per-client output queue holds 5000 lines; one more closes the socket with 1008. Output uses at most half of the 256-message send queue, so replies to the client still fit.
- Updates are debounced per topic with a trailing timer of 100 ms, so a burst of changes sends one update.
- The protocol `v` is a contract with another repository. A change that breaks it bumps `v` and is recorded here. The machine-readable form of the contract is the JSON Schema `socket-v1.schema.json`, and tests tie it to the code.

## Related Issues

- Issue #424: the internal web server (ADR-0022)
- Issue #840: data providers
- Issue #842: the client socket endpoint `/ws`
- Issue #843: subscriptions to data providers over the socket
- Issue #844: a socket is a proxy client (output as spans, input to the MUD, view-only login)
- Issue #845: command calls with structured replies over the socket
- Issue #846: the client bundle served from `clientdir`
- Issue #870: a JSON Schema of the socket messages, checked by tests
- The core issues filed with this ADR, listed in its PR

## Related Documentation

- [Web server](../web-server.md)
- [Socket message schema](../../src/bastproxy/plugins/core/web/schema/socket-v1.schema.json)
- [Web system](../claude/web_system.md)
- [Colour system](../claude/colors_system.md)
- [Data flow](../claude/data_flow.md)
- [ADR-0008](0008-the-colors-tokenizer-is-the-single-definition-of-the-colour-code-syntax.md)
- [ADR-0022](0022-the-web-plugin-serves-token-links-and-session-gated-plugin-routes-over-a-get-only-standard-library-server.md)
