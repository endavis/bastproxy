# Project: bastproxy
# Filename: plugins/core/web/plugin/_web.py
#
# File Description: a plugin that serves web pages for plugins
#
# By: Bast
"""The web plugin: a GET-only HTTP server that plugins publish pages through."""

# Standard Library
import asyncio
import logging
import ssl
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bastproxy import __version__
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.validators import int_range

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddCommand, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.web.libs._call import Calls
from bastproxy.plugins.core.web.libs._proxyclient import SocketClients
from bastproxy.plugins.core.web.libs._render import render_page
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import (
    LoginTokens,
    PageStore,
    ProviderListeners,
    RouteTable,
    SessionStore,
)
from bastproxy.plugins.core.web.libs._subscribe import Subscriptions
from bastproxy.plugins.core.web.libs._tls import (
    CertManager,
    all_loopback,
    cert_details,
    parse_bind_addresses,
    validate_bind_address,
)
from bastproxy.plugins.core.web.libs._ws import CLOSE_SESSION_ENDED


def _login_reply(plugin: Any, *, view_only: bool) -> tuple[bool, list[str]]:
    """The reply of a login command: a one-time link, full or view-only."""
    if not plugin._setting("enabled"):
        return True, ["the web server is not enabled (set enabled true)"]
    escape = plugin.api("plugins.core.colors:colorcode.escape")
    token = plugin.logins.issue(view_only=view_only)
    kind = "view-only login" if view_only else "login"
    log_to([plugin.plugin_id], logging.DEBUG, "%s token %s issued", kind, token[:6])
    label = "View-only login link" if view_only else "Login link"
    return True, [f"{label}: {escape(f'{plugin._base_url()}/login/{token}')}"]


