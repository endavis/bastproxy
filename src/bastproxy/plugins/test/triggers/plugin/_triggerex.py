# Project: bastproxy
# Filename: plugins/debug/apihelp/_apihelp.py
#
# File Description: a plugin to show api functions and details
#
# By: Bast
"""A plugin to test mud triggers"""
# Standard Library

# 3rd Party

# Project
from bastproxy.libs.records import NetworkData, SendDataDirectlyToClient
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult


class TriggerExPlugin(BasePlugin):
    """a plugin to test triggers"""

    @RegisterPluginHook("after_load")
    def _phook_triggerex_initialize(self) -> None:
        """Register a test trigger to capture say events."""
        result = self.api("plugins.core.triggers:trigger.add")(
            "test_say", r"^(?P<object>.*) says, \"(?P<message>.*)\"$"
        )
        if result.success:
            self.api("plugins.core.triggers:trigger.register")(
                result.trigger.trigger_id, self._trigger_say
            )

    def _trigger_say(self) -> None:
        """Handle the test trigger by echoing the parsed event."""
        if event_record := self.api("plugins.core.events:event.current.record.get")():
            print(f"_trigger_say - {event_record}")
        else:
            print("_trigger_say - No event record")

        if event_record["matches"]["message"] == "block":
            event_record["line"].send = False
        else:
            event_record["line"].line = (
                f"{event_record['matches']['object']} said something!!!!! "
                f"({event_record['matches']['message']})"
            )

    @AddParser(description="send a command and wait for a matching line (#548 demo)")
    @AddArgument("-t", "--timeout", help="seconds to wait", type=float, default=5.0)
    @AddArgument("-p", "--prompt", help="then wait for the next prompt", action="store_true")
    @AddArgument("pattern", help="regex the answer line must match from its start")
    @AddArgument("command", help="the command to send to the mud", nargs="+")
    def _command_sendwait(self) -> CommandResult:
        """@G%(name)s@w - @B%(cmdname)s@w.

        Send a command to the mud and report the line that answers it.
        @CUsage@w: sendwait @Y"pattern"@w @Y"command"@w
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        command = " ".join(args["command"])
        self.api("libs.asynch:task.add")(
            self._sendwait(command, args["pattern"], args["timeout"], args["prompt"]),
            f"{self.plugin_id}:sendwait",
        )
        return CommandResult(
            True, [f"sending {command!r} and waiting {args['timeout']}s for {args['pattern']!r}"]
        )

    async def _sendwait(
        self,
        command: str,
        pattern: str,
        timeout: float,  # noqa: ASYNC109  # per-call timeout is the helper API; asyncio.timeout is used inside
        prompt: bool,
    ) -> None:
        """Run the send-and-wait and report the outcome to the client."""
        message: list[str] = []
        with self.api("plugins.core.triggers:waiter.add")() as waiter:
            result = await waiter.send_and_wait(command, pattern, timeout)
            if result is None:
                message.append("timed out (or an error was logged)")
            else:
                message.append(f"matched: {result.text}")
                message.append(f"matches: {result.matches}")
                if prompt:
                    got = await waiter.wait_for_prompt(timeout)
                    message.append(f"prompt: {got.text!r}" if got else "prompt: timed out")
        message.append(f"open waiters: {self.api('plugins.core.triggers:waiter.count')()}")
        SendDataDirectlyToClient(NetworkData(message, owner_id=f"{self.plugin_id}:sendwait"))()
