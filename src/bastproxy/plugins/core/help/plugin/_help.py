# Project: bastproxy
# Filename: plugins/core/help/plugin/_help.py
#
# File Description: a plugin with guides for using the proxy
#
# By: Bast
"""A plugin with guides for using the proxy."""

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult

from ._topics import TOPICS, find_topic, render_topic


class HelpPlugin(BasePlugin):
    """a plugin with guides for using the proxy."""

    def _topic_list(self, prefix: str) -> list[str]:
        """Return the topic list lines, with a hint on how to show one."""
        width = max(len(topic.name) for topic in TOPICS)
        lines = [f"{topic.name:<{width}} : {topic.summary}" for topic in TOPICS]
        lines.extend(["", f"Show a topic with {prefix}.core.help.topic <name>"])
        return lines

    @AddParser(description="list help topics or show one")
    @AddArgument("name", help="the topic to show", default="", nargs="?")
    def _command_topic(self) -> CommandResult:
        """@G%(name)s@w - @B%(cmdname)s@w.

        list the help topics, or show one
        @CUsage@w: topic [@Y<name>@w]
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        prefix = self.api("plugins.core.commands:command.prefix.get")()
        header = self.api("plugins.core.commands:output.header.format")
        name = args.get("name") or ""

        if not name:
            return CommandResult(True, [*header("Help Topics"), *self._topic_list(prefix)])

        topic = find_topic(name)
        if topic is None:
            return CommandResult(
                False,
                [f"Unknown topic: {name}", "", *self._topic_list(prefix)],
            )
        return CommandResult(True, [*header(topic.name), *render_topic(topic, prefix)])
