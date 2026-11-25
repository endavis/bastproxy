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

from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.validators import int_range

# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddCommand, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent
from bastproxy.plugins.core.web.libs._render import render_page
from bastproxy.plugins.core.web.libs._server import WebApp, WebServer
from bastproxy.plugins.core.web.libs._store import LoginTokens, PageStore, RouteTable, SessionStore
from bastproxy.plugins.core.web.libs._tls import (
    CertManager,
    cert_details,
    is_loopback,
    validate_bind_address,
)


class WebPlugin(BasePlugin):
    """a plugin that serves web pages for plugins."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.pages = PageStore()
        self.routes = RouteTable()
        self.logins = LoginTokens()
        self.sessions = SessionStore()
        self.server = WebServer()
        self.cert: CertManager | None = None
        self._generation = 0
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
            "the address to listen on; anything but a loopback address needs a certificate",
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

    @RegisterPluginHook("after_load", priority=80)
    def _phook_start(self) -> None:
        """Start the server once the settings are initialised."""
        self._schedule_restart()

    @RegisterPluginHook("uninitialize", priority=10)
    def _phook_close_server(self) -> None:
        """Stop the listener before the base hook raises the unloaded events."""
        self._generation += 1
        self.server.close()
        self.api("libs.asynch:task.add")(self.server.wait_closed(), f"{self.plugin_id}:close")

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
        """Queue a restart; the queued task gets a fresh context, not this caller's."""
        self.api("libs.asynch:task.add")(
            self._restart(self._generation), f"{self.plugin_id}:restart"
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
        )

    def _secure_cookie(self) -> bool:
        """The session cookie is Secure with TLS, or when the public url is https."""
        return self.server.tls or str(self._setting("publicurl")).startswith("https://")

    def _path(self, name: str) -> Path:
        """A path setting, relative to the data directory unless absolute."""
        return Path(self.api.BASEDATAPATH) / str(self._setting(name))

    async def _restart(self, generation: int) -> None:
        """Close the listener and start it again from the settings."""
        async with self._lock:
            self.server.close()
            self.cert = None
            await self.server.wait_closed()
            if generation != self._generation or not self._setting("enabled"):
                return
            host = str(self._setting("bindaddress"))
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
            if not has_cert and not is_loopback(host):
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "web server not started: bindaddress %s is not a loopback address, "
                    "so certfile and keyfile must be set (plain http is only allowed on loopback)",
                    host,
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
                await self.server.start(host, port, self._build_app(), cert)
            except OSError as exc:
                log_to(
                    [self.plugin_id],
                    logging.ERROR,
                    "web server not started: cannot listen on %s port %s: %s",
                    host,
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
        host = str(self._setting("bindaddress"))
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
        self, owner: str, subpath: str, handler: Callable[..., Any], title: str
    ) -> str | None:
        """Serve a page at ``/<plugin path>/<subpath>`` for a logged in browser.

        @Yowner@w     = the plugin id; it must be the calling plugin
        @Ysubpath@w   = lower case letters, digits, _ and -, separated by /; "" for the prefix
        @Yhandler@w   = a sync or async function taking a Request, returning a dict
        @Ytitle@w     = the title shown in the index

        The path comes from the plugin id: plugins.aardwolf.mapper is served at
        /aardwolf/mapper/<subpath>. Returns the path, or None (and logs an error) when the
        route is refused.
        """
        caller = self.api("libs.api:caller.owner.get")(ignore_owner_list=[self.plugin_id])
        error = ""
        if owner != caller:
            error = f"{owner} is not the calling plugin ({caller})"
        elif not self.api("libs.plugins.loader:plugin.id.is.valid")(owner):
            error = f"{owner} is not a plugin id"
        else:
            try:
                return self.routes.add(owner, subpath, handler, title)
            except ValueError as exc:
                error = str(exc)
        log_to(
            [self.plugin_id, owner],
            logging.ERROR,
            "web route %r refused for %s: %s",
            subpath,
            owner,
            error,
        )
        return None

    @AddAPI("web.route.remove", description="remove the routes of a plugin")
    def _api_web_route_remove(self, owner: str) -> int:
        """Remove every route of a plugin and return how many there were.

        @Yowner@w   = the plugin id
        """
        return self.routes.remove(owner)

    @RegisterToEvent(event_name="ev_plugin_unloaded")
    def _eventcb_plugin_unloaded(self) -> None:
        """A plugin was unloaded: drop its routes."""
        event_record = self.api("plugins.core.events:event.current.record.get")()
        removed = self.routes.remove(event_record["plugin_id"])
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
        if not self._setting("enabled"):
            return CommandResult(True, ["the web server is not enabled (set enabled true)"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        token = self.logins.issue()
        log_to([self.plugin_id], logging.DEBUG, "login token %s issued", token[:6])
        return CommandResult(True, [f"Login link: {escape(f'{self._base_url()}/login/{token}')}"])

    @AddParser(description="end every web session")
    def _command_logout(self) -> CommandResult:
        """End all sessions."""
        count = self.sessions.clear()
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
        routes = ", ".join(f"{owner} ({len(items)})" for owner, items in by_owner.items())
        message.append(
            f"{'Routes':<14}: {self.routes.count()}" + (f" - {escape(routes)}" if routes else "")
        )
        message.append(f"{'Sessions':<14}: {self.sessions.count()}")
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
