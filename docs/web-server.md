---
title: Web Server
description: The web plugin serves pages that plugins publish over a small HTTP server, with its settings, commands, security model, and two ways to reach it remotely over TLS
audience:
  - users
  - contributors
tags:
  - web
---

# Web Server

The `plugins.core.web` plugin runs a small web server inside the proxy. Plugins use it to show output that is too long for the client, such as a record detail. A plugin stores a page and gets back a link; you open the link in a browser.

The server is **off by default**. The plugin is a core plugin, so it is always loaded, but it only listens when `enabled` is true. How plugins publish pages is in the [web system](claude/web_system.md) page, and the design is in [ADR-0022](decisions/0022-the-web-plugin-serves-token-links-and-session-gated-plugin-routes-over-a-get-only-standard-library-server.md).

The design of issue #424 lands in three pull requests. This page describes the first two: the server with its one-off page links, and plugin routes behind a login session. Table pages come in the last one and will add to this page.

## Quick start

```
#bp.core.web.set enabled true
#bp.core.web.status
#bp.debug.records.detail <uid> --web
```

The last command replies with a link such as `http://127.0.0.1:9998/p/<token>`. On a default setup the address only works on the machine the proxy runs on. To open links from another machine, use Setup A or Setup B below.

## Settings

Change them with `#bp.core.web.set <name> <value>`. A change to `enabled`, `port`, `bindaddress`, `certfile` or `keyfile` restarts the server. `publicurl` is read each time a link is made.

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `enabled` | `False` | Run the server. |
| `port` | `9998` | The port to listen on (1 to 65535). |
| `bindaddress` | `127.0.0.1` | The address to listen on: an IP address or `localhost`. |
| `certfile` | empty | The certificate file (PEM). Setting it, with `keyfile`, turns TLS on. A relative path is relative to `BASTPROXY_HOME`. |
| `keyfile` | empty | The private key file (PEM) of the certificate. |
| `publicurl` | empty | The base URL put in links, for example `https://bastproxy.example.net:9998`. The proxy cannot know the name a client reaches it by. When empty, links use the bind address and port. When it starts with `https://`, the session cookie is marked `Secure`. |
| `sessionhours` | `12` | How long a login session lasts, in hours (1 to 720). It is read when a session starts. |
| `clientdir` | empty | The directory of the built web client, served at `/webclient/` (see [Web client bundle](#web-client-bundle)). A relative path is relative to `BASTPROXY_HOME`. Empty turns it off. It is read on each request. |

**Upgrade note:** `certfile`, `keyfile` and `clientdir` were once resolved under `BASTPROXY_HOME/data/` by mistake. If you put files or symlinks there as a workaround, change the settings to paths relative to `BASTPROXY_HOME` (or absolute).

**Plain HTTP is allowed only on a loopback bind** (`127.0.0.1`, `::1`, `localhost`). If `bindaddress` is anything else and `certfile` or `keyfile` is empty, the server refuses to start and logs an error that names the setting. There is no override. Setting only one of `certfile` and `keyfile` also refuses to start.

## Commands

| Command | Does |
| :--- | :--- |
| `#bp.core.web.status` | Shows whether the server is running, on which address and port, and whether that is plain HTTP or TLS; the `publicurl`; in TLS mode the certificate's name, expiry and the file's modification time, when it was last reloaded, and the last reload error; and the number of pages held, the routes by owner, and the number of sessions. |
| `#bp.core.web.login` | Replies with a one-time login link, `<base>/login/<token>`. The command is not kept in the command history. When the server is not enabled it says so. |
| `#bp.core.web.logout` | Ends every session and reports how many there were. |
| `#bp.core.web.reload` | Reloads the certificate and key now. A reload that fails keeps the previous certificate and says why. |

`status` reads the certificate with a TLS handshake held in memory between two `ssl` objects, using only the standard library. If the certificate has expired, `status` says `expired` and shows the file's modification time. If the handshake fails for another reason, it shows the modification time and `details unavailable`.

## Security model for page links

- **The link is the credential.** Each page has a random token (`secrets.token_urlsafe(32)`, 256 bits) in its URL, `/p/<token>`. Anyone who has the link can read that page until it expires; nobody can guess one. The proxy password is never used, because sending it over HTTP would expose it.
- **Pages are kept in memory only.** At most 50 pages are held, and a page lasts one hour. The oldest page goes first. A restart drops them all. A reload of the web plugin keeps them.
- **Unknown or expired tokens return 404.** An unknown path returns 404 too. The index and the plugin routes return 401 without a session; see [Sessions and login](#sessions-and-login).
- **GET only.** Any other method returns 405.
- **Limits.** The request head is at most 8 KiB (larger gets 431), a client has 10 seconds to send it, at most 32 connections are open at once (more are closed at once), the TLS handshake has 10 seconds, and no request body is ever read. Every response closes the connection.
- **Output is escaped.** The text of a page is MUD output, so it is HTML-escaped. Colour codes become `span` elements with inline colours, and raw terminal escape sequences are dropped.
- **Response headers.** Every response, including errors, carries these:

  | Header | Value |
  | :--- | :--- |
  | `Content-Security-Policy` | `default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'` |
  | `Referrer-Policy` | `no-referrer` |
  | `Cache-Control` | `no-store` |
  | `X-Content-Type-Options` | `nosniff` |

  The one exception is a successful file response under `/webclient/`: its `Content-Security-Policy` is the policy above plus `connect-src 'self'; font-src 'self'`. Errors there carry the policy above.

  The page you get from a link contains no script at all. Only table pages of routes load a script (see below).
- **One static script.** The web plugin serves `/static/table.js`, a vanilla JS file shipped in the package, without a session. It is the only script: pages never carry an inline script, and the policy `script-src 'self'` allows nothing else. Table pages link to it with `<script src="/static/table.js" defer>`. It sorts and filters the rows in the browser when a result fits on one page, writes only through `textContent` and moved nodes, and never uses `innerHTML`, `eval` or `fetch`. Any other `/static/` path returns 404. Plugins cannot add scripts.
- **Sessions.** The cookie is `HttpOnly`, `SameSite=Strict` and `Path=/`, and `Secure` with TLS or an `https://` `publicurl`. Login links work once and last 5 minutes; sessions last `sessionhours` and live in memory only.
- **Tokens show up in places.** The link is in the command's reply, so it is in the client's scrollback and in the record of that command (`#bp.debug.records` trees hold the reply text). Treat the reply like a password until the page expires, and do not paste it in a shared channel.
- **Logs never hold a full token.** At most the first 6 characters are logged.

## Sessions and login

Pages that plugins serve at a path of their own (routes, see the [web system](claude/web_system.md#serving-a-route)) and the index at `/` need a session. A one-off page link does not.

1. Run `#bp.core.web.login`. The reply is a link, `<base>/login/<token>`, built like the page links. You are already logged in to the proxy, so the proxy password never goes over HTTP.
2. Open the link. It works once and expires after 5 minutes. The server starts a session, sends `303` to `/` and sets the cookie.
3. `/` lists the registered pages by plugin and title.
4. `#bp.core.web.logout` ends every session. A restart ends them too, because sessions are kept in memory only.

The session cookie, `bpsession`, holds a random id (`secrets.token_urlsafe(32)`) and has these attributes:

| Attribute | Value |
| :--- | :--- |
| `HttpOnly` | Always. |
| `SameSite` | `Strict`. |
| `Path` | `/`. |
| `Max-Age` | `sessionhours` times 3600. |
| `Secure` | When the server uses TLS, or when `publicurl` starts with `https://`. The second case covers a reverse proxy that ends TLS (Setup B). |

At most 20 sessions are held; the oldest goes first. Without a valid session (none, expired or forged), `/` and every route return 401 with a page that tells you to run `#bp.core.web.login`, shown with your command prefix. An unknown path returns 404 with or without a session. The login link is a credential like a page link: see the notes on tokens below.

## Setup A: built-in TLS

Use this when you can give the proxy a certificate for a name that resolves to the machine, and want to open links from other machines directly.

1. Pick a name, for example `bastproxy.example.net`, and make a DNS record for it that points at the address the client will use (a public address, a VPN address or a tailnet address). Use a **DNS-only** record; see the Cloudflare note below.
2. Get a certificate, with one of the methods below, and put the files where the proxy's own user can read them, for example `<BASTPROXY_HOME>/certs/fullchain.pem` and `<BASTPROXY_HOME>/certs/key.pem`.
3. Configure the proxy:

   ```
   #bp.core.web.set bindaddress 0.0.0.0
   #bp.core.web.set certfile certs/fullchain.pem
   #bp.core.web.set keyfile certs/key.pem
   #bp.core.web.set publicurl https://bastproxy.example.net:9998
   #bp.core.web.set enabled true
   ```

   Use the address of one interface instead of `0.0.0.0` to listen on one network only. Open the port in the firewall, and forward it on the router when the client is on the internet.
4. Run `#bp.core.web.status`. It should say `running, TLS`, and show the certificate name and expiry.
5. Run `#bp.debug.records.detail <uid> --web` and open the link.

### Getting a certificate with DNS-01

A name that is only reachable privately, for example one that resolves to a VPN or tailnet address, can still get a publicly trusted certificate. With the DNS-01 challenge the certificate authority checks a TXT record in your DNS zone, so the host never has to be reachable from the internet.

An example with acme.sh and Cloudflare DNS, run as the proxy's own user so no root and no copy step are needed:

```bash
export CF_Token=<token>
acme.sh --issue --dns dns_cf -d bastproxy.example.net
acme.sh --install-cert -d bastproxy.example.net \
  --key-file <BASTPROXY_HOME>/certs/key.pem \
  --fullchain-file <BASTPROXY_HOME>/certs/fullchain.pem
```

- Create the Cloudflare API token with one permission, **Zone → DNS → Edit**, limited to that one zone.
- acme.sh renews on its own schedule and installs the files again. The plugin notices the changed files and uses the new certificate for the next connection, so no restart is needed.
- The alternative is certbot with the `certbot-dns-cloudflare` plugin and a `--deploy-hook` that copies the renewed files to `<BASTPROXY_HOME>/certs/` and makes them readable by the proxy's user.

**Cloudflare-proxied records.** A record proxied through Cloudflare (the orange cloud) only passes a fixed set of HTTPS ports and puts Cloudflare between the client and the proxy. Use a DNS-only record.

**Certificate Transparency.** Publicly trusted certificates are published in Certificate Transparency logs. The name you chose becomes visible there, though the host stays unreachable.

### A self-signed certificate, for testing

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=bastproxy.test" \
  -addext "subjectAltName=DNS:bastproxy.test" \
  -keyout <BASTPROXY_HOME>/certs/key.pem -out <BASTPROXY_HOME>/certs/fullchain.pem
```

A browser warns about it until you trust the certificate.

### Certificate reload

Before each new connection the plugin compares the modification times of the certificate and key files. When either changed, it builds a new TLS context from the files, so a renewal needs no restart. A failed reload, for example when a renewal has written the new key but not yet the new certificate, keeps the previous context and logs an error. The next change to either file tries again. `#bp.core.web.reload` forces a reload and reports the error.

### The name has to match

The name in `publicurl` has to be a name the certificate covers (its subject name or a subject alternative name), or the browser shows a warning. `#bp.core.web.status` shows the names the certificate has.

## Setup B: a TLS front end

Use this when something else handles TLS and the proxy stays on loopback. The proxy keeps its default `bindaddress` of `127.0.0.1`, serves plain HTTP, and has no certificate settings. Only `publicurl` is set, to the front end's HTTPS URL. The per-page tokens still protect pages from other devices that can reach the front end.

### Tailscale

1. In the tailnet admin console, enable **MagicDNS** and **HTTPS Certificates**.
2. Start the proxy's web server on loopback:

   ```
   #bp.core.web.set enabled true
   ```

3. On the machine that runs the proxy, serve the loopback port on the tailnet (`tailscale serve --help` describes the command):

   ```bash
   tailscale serve --bg 9998
   ```

   The page is then at `https://<machine>.<tailnet>.ts.net`. Tailscale obtains and renews the certificate itself.
4. Tell the proxy the URL:

   ```
   #bp.core.web.set publicurl https://<machine>.<tailnet>.ts.net
   ```

5. Run `#bp.debug.records.detail <uid> --web` and open the link from a device on the tailnet.

Do not use `tailscale funnel`: it makes the page public on the internet.

### Caddy

```
bastproxy.example.net {
    reverse_proxy 127.0.0.1:9998
}
```

Caddy gets and renews a certificate for the name. Set `publicurl` to `https://bastproxy.example.net`.

### nginx

```nginx
server {
    listen 443 ssl;
    server_name bastproxy.example.net;
    ssl_certificate     /etc/ssl/bastproxy/fullchain.pem;
    ssl_certificate_key /etc/ssl/bastproxy/key.pem;

    location / {
        proxy_pass http://127.0.0.1:9998;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

Set `publicurl` to `https://bastproxy.example.net`. The `Upgrade` and `Connection` lines let the client socket through; the proxy sends the `Origin` it received on to bastproxy unchanged, so it must equal `publicurl`.

## Web client bundle

The `clientdir` setting points at a built web client. Files under it are served at `/webclient/`, behind the session; `/webclient/` itself serves `index.html`. (`/client/` is not used: the mapper plugin serves pages under `/client/mapper`.)

- **Off by default.** With `clientdir` empty, or not an existing directory, every `/webclient/` request is 404. With a directory and no session it is 401, before any file is touched.
- **Refusals are 404.** Every path segment must match `^[A-Za-z0-9_][A-Za-z0-9._-]*$`, so `..`, hidden files, empty segments and backslashes are refused. The file must resolve inside the directory (a symlink that leaves it is refused), be a regular file, and be at most 8 MiB. A larger file is also logged.
- **Types.** Only these suffixes are served: `.html`, `.js`, `.css`, `.json`, `.svg`, `.png` and `.woff2`. Anything else, such as `.map`, is 404.
- **Policy.** Files served here carry the client policy described under Response headers; `Cache-Control: no-store` and the other headers stay. The segment `webclient` is reserved, so no plugin route or provider can use it.

## Client socket

The listener also answers a WebSocket upgrade at `/ws`, on the same port, TLS and connection cap (a socket counts as one connection). `GET /ws` without an upgrade is 404.

- **Who may connect.** The `bpsession` cookie must be a live session, else 401. The `Origin` header must be present, appear once and equal the origin of `publicurl` (or of the address the server listens on when it is unset), compared with a lower-case scheme and host and the default port dropped; anything else is 403. Both refusals carry the usual security headers. A missing key is 400 and a missing `Connection: Upgrade` is 426.
- **Messages.** JSON text frames shaped `{"v": 1, "type": ...}`. The proxy sends `{"v":1,"type":"hello","protocol":1,"proxy":"<version>","connection":"<id>","topics":[...]}` first, where `topics` lists every provider topic (sorted; all sessions are equal today, so all of them). The connection id is new for each socket; the session id is never sent. A client message that is not valid JSON, not an object, has no string `type`, has a `v` other than the integer 1, or has a type nobody handles gets `{"v":1,"type":"error","code":...,"message":...}` (codes `bad_json`, `bad_message`, `version`, `unknown_type`, `internal`, with `for` naming the type when known). An error never closes the socket.
- **Subscriptions.** `{"v":1,"type":"subscribe","topic":"<topic>"}` is answered with `{"v":1,"type":"snapshot","topic":...,"data":...}`, then each change of the provider sends `{"v":1,"type":"update","topic":...,"data":...}`. `data` is the whole value the provider's snapshot returns (v1 sends full snapshots, no diffs; table providers send their raw rows, without paging or colour escaping). Changes are debounced per topic: the first change starts a 100 ms timer and a burst inside it sends one update. `{"v":1,"type":"unsubscribe","topic":...}` stops updates; it has no reply and is safe to repeat. Subscribing again sends a fresh snapshot, and `update` never comes before `snapshot`. Errors carry the `topic` and, when answering a `subscribe`, `for: "subscribe"`: `bad_message` (no string topic), `unknown_topic`, `snapshot_failed` (the snapshot raised; only that topic is affected and an existing subscription stays), and `topic_removed` (the provider was unloaded or removed; the subscription is dropped). A subscription ends with the socket. Updates use the same send queue and its limit as every other message.
- **Limits.** A message is at most 64 KiB (close 1009), the send queue holds 256 messages (close 1008) and binary frames are refused (close 1003). The proxy pings every 20 seconds and closes with 1011 when nothing arrived for 40 seconds.
- **Close codes.** 1001 for a shutdown or plugin unload, 4001 when `#bp.core.web.logout` ends the session or the session is no longer valid (checked at each ping), plus the codes above. `#bp.core.web.status` shows a `Sockets` line.

## Data providers

A plugin can register its data once with `web.provider.add`. The data is then served as a page behind the session, as JSON or as a table, at a path built from the plugin id; see [Data providers](claude/web_system.md#data-providers). `#bp.core.web.status` shows a `Providers` line, and the index at `/` lists provider pages with the routes.

## Related

- [Web system](claude/web_system.md) for plugin authors.
- [ADR-0025](decisions/0025-the-web-plugin-serves-pages-and-a-client-websocket-from-one-listener-with-shared-sessions-and-data-providers.md) for data providers.
- [ADR-0022](decisions/0022-the-web-plugin-serves-token-links-and-session-gated-plugin-routes-over-a-get-only-standard-library-server.md).