class WebPlugin(BasePlugin):
    """a plugin that serves web pages for plugins."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.pages = PageStore()
        self.routes = RouteTable()
        self.provider_listeners = ProviderListeners()
        self.logins = LoginTokens()
        self.sessions = SessionStore()
        self.server = WebServer()
        # a lazy lookup: self.routes is replaced when the plugin reloads
        self.subscriptions = Subscriptions(
            self.server.sockets, lambda: self.routes, self.provider_listeners
        )
        self.socket_clients = SocketClients(self.server.sockets)
        self.command_calls = Calls(
            self.server.sockets,
            lambda command, arguments: self._run_call(command, arguments),
            lambda text: self._spans(text),
        )
        self.cert: CertManager | None = None
        self._generation = 0
        self._restart_sequence = 0
        self._lock = asyncio.Lock()
        self.attributes_to_save_on_reload = ["pages", "routes", "sessions", "logins"]

    @RegisterPluginHook("after_load")
    def _phook_initialize(self) -> None:
        """Add the settings."""
        add = self.api("plugins.core.settings:setting.add")
        add(self.plugin_id, "enabled", False, bool, "run the web server")
        add(
            self.plugin_id,
            "port",
            9998,
            int,
            "the port the web server listens on",
            validator=int_range(1, 65535, label="port"),
        )
        add(
            self.plugin_id,
            "bindaddress",
            "127.0.0.1",
            str,
            "the addresses to listen on, an IP address or localhost, comma-separated for "
            "several (0.0.0.0,::); anything but loopback addresses needs a certificate",
            validator=validate_bind_address,
        )
        add(
            self.plugin_id,
            "certfile",
            "",
            str,
            "the certificate file (PEM) that turns TLS on; relative to BASTPROXY_HOME",
        )
        add(
            self.plugin_id,
            "keyfile",
            "",
            str,
            "the private key file (PEM) for the certificate; relative to BASTPROXY_HOME",
        )
        add(
            self.plugin_id,
            "publicurl",
            "",
            str,
            "the base url used in links, for example https://bastproxy.example.net:9998",
        )
        add(
            self.plugin_id,
            "sessionhours",
            12,
            int,
            "how many hours a login session lasts",
            validator=int_range(1, 720, label="hours"),
        )
        add(
            self.plugin_id,
            "clientdir",
            "",
            str,
            "the directory of the built web client, served at /webclient/; "
            "relative to BASTPROXY_HOME, empty is off",
        )

    @RegisterPluginHook("after_load", priority=80)
    def _phook_start(self) -> None:
        """Start the server once the settings are initialised."""
        self._schedule_restart()

    def _run_call(self, command: str, arguments: str) -> dict[str, Any]:
        """Run a command for a client socket call."""
        reply: dict[str, Any] = self.api("plugins.core.commands:command.run.structured")(
            command, arguments
        )
        return reply

    def _spans(self, text: str) -> list[dict[str, Any]]:
        """Split colour coded text into spans for a client socket."""
        spans: list[dict[str, Any]] = self.api("plugins.core.colors:colorcode.to.spans")(text)
        return spans

    @RegisterPluginHook("after_load", priority=85)
    def _phook_sync_provider_events(self) -> None:
        """Follow the events of the providers a reload carried over."""
        self._sync_provider_events(set())

    @RegisterPluginHook("uninitialize", priority=10)
    def _phook_close_server(self) -> None:
        """Stop the listener before the base hook raises the unloaded events."""
        self._generation += 1
        self.subscriptions.close()
        self.command_calls.close()
        self.server.close()
        self.api("libs.asynch:task.add")(self.server.wait_closed(), f"{self.plugin_id}:close")

    @RegisterPluginHook("uninitialize", priority=11)
    def _phook_close_socket_clients(self) -> None:
        """Drop the socket clients and their handlers."""
        self.socket_clients.close()

    @RegisterToEvent(event_name="ev_{plugin_id}_var_enabled_modified")
    @RegisterToEvent(event_name="ev_{plugin_id}_var_port_modified")
    @RegisterToEvent(event_name="ev_{plugin_id}_var_bindaddress_modified")
    @RegisterToEvent(event_name="ev_{plugin_id}_var_certfile_modified")
    @RegisterToEvent(event_name="ev_{plugin_id}_var_keyfile_modified")
    def _eventcb_restart_setting_modified(self) -> None:
        """A setting the listener depends on changed."""
        self._schedule_restart()

    def _setting(self, name: str) -> object:
        return self.api("plugins.core.settings:setting.get")(self.plugin_id, name)

    def _schedule_restart(self) -> None:
        """Queue a restart; the queued task gets a fresh context, not this caller's.

        Each request takes the next sequence number, so a queued restart that a
        newer one has overtaken returns without touching the listener.
        """
        self._restart_sequence += 1
        self.api("libs.asynch:task.add")(
            self._restart(self._generation, self._restart_sequence),
            f"{self.plugin_id}:restart",
        )

    def _build_app(self) -> WebApp:
        """The request dispatcher, wired to this plugin's stores and settings."""
        return WebApp(
            self.pages,
            routes=self.routes,
            logins=self.logins,
            sessions=self.sessions,
            to_html=self.api("plugins.core.colors:colorcode.to.html"),
            login_command=lambda: self.api("plugins.core.commands:command.format")(
                self.plugin_id, "login"
            ),
            secure_cookie=self._secure_cookie,
            session_seconds=lambda: int(str(self._setting("sessionhours"))) * 3600,
            client_dir=self._client_dir,
            allowed_origins=lambda: [self._base_url()],
            proxy_version=__version__,
        )

    def _client_dir(self) -> Path | None:
        """The web client directory, or None when the setting is empty."""
        if not str(self._setting("clientdir")):
            return None
        return self._path("clientdir")

    def _secure_cookie(self) -> bool:
        """The session cookie is Secure with TLS, or when the public url is https."""
        return self.server.tls or str(self._setting("publicurl")).startswith("https://")

    def _path(self, name: str) -> Path:
        """A path setting, relative to BASTPROXY_HOME unless absolute."""
        return Path(self.api.BASEHOMEPATH) / str(self._setting(name))

    async def _restart(self, generation: int, sequence: int | None = None) -> None:
        """Close the listener and start it again from the settings.

        A ``sequence`` older than the latest request is skipped: the newer
        restart reads the same settings and does the work once.
        """
        async with self._lock:
            if sequence is not None and sequence != self._restart_sequence:
                return
            self.server.close()
            self.cert = None
            await self.server.wait_closed()
            if generation != self._generation or not self._setting("enabled"):
                return
            hosts = parse_bind_addresses(str(self._setting("bindaddress")))
            port = int(str(self._setting("port")))
            has_cert = bool(self._setting("certfile"))
            has_key = bool(self._setting("keyfile"))
            if has_cert != has_key:
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "web server not started: certfile and keyfile must both be set",
                )
                return
            if not has_cert and not all_loopback(hosts):
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "web server not started: bindaddress %s is not all loopback addresses, "
                    "so certfile and keyfile must be set (plain http is only allowed on loopback)",
                    ", ".join(hosts),
                )
                return
            cert: CertManager | None = None
            if has_cert:
                cert = CertManager(self._path("certfile"), self._path("keyfile"))
                try:
                    cert.load()
                except (OSError, ssl.SSLError) as exc:
                    log_to(
                        [self.plugin_id],
                        logging.ERROR,
                        "web server not started: cannot load the certificate: %s",
                        exc,
                    )
                    return
            try:
                await self.server.start(hosts, port, self._build_app(), cert)
            except OSError as exc:
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "web server not started: cannot listen on %s port %s: %s",
                    ", ".join(hosts),
                    port,
                    exc,
                )
                return
            if generation != self._generation:
                # the plugin unloaded while the server was starting
                self.server.close()
                return
            self.cert = cert
            log_to(
                [self.plugin_id],
                logging.INFO,
                "web server listening on %s (%s)",
                self.server.address,
                "TLS" if self.server.tls else "plain http",
            )

    def _base_url(self) -> str:
        """The base url for links: ``publicurl`` or the address the server listens on."""
        public = str(self._setting("publicurl")).rstrip("/")
        if public:
            return public
        host = parse_bind_addresses(str(self._setting("bindaddress")))[0]
        if ":" in host:
            host = f"[{host}]"
        scheme = "https" if self.server.tls else "http"
        return f"{scheme}://{host}:{self._setting('port')}"

    @AddAPI("web.page.add", description="publish a page and get its link")
    def _api_web_page_add(self, owner: str, title: str, lines: list[str] | str) -> str:
        """Store one page that expires and return its link.

        @Yowner@w   = the plugin id publishing the page
        @Ytitle@w   = the page title
        @Ylines@w   = the text, with @@ colour codes; it is escaped and converted to html

        The link is the credential. This returns an empty string when the web server is
        not enabled.
        """
        if not self._setting("enabled"):
            return ""
        to_html = self.api("plugins.core.colors:colorcode.to.html")
        document = render_page(title, lines, to_html)
        token = self.pages.add(owner, title, document.encode("utf-8"))
        log_to([self.plugin_id], logging.DEBUG, "page %s added by %s", token[:6], owner)
        return f"{self._base_url()}/p/{token}"

    @AddAPI("web.route.add", description="serve a page under the plugin's own path")
    def _api_web_route_add(
        self,
        owner: str,
        subpath: str,
        handler: Callable[..., Any],
        title: str,
        columns: list[dict[str, str]] | None = None,
        *,
        listed: bool = True,
    ) -> str | None:
        """Serve a page at ``/<plugin path>/<subpath>`` for a logged in browser.

        @Yowner@w     = the plugin id; it must be the calling plugin
        @Ysubpath@w   = lower case letters, digits, _ and -, separated by /; "" for the prefix
        @Yhandler@w   = a sync or async function taking a Request, returning a dict
        @Ytitle@w     = the title shown in the index
        @Ycolumns@w   = for a table route, a list of dicts with name, label and type
                        (text, int or float); the handler then gets ``request.table`` and
                        returns a ``table`` dict
        @Ylisted@w    = False keeps the route out of the index at /; it is still served

        The path comes from the plugin id: plugins.aardwolf.mapper is served at
        /aardwolf/mapper/<subpath>. Returns the path, or None (and logs an error) when the
        route is refused.
        """
        return self._refuse(
            "route",
            subpath,
            owner,
            lambda: self.routes.add(owner, subpath, handler, title, columns, listed=listed),
        )

    def _refuse(self, what: str, name: str, owner: str, add: Callable[[], str]) -> str | None:
        """Run ``add`` for the calling plugin; log and return None when it is refused."""
        caller = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
        error = ""
        if owner != caller:
            error = f"{owner} is not the calling plugin ({caller})"
        elif not self.api("libs.plugins.loader:plugin.id.is.valid")(owner):
            error = f"{owner} is not a plugin id"
        else:
            try:
                return add()
            except ValueError as exc:
                error = str(exc)
        log_to(
            [self.plugin_id, owner],
            logging.ERROR,
            "web %s %r refused for %s: %s",
            what,
            name,
            owner,
            error,
        )
        return None

    def _escape(self, text: str) -> str:
        """Escape colour codes in provider text."""
        return str(self.api("plugins.core.colors:colorcode.escape")(text))

    @AddAPI("web.provider.add", description="register a data provider served as a page")
    def _api_web_provider_add(
        self,
        owner: str,
        name: str,
        snapshot: Callable[[], Any],
        columns: list[dict[str, str]] | None = None,
        kind: str = "json",
        event: str | None = None,
    ) -> str | None:
        """Register a data provider; its data is served at ``/<plugin path>/<name>``.

        @Yowner@w      = the plugin id; it must be the calling plugin
        @Yname@w       = lower case letters, digits, _ and -, separated by /; not empty
        @Ysnapshot@w   = a sync or async function returning the whole data: any json value
                         for ``json``, a list of rows (one cell per column) for ``table``
        @Ycolumns@w    = for ``table``, a list of dicts with name, label and type
        @Ykind@w       = ``json`` or ``table``
        @Yevent@w      = an event name; when it is raised, listeners are told the data changed

        The topic is the path without the leading slash and with . for /. Returns the
        topic, or None (and logs an error) when the provider is refused.
        """
        before = self.routes.provider_events()
        topic = self._refuse(
            "provider",
            name,
            owner,
            lambda: self.routes.add_provider(
                owner, name, snapshot, columns, kind, event, self._escape
            ),
        )
        self._sync_provider_events(before)
        return topic

    @AddAPI(
        "web.provider.changed.raise", description="tell the listeners a provider's data changed"
    )
    def _api_web_provider_changed_raise(self, owner: str, name: str) -> bool:
        """Tell the listeners that the data of a provider changed.

        @Yowner@w   = the plugin id; it must be the calling plugin
        @Yname@w    = the name the provider was added with

        Returns False (and logs an error) for another plugin's provider or an unknown one.
        """
        caller = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
        route = self.routes.provider(owner, name)
        if owner != caller or route is None or route.provider is None:
            log_to(
                [self.plugin_id, caller],
                logging.ERROR,
                "web provider %r changed refused for %s: not a provider of the calling plugin",
                name,
                owner,
            )
            return False
        self.provider_listeners.notify(route.provider.topic)
        return True

    @AddAPI("web.provider.list", description="list the provider topics")
    def _api_web_provider_list(self) -> list[str]:
        """Return the topics of all providers, sorted."""
        return self.routes.topics()

    def _sync_provider_events(self, before: set[str]) -> None:
        """Register for the events providers now follow and drop those no one follows.

        ``before`` is the set of followed events before the change.
        """
        after = self.routes.provider_events()
        events = "plugins.core.events:"
        for name in sorted(after - before):
            self.api(f"{events}event.register")(name, self._provider_event_fired)
        for name in sorted(before - after):
            self.api(f"{events}event.unregister")(name, self._provider_event_fired)

    def _provider_event_fired(self) -> None:
        """A followed event was raised: tell the listeners about the topics that follow it."""
        name = self.api("plugins.core.events:event.current.name.get")()
        for topic in self.routes.topics_for_event(name):
            self.provider_listeners.notify(topic)

    @AddAPI("web.route.remove", description="remove the routes of a plugin")
    def _api_web_route_remove(self, owner: str) -> int:
        """Remove every route and data provider of a plugin and return how many there were.

        @Yowner@w   = the plugin id
        """
        return self._remove_routes(owner)

    def _remove_routes(self, owner: str) -> int:
        """Remove the routes of an owner, follow the events that changed, tell subscribers."""
        before = self.routes.provider_events()
        topics = [r.provider.topic for r in self.routes.by_owner().get(owner, []) if r.provider]
        removed = self.routes.remove(owner)
        self._sync_provider_events(before)
        self.subscriptions.removed(topics)
        return removed

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded: drop its routes."""
        event_record = self.api("plugins.core.events:event.current.record.get")()
        removed = self._remove_routes(event_record["plugin_id"])
        if removed:
            log_to(
                [self.plugin_id, event_record["plugin_id"]],
                logging.DEBUG,
                "removed %s web routes of %s",
                removed,
                event_record["plugin_id"],
            )

    @AddCommand(show_in_history=False)
    @AddParser(description="get a one-time link that logs a browser in")
    def _command_login(self) -> CommandResult:
        """Give a login link; it works once and expires after 5 minutes."""
        success, message = _login_reply(self, view_only=False)
        return CommandResult(success, message)

    @AddCommand(show_in_history=False)
    @AddParser(description="get a one-time link that logs a browser in view-only")
    def _command_viewlogin(self) -> CommandResult:
        """Give a view-only login link; it works once and expires after 5 minutes."""
        success, message = _login_reply(self, view_only=True)
        return CommandResult(success, message)

    @AddParser(description="end every web session")
    def _command_logout(self) -> CommandResult:
        """End all sessions."""
        count = self.sessions.clear()
        self.server.sockets.close_all(CLOSE_SESSION_ENDED, "session ended")
        return CommandResult(True, [f"ended {count} web session{'' if count == 1 else 's'}"])

    @AddParser(description="show the state of the web server")
    def _command_status(self) -> CommandResult:
        """Show whether the server is running, where, and its certificate."""
        escape = self.api("plugins.core.colors:colorcode.escape")
        if self.server.running:
            mode = "TLS" if self.server.tls else "plain http"
            state = f"running, {mode}, on {self.server.address}"
        elif self._setting("enabled"):
            state = "enabled but not running (see the log)"
        else:
            state = "stopped (enabled is false)"
        message = [
            f"{'Server':<14}: {escape(state)}",
            f"{'Public url':<14}: {escape(str(self._setting('publicurl')) or '(not set)')}",
        ]
        if self.cert is not None:
            details = cert_details(self.cert.certfile, self.cert.keyfile)
            message.append(f"{'Certificate':<14}: {escape(self._describe_cert(details))}")
            if self.cert.last_reload is not None:
                stamp = self.cert.last_reload.strftime("%Y-%m-%d %H:%M:%S %Z")
                message.append(f"{'Last reload':<14}: {stamp}")
            if self.cert.last_error:
                message.append(f"{'Last error':<14}: {escape(self.cert.last_error)}")
        message.append(f"{'Pages held':<14}: {self.pages.count()}")
        by_owner = self.routes.by_owner()
        plain = {
            owner: [r for r in items if r.provider is None] for owner, items in by_owner.items()
        }
        routes = ", ".join(f"{owner} ({len(items)})" for owner, items in plain.items() if items)
        message.append(
            f"{'Routes':<14}: {self.routes.count()}" + (f" - {escape(routes)}" if routes else "")
        )
        topics = ", ".join(r.provider.topic for r in self.routes.providers() if r.provider)
        message.append(
            f"{'Providers':<14}: {self.routes.provider_count()}"
            + (f" - {escape(topics)}" if topics else "")
        )
        message.append(f"{'Sessions':<14}: {self.sessions.count()}")
        message.append(f"{'Sockets':<14}: {self.server.sockets.count()}")
        return CommandResult(True, message)

    @staticmethod
    def _describe_cert(details: dict[str, Any]) -> str:
        """One line about a certificate from ``cert_details``."""
        mtime = details["mtime"]
        modified = f"file modified {mtime:%Y-%m-%d %H:%M}" if mtime else "file not readable"
        if details["state"] == "ok":
            return f"{details['subject']}, expires {details['not_after']}, {modified}"
        if details["state"] == "expired":
            return f"expired, {modified}"
        return f"details unavailable, {modified}"

    @AddParser(description="reload the certificate now")
    def _command_reload(self) -> CommandResult:
        """Reload the certificate and key files without waiting for a change."""
        if self.cert is None:
            return CommandResult(True, ["TLS is not active, there is no certificate to reload"])
        if self.cert.reload():
            return CommandResult(True, ["certificate reloaded"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        return CommandResult(
            True,
            [f"reload failed, keeping the previous certificate: {escape(self.cert.last_error)}"],
        )
