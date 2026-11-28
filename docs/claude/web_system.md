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

Issue #424 lands in three pull requests. This page covers the first two: one-off pages (`web.page.add`) and plugin routes behind a login session (`web.route.add`). Table pages come in the last one and will be added here.

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

## Serving a route

A one-off page is a link. A route is a page that a plugin serves for as long as it is loaded, at a fixed path under the plugin's own prefix. A browser needs a session to open it (see [Web Server](../web-server.md#sessions-and-login)).

```python
def _area_page(self, request) -> dict:
    area = request.query.get("area", "")
    return {"kind": "html", "title": f"Area {area}", "lines": self.area_lines(area)}

self.api("plugins.core.web:web.route.add")(self.plugin_id, "area", self._area_page, "Area map")
```

`web.route.add(owner, subpath, handler, title, columns=None, *, listed=True) -> str | None`

| Argument | Meaning |
| :--- | :--- |
| `owner` | Your plugin id. It must be the plugin that makes the call. |
| `subpath` | Lower case letters, digits, `_` and `-`, in segments separated by `/` (`^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)*$`), or `""` for the prefix itself. |
| `handler` | A function or coroutine function that takes a `Request` and returns a dict. |
| `title` | The text shown in the index at `/`. It is escaped. |
| `columns` | Optional. A list of dicts with `name`, `label`, `type` and an optional `long` that makes this a table route (see [Tables](#tables)). |
| `listed` | Optional, keyword only. `False` serves the route as usual (session, GET only) but leaves it out of the index at `/`. |

- **Listing.** List entry pages, not pages that need a parameter such as `?uid=`: register those with `listed=False` and reach them by links from other pages. An owner whose routes are all unlisted gets no heading in the index. Unlisted routes are still removed on unload and still counted by `#bp.core.web.status`.
- **URL derivation.** `plugins.` is dropped from the owner id and the dots become slashes. `plugins.aardwolf.mapper` with subpath `area` is served at `/aardwolf/mapper/area`; with `""` it is `/aardwolf/mapper`. A plugin cannot pick a path outside its own prefix. A prefix that starts with `p`, `login`, `static`, `ws`, `webclient` or `data` is reserved and refused, and so is a path that another plugin already serves.
- **Refusals.** The call logs an error and returns `None` when `owner` is not the calling plugin (`libs.api:caller.owner.get`), is not a valid plugin id, or the route table refuses the subpath or prefix. On success it returns the path.
- **Removal.** `web.route.remove(owner) -> int` removes a plugin's routes and returns how many. The web plugin also removes them when the plugin unloads (`ev_plugin_unloaded`), so a plugin only calls it to take routes down while it stays loaded. A reload of the web plugin itself keeps the routes, the sessions and the login tokens.
- **Methods.** GET only. A handler never sees a POST: it gets 405. A change of data would need CSRF protection, which is a later design.
- **No import of the web plugin.** Plugins call the API; the handler returns a plain dict.

### The request

The handler receives a frozen dataclass, `Request`, which it only reads.

| Field | Meaning |
| :--- | :--- |
| `method` | Always `"GET"`. |
| `path` | The decoded url path. |
| `query` | The first value of each query key, as `dict[str, str]`. |
| `cookies` | The cookies, as `dict[str, str]`. |
| `subpath` | The `subpath` the route was registered with. |
| `table` | A validated `TableQuery` on a route registered with `columns`, otherwise `None`. |

A query value is untrusted text. A page that reads a database runs fixed, parameterised queries and binds the values; it never builds SQL from the request.

### The response kinds

The handler returns a dict with a `kind`:

| Kind | Keys | Served as |
| :--- | :--- | :--- |
| `html` | `title`, `lines` (a list of strings or one string) | `text/html`. The web plugin escapes the title, and escapes and colour-converts the lines through `colorcode.to.html`, as for a one-off page. |
| `table` | `title`, `rows` (a list of lists or tuples, one cell per column), `total` (the row count before paging), optional `lines` | `text/html`: the title, the lines, a filter form, the table and paging links. Cells go through `colorcode.to.html`. Only valid on a route with `columns`, else 500. |
| `error` | `status` (400 or 404), `message` | `text/html`: the status page with the message escaped. Any other `status` returns 500. A handler uses it for a missing parameter (400) or an unknown id (404). |
| `svg` | `svg` (a string holding the document) | `image/svg+xml`. |
| `json` | `data` | `application/json`, from `json.dumps(data, default=str)`. |

Anything else, or a dict with a missing key, returns 500 and is logged.

- **SVG escaping.** The web plugin serves the SVG string as it is. A handler that puts MUD text, a room name for example, into an SVG must escape it with `html.escape(text, quote=True)` first, or the text can inject markup.
- **Errors and time.** A handler runs under a 30 second timeout (`HANDLER_TIMEOUT`). A timeout returns 504. An exception returns 500 and is logged with its traceback; the response carries no detail.
- **Slow work.** A synchronous handler runs on the event loop, so it must be quick and it cannot be timed out. Slow work, such as drawing a large map or a big query, belongs in an async handler that takes a snapshot of the data on the loop and runs the work with `await asyncio.to_thread(fn, snapshot)`. Do not call an API from the thread: the API is not thread-safe. The colour conversion of an `html` result happens on the loop, after the handler returns.

```python
async def _map_page(self, request) -> dict:
    rooms = list(self.rooms.values())  # a snapshot, taken on the loop
    svg = await asyncio.to_thread(draw_svg, rooms)
    return {"kind": "svg", "svg": svg}
```

### Tables

A route registered with `columns` serves a table that the browser can sort, filter and page through GET parameters. It works without any script, at any size.

```python
COLUMNS = [
    {"name": "name", "label": "Name", "type": "text"},
    {"name": "level", "label": "Lvl", "long": "Level", "type": "int"},
]
self.api("plugins.core.web:web.route.add")(self.plugin_id, "mobs", self._mobs, "Mobs", COLUMNS)
```

- **Columns.** `name` matches `[a-z0-9_]+` and is unique in the table, `label` is the header text and `type` is `text`, `int` or `float`. `long` is optional text, the full name: the header shows it on a first line and the short `label` in brackets on a second, in smaller muted monospace (classes in the page stylesheet, one sort link); a column without `long` shows the label alone. They are checked when the route is added; an invalid declaration is refused like a bad subpath (error logged, `None` returned).
- **The query.** Before the handler runs, the web plugin parses the query into `request.table`, a frozen `TableQuery`: `sort` (a column name or `None`), `descending`, `filters` (column name to a `str`, `int` or `float` according to the column type), `page` (1 or more), `count` (rows per page) and `offset` (`(page - 1) * count`). The parameters are `sort`, `dir` (`asc` or `desc`), `f_<column>`, `page` and `count`; an empty value counts as not given, because a GET form sends every box. Other keys stay in `request.query`.
- **400.** An unknown `sort` or `f_` column, a `dir` other than `asc` or `desc`, a `page` that is not an integer from 1 to 10,000,000, a `count` outside 1 to 500 (default 50), an `int` or `float` filter that does not parse (a float must be finite, an int must fit in 64 bits) or a text filter over 200 characters returns 400, and the handler is not called.
- **The handler** returns `{"kind": "table", "title", "rows", "total"}` for the one page described by `request.table`, with `total` the count of all rows that match the filters. Each row has one cell per column; a row of another width returns 500.
- **Link cells.** A cell may be `{"text": str, "href": str}` instead of text. It is rendered as `<a href="...">text</a>`: the text goes through `colorcode.to.html` like any cell, so a plugin escapes MUD text with `colorcode.escape` first, and the href is html-escaped. This format is stable; build it only with these two keys. The href must be a same-origin absolute path: it starts with `/`, not `//`, and has no backslash, whitespace or control character. Anything else (`javascript:x`, `http://x`, `//host`), a missing key, an extra key or a non-string `text` makes the page return 500 and the error is logged. Percent-encode query values yourself (`urllib.parse.urlencode`). The browser script reads cells with `textContent`, so a link cell sorts and filters by its text.
- **SQL.** Filter values are untrusted. Bind them as parameters, and let a column name only choose a fixed fragment; never put request text in the SQL string.

```python
ORDER = {"name": "name", "level": "level"}  # column name -> fixed SQL
WHERE = {"name": "name LIKE ?", "level": "level = ?"}

def _mobs(self, request) -> dict:
    query = request.table
    where, args = [], []
    for name, value in query.filters.items():
        where.append(WHERE[name])
        args.append(f"%{value}%" if name == "name" else value)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    order = f" ORDER BY {ORDER[query.sort]} {'DESC' if query.descending else 'ASC'}" if query.sort else ""
    total = db.execute("SELECT COUNT(*) FROM mobs" + clause, args).fetchone()[0]
    rows = db.execute(
        "SELECT name, level FROM mobs" + clause + order + " LIMIT ? OFFSET ?",
        [*args, query.count, query.offset],
    ).fetchall()
    return {"kind": "table", "title": "Mobs", "rows": rows, "total": total}
```

- **The page.** Header cells are sort links that keep the filters and toggle `dir`; a GET form has one `f_<column>` box per column plus hidden `sort`, `dir` and `count`; previous and next links keep the state. `data-pages` is on the `<table>` and `data-type` on each `<th>`.
- **The script.** A table page loads `/static/table.js`, which the core web plugin serves; plugins cannot ship scripts. When `data-pages` is 1 the script sorts the rows in the browser and adds a filter row; with more pages it does nothing and the links and form do the work. No other page loads it.

## Data providers

A data provider is a route that also has a topic, so a plugin registers its data once and the web plugin serves it. It is stored in the same table as routes, keyed under `/data` (`DATA_SEGMENT`; `data` is a reserved segment, so a route can never start with it): the path rules, the owner check, the 401 and 404 handling, the handler timeout and the removal on unload are the same. See [ADR-0025](../decisions/0025-the-web-plugin-serves-pages-and-a-client-websocket-from-one-listener-with-shared-sessions-and-data-providers.md).

```python
self.api("plugins.core.web:web.provider.add")(
    self.plugin_id, "mobsleft", self._mobs_snapshot,
    columns=[{"name": "mob", "label": "Mob"}, {"name": "left", "label": "Left", "type": "int"}],
    kind="table", event="ev_aardwolf_cp_mobs_changed", title="Campaign mobs left",
)
```

`web.provider.add(owner, name, snapshot, columns=None, kind="json", event=None, title=None) -> str | None`

| Argument | Meaning |
| :--- | :--- |
| `owner` | Your plugin id. It must be the plugin that makes the call. |
| `name` | A non-empty subpath, with the same rules as a route subpath. |
| `snapshot` | A sync or async function with no arguments that returns all the data as plain data. |
| `columns` | For `table` only, a list of dicts with `name`, `label` and `type`, optional `long` (the full name shown in the header), and optionally `colour: True` on a text column. A `json` provider refuses columns. |
| `kind` | `json` (the default) or `table`. |
| `event` | Optional. An event name that means the data changed. |
| `title` | Optional text. The page heading, the HTML `<title>` and the entry in the `/data/` index. It defaults to the topic. A value that is not text is refused. |

- **Topic and page.** The topic is the path without the leading `/`, with `.` for `/`. `plugins.aardwolf.cp` with `mobsleft` is the topic `aardwolf.cp.mobsleft`, served at `/data/aardwolf/cp/mobsleft`. `add` returns the topic.
- **json.** The page is the snapshot as JSON. **table.** The snapshot is every row (one cell per column, a cell may be a `{"text", "href"}` link); the web plugin filters, sorts and pages it for the request and escapes the cell text, so the snapshot returns plain MUD text. A bad table query is a 400, as for a table route.
- **Table snapshot mapping.** A `table` snapshot may return a mapping with keys from `rows`, `lines` and `unavailable` instead of a list. `lines` (a string or a list of strings) is shown above the table and is converted like a route page's lines. `unavailable` (a non-empty string) is shown in place of the table, after the lines; the page is still a 200 and `rows` may be left out. Without `unavailable`, `rows` is required. An unknown key or a wrong type is a `ValueError`: a 500 for the page and `snapshot_failed` over the socket. A plain list keeps today's behaviour. A `json` provider is never read this way.
- **Colour columns.** A column dict with `colour: True` (text columns only) leaves its cell text, or a link cell's text, unescaped, so colour codes in it are converted like a route page's. Other columns stay escaped, and no raw HTML is possible. A `colour` that is not a bool, or set on an int or float column, is refused.
- **Refusals.** The call logs an error and returns `None` for an owner that is not the caller, a bad name, kind or columns, or a path another plugin serves. A provider is served at `/data/<plugin path>/<name>` (the topic leaves out `/data`), so it can share a name with a route of the same plugin; both are served, and `web.route.remove` drops both. Added in #877; before it a provider sat at the route path and a clash was refused. The same owner adding the same name again replaces the provider.
- **Socket and unavailable.** A table provider whose snapshot has `unavailable` sends `data: null` and a top-level `unavailable` string in its `snapshot` and `update` (the optional field is in `socket-v1.schema.json`, so `v` stays 1). Any other snapshot, and every `json` provider, sends `data` only, as before. Added in #876.
- **Changed.** `web.provider.changed.raise(owner, name) -> bool` tells the listeners the data changed. It returns `False` and logs an error for a provider that is not the caller's or is unknown. The `event` argument does the same whenever that event is raised; the web plugin registers one handler per followed event and unregisters it when no provider follows it.
- **List.** `web.provider.list() -> list[str]` returns the sorted topics. The index at `/data/` lists the providers by owner (topic, kind, link; an empty list says so), behind the same session guard as `/`, and `/data` without the slash is a 404. The index at `/` lists only plain pages and links to `/data/`. `RouteTable.pages_by_owner()` and `providers_by_owner()` build the two lists. Also, `#bp.core.web.status` shows a `Providers` line next to `Routes` (which counts plain routes only), each provider as `topic (path)`.
- **Removal.** `web.route.remove(owner)` and the unload of the plugin remove its providers and their event registrations. A reload of the web plugin keeps the providers, and re-registers their events.
- **Listener interface.** Inside the web plugin, `ProviderListeners` (`add(listener)`, `remove(listener)`, `notify(topic)`) is held as `provider_listeners`. A listener is a function taking the topic. A listener that raises is logged and skipped. The client socket attaches here through `Subscriptions` (see Client socket). It is not saved on reload.

## Client socket

`src/bastproxy/plugins/core/web/libs/_ws.py` holds the socket code and `WebServer._answer` hands a `GET /ws` upgrade to it, after `WebApp.check_upgrade` has checked the session cookie (401) and the `Origin` (403). The handshake and framing are `websockets.server.ServerProtocol` (sans-I/O) over the reader and writer the server already owns; see [Web server](../web-server.md#client-socket) for the wire format, limits and close codes.

- **`SocketConnection`** has a bounded send queue (`send(message)` is synchronous and returns False when it cannot queue) and three tasks: a reader, a sender and a keepalive. `close(code, reason)` starts the close handshake and aborts the connection after `CLOSE_TIMEOUT`.
- **`SocketHub`** (`WebServer.sockets`) tracks the open sockets and holds the handlers of client message types. `register(type, handler)` and `unregister(type)` are the hook for later work; a handler takes `(connection, message)`, may be sync or async, and runs under the handler timeout. A handler that raises is logged and the client gets an `internal` error. `close_all(code, reason)` closes every socket; `connections()` returns a copy of the open sockets.
- **`Subscriptions`** (`src/bastproxy/plugins/core/web/libs/_subscribe.py`, held as `subscriptions`) registers the `subscribe` and `unsubscribe` handlers on the hub and a listener on `provider_listeners`. A socket's followed topics are `SocketConnection.subscriptions`; `Subscriptions` keeps only a trailing timer per topic (`DEBOUNCE`, 0.1 s) and the flush tasks. `changed(topic)` returns at once when nobody follows the topic. A flush runs the provider's `snapshot` (stored on `Provider.snapshot`, run by `run_snapshot`, also used by the HTTP handler) under the handler timeout and sends `update` to the sockets that follow. `RouteTable.topics()` is the sorted topic list used by `hello` and `web.provider.list`; `provider_for_topic(topic)` finds the route at `/data/` plus the topic with `.` as `/`. `removed(topics)` is called by `_remove_routes` (plugin unload and `web.route.remove`) and sends `topic_removed`. It looks up `self.routes` lazily because the table is replaced on reload, is not saved on reload and is closed by the close-server hook. See [Web server](../web-server.md#client-socket) for the messages.
- **Open and close listeners.** `SocketHub.add_listener(opened, closed)` and `remove_listener` register a pair of functions taking the connection. `SocketConnection.run` calls `hub.opened(connection)` after it queued `hello`, so `hello` stays the first message, and `hub.closed(connection)` once its tasks ended. A listener that raises is logged and skipped.
- **`view_only` and `send_wait`.** `SocketConnection.view_only` is set from the session (`SessionStore.is_view_only`) when the socket is created. `send_wait(message)` is the awaitable `send` for output: it waits while the send queue holds `OUTPUT_SHARE` (`SEND_QUEUE_LIMIT // 2`) messages, so a burst of MUD output does not trip the 256-message close, and returns False once the socket is closed.
- **`SocketClients` and `SocketClient`** (`src/bastproxy/plugins/core/web/libs/_proxyclient.py`, held as `socket_clients`) register the `input` and `cols` handlers and a hub listener. `opened` makes a `SocketClient` for the socket, registers it with the clients plugin and starts its writer task; `closed` removes it. The behaviour is described in [Data flow](data_flow.md#socket-clients-844-adr-0025). The plugin has its own `uninitialize` hook (priority 11, after `_phook_close_server`) that calls `SocketClients.close()`. It is not saved on reload.
- **`Calls`** (`src/bastproxy/plugins/core/web/libs/_call.py`, held as `command_calls`) registers the `call` handler on the hub. It checks `id` (string up to 64 characters or an integer), `command` and `args` (string or list of strings, joined with `shlex.join`), refuses a socket whose `view_only` is true (the `SocketConnection.view_only` field, set from a `#bp.core.web.viewlogin` session), runs the injected runner under `CALL_TIMEOUT` (25 s, below the hub's `HANDLER_TIMEOUT`) and answers `result`, with `reason: "timeout"` when the runner is too slow. The plugin passes `_run_call` (the `command.run.structured` api) as the runner and `_spans` (`colorcode.to.spans`) as the converter; each line of the reply becomes a list of spans. A runner exception goes to the hub, which answers `internal`. Closed by the close-server hook. See [Web server](../web-server.md#client-socket) for the messages.
- The constants (`MAX_MESSAGE`, `SEND_QUEUE_LIMIT`, `OUTPUT_SHARE`, `PING_INTERVAL`, `PING_TIMEOUT`, `CLOSE_TIMEOUT`, `READ_CHUNK`) are module level in `_ws.py`.

## Lifecycle

- `#bp.core.web.logout` also closes every socket with 4001.
- The web plugin starts its listener in a queued task (`libs.asynch:task.add`), so connections do not inherit the context of the command or event that started it.
- When the plugin unloads, it closes the listener, closes the open sockets with 1001 and aborts the other open connections before the base unload hook raises `ev_plugin_unloaded`.
- When the web plugin is reloaded, the stored pages, routes (and data providers), sessions and login tokens carry over (`attributes_to_save_on_reload`), so links and sessions keep working. The classes of these stores live in a module with `CANRELOAD = False`, so their identity survives the reload.
