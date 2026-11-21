# Project: bastproxy
# Filename: plugins/core/help/plugin/_topics.py
#
# File Description: the help topics and the functions that find and render them
#
# By: Bast
"""Help topics for using the proxy.

Body lines write the command prefix as the token ``{prefix}``, which
``render_topic`` replaces with the live prefix.
"""

from dataclasses import dataclass

PREFIX_PLACEHOLDER = "{prefix}"


@dataclass(frozen=True)
class Topic:
    """One help topic."""

    name: str
    summary: str
    lines: tuple[str, ...]


TOPICS: tuple[Topic, ...] = (
    Topic(
        "connecting",
        "connect a client to the proxy and the proxy to the MUD",
        (
            "Point your client at the proxy's host and port (default localhost:9999).",
            "Log in with the proxy password (default: defaultpass).",
            "The view password (default: defaultviewpass) gives a view-only session.",
            "Then tell the proxy where the MUD is and connect:",
            "  {prefix}.core.proxy.set mudhost 'host'",
            "  {prefix}.core.proxy.set mudport 'port'",
            "  {prefix}.core.proxy.connect",
            "Change both default passwords:",
            "  {prefix}.core.proxy.proxypw '...'",
            "  {prefix}.core.proxy.proxypwview '...'",
            "Also see {prefix}.core.proxy.disconnect, {prefix}.core.proxy.restart"
            " and {prefix}.core.proxy.shutdown.",
        ),
    ),
    Topic(
        "commands",
        "the command prefix and how commands are named and found",
        (
            "Commands look like: {prefix}.<package>.<plugin>.<command> [args]",
            "  example: {prefix}.core.proxy.info",
            "Type {prefix}, {prefix}.core or {prefix}.core.proxy to list the packages,"
            " plugins or commands at that level.",
            "Command names are matched fuzzily.",
            "Add -h after any command to see its arguments.",
            "Proxy output lines start with '#BP: ', and commands print Begin/End banners.",
            "Change the prefix with: {prefix}.core.commands.set cmdprefix <new>",
            "Clients that use # for their own commands (TinTin++) need it escaped: \\#bp...",
            "{prefix}.core.commands.history shows recent commands.",
        ),
    ),
    Topic(
        "settings",
        "view and change plugin settings",
        (
            "{prefix}.<plugin>.set lists a plugin's settings.",
            '{prefix}.<plugin>.set <name> <value> changes one; "" sets an empty string.',
            "{prefix}.<plugin>.set <name> --default resets a setting to its default.",
            "{prefix}.core.settings.list lists settings across plugins.",
        ),
    ),
    Topic(
        "plugins",
        "find, load and get help for plugins",
        (
            "{prefix}.core.pluginm.list lists plugins.",
            "{prefix}.core.pluginm.load <plugin>, unload <plugin> and reload <plugin> manage them.",
            "Every plugin has {prefix}.<plugin>.help:",
            "  -c lists its commands",
            "  -a lists its API",
        ),
    ),
    Topic(
        "core",
        "what each core plugin is for",
        (
            "proxy: connections to the MUD and clients, see {prefix}.core.proxy.help",
            "clients: connected clients, see {prefix}.core.clients.help",
            "commands: command parsing and the prefix, see {prefix}.core.commands.help",
            "settings: plugin settings, see {prefix}.core.settings.help",
            "pluginm: loading and unloading plugins, see {prefix}.core.pluginm.help",
            "log: log output and levels, see {prefix}.core.log.help",
            "colors: color handling, see {prefix}.core.colors.help",
            "errors: recent errors logged since startup (ERROR and above),"
            " see {prefix}.core.errors.help",
            "triggers: pattern matching on text, see {prefix}.core.triggers.help",
            "watch: watching commands and output, see {prefix}.core.watch.help",
            "timers: scheduled actions, see {prefix}.core.timers.help",
        ),
    ),
    Topic(
        "status",
        "check what the proxy is doing",
        (
            "{prefix}.core.proxy.info and {prefix}.core.proxy.details show the MUD and"
            " client connections.",
            "{prefix}.core.clients.show shows connected clients.",
            "{prefix}.core.errors.show shows the recent errors logged since startup"
            " (ERROR and above).",
            "{prefix}.core.log.client and {prefix}.core.log.console control log output"
            " to the client and the console.",
        ),
    ),
)


def find_topic(name: str) -> Topic | None:
    """Find a topic by exact name, then by a unique prefix, ignoring case."""
    key = name.strip().lower()
    if not key:
        return None
    for topic in TOPICS:
        if topic.name == key:
            return topic
    matches = [topic for topic in TOPICS if topic.name.startswith(key)]
    return matches[0] if len(matches) == 1 else None


def render_topic(topic: Topic, prefix: str) -> list[str]:
    """Return the topic's lines with the command prefix substituted."""
    return [line.replace(PREFIX_PLACEHOLDER, prefix) for line in topic.lines]
