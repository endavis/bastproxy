"""Error pages, plugin lists, command list groups and the pass-through path (#401)."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands import CommandResult
from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin

PID = "plugins.core.commands"


def _stub(handlers: dict[str, Callable[..., Any]] | None = None) -> MagicMock:
    """Build a plugin stub whose api returns `handlers[name]` or a no-op returning []."""
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.settings:setting.get": lambda _pid, _key: "@w",
        f"{PID}:output.header.format": lambda title: [f"HEADER {title}"],
        "plugins.core.utils:line.cap": lambda *_a, **_k: "CAP",
        "plugins.core.utils:string.center.colored": lambda text, **_k: text,
        "libs.plugins.loader:plugin.list.in.package": lambda _pkg: ["plugins.core.alpha"],
        "libs.plugins.loader:package.list": lambda active_only: ["plugins.core"],
    }
    table.update(handlers or {})
    stub = MagicMock()
    stub.plugin_id = PID

    def api(name: str) -> Callable[..., Any]:
        return table.get(name, lambda *_a, **_k: [])

    stub.api = api
    stub.proxy_help = lambda *a: CommandsPlugin.proxy_help(stub, *a)
    return stub


def test_proxy_help_wraps_data() -> None:
    """proxy_help adds the intro, the optional second header and the data."""
    stub = _stub()

    out = CommandsPlugin.proxy_help(stub, "Title", "Second", ["row"])

    assert out[1] == "HEADER Title"
    assert "@BSecond" in out
    assert "row" in out
    assert out[-1] == ""


def test_proxy_help_without_second_header() -> None:
    """No second header means no separator line."""
    out = CommandsPlugin.proxy_help(_stub(), "Title", "", ["row"])

    assert not any(line.startswith("@B") for line in out)


def test_only_prefix_lists_packages() -> None:
    """The prefix-only page lists the active packages without the `plugins.` part."""
    out = CommandsPlugin.find_command_only_prefix(_stub())

    assert "core" in out
    assert "plugins.core" not in out


def test_error_command_not_found_names_plugin_and_command() -> None:
    """The error names the plugin and the command and lists the plugin's commands."""
    stub = _stub({f"{PID}:command.list.formatted": lambda pid: [f"cmds of {pid}"]})

    out = "\n".join(
        CommandsPlugin.error_command_not_found_in_plugin(stub, "plugins.core.alpha", "zzz")
    )

    assert "Plugin core.alpha has no command : zzz" in out
    assert "cmds of core.alpha" in out


def test_error_command_not_found_without_command_has_no_error_line() -> None:
    """With no command name only the command list is shown."""
    stub = _stub({f"{PID}:command.list.formatted": lambda pid: ["cmds"]})

    out = "\n".join(CommandsPlugin.error_command_not_found_in_plugin(stub, "plugins.core.alpha"))

    assert "has no command" not in out
    assert "cmds" in out


def test_error_plugin_not_found_lists_plugins_of_package() -> None:
    """The error names the unknown plugin and lists the package's plugins."""
    stub = _stub({"plugins.core.utils:column.format": lambda plugins, **_k: plugins})

    out = "\n".join(CommandsPlugin.error_plugin_not_found(stub, "zzz", "plugins.core"))

    assert "Unknown plugin : zzz" in out
    assert "Available Plugins in plugins.core" in out
    assert "core.alpha" in out


def test_error_plugin_not_found_without_plugin_id() -> None:
    """Without a plugin id there is no error line, only the list."""
    stub = _stub({"plugins.core.utils:column.format": lambda plugins, **_k: plugins})

    out = "\n".join(CommandsPlugin.error_plugin_not_found(stub, None, "plugins.core"))

    assert "Unknown plugin" not in out
    assert "core.alpha" in out


def test_error_package_not_found_lists_packages() -> None:
    """The error names the unknown package and lists the active packages."""
    out = "\n".join(CommandsPlugin.error_package_not_found(_stub(), "zzz"))

    assert "Unknown package : zzz" in out
    assert "Available Packages" in out


def _command(name: str, group: str) -> Any:
    return SimpleNamespace(
        name=name, group=group, arg_parser=SimpleNamespace(description=f"{name} description")
    )


def _list_stub(command_data: dict[str, Any]) -> MagicMock:
    stub = _stub({"libs.plugins.loader:plugin.id.is.valid": lambda _pid: True})
    stub.command_data = command_data
    stub.format_command_list = lambda cl: CommandsPlugin.format_command_list(stub, cl)
    return stub


def test_command_list_sections_own_group_other_group_then_base() -> None:
    """The plugin's own group comes first, other groups next and Base last."""
    target = "plugins.core.alpha"
    stub = _list_stub(
        {
            target: {
                "own": _command("own", target),
                "other": _command("other", "plugins.core.beta"),
                "base": _command("base", "Base"),
                "default": _command("default", "Base"),
            }
        }
    )

    text = "\n".join(CommandsPlugin._api_command_list_formatted(stub, target))

    assert text.index("own description") < text.index("other description")
    assert text.index("other description") < text.index("base description")
    assert "----- core.beta -----" in text
    assert "default description" not in text


def test_command_list_for_invalid_plugin_is_empty() -> None:
    """An unknown plugin gives an empty list."""
    stub = _stub({"libs.plugins.loader:plugin.id.is.valid": lambda _pid: False})

    assert CommandsPlugin._api_command_list_formatted(stub, "plugins.nope") == []


def test_format_command_list_skips_empty_description_and_leading_blank() -> None:
    """A command with no description is skipped; a leading blank line is dropped."""
    blank: Any = SimpleNamespace(
        name="plugins.x.blank", arg_parser=SimpleNamespace(description="\nreal text")
    )
    none: Any = SimpleNamespace(name="plugins.x.none", arg_parser=SimpleNamespace(description=""))

    out = CommandsPlugin.format_command_list(_stub(), [blank, none])

    assert len(out) == 1
    assert "real text" in out[0]


def test_plugin_list_in_package() -> None:
    """With a package the plugins of that package are listed, sorted and stripped."""
    stub = _stub(
        {
            "libs.plugins.loader:plugin.list.in.package": lambda _p: ["plugins.b", "plugins.a"],
            "plugins.core.utils:column.format": lambda items, **_k: items,
        }
    )

    assert CommandsPlugin._api_plugin_list_formatted(stub, "plugins.core") == ["a", "b"]


def test_plugin_list_loaded_when_no_package() -> None:
    """Without a package the loaded plugins are listed."""
    stub = _stub(
        {
            "libs.plugins.loader:plugin.list.loaded": lambda: ["plugins.z"],
            "plugins.core.utils:column.format": lambda items, **_k: items,
        }
    )

    assert CommandsPlugin._api_plugin_list_formatted(stub) == ["z"]


def test_plugin_list_empty() -> None:
    """No plugins gives a single explanatory line."""
    stub = _stub({"libs.plugins.loader:plugin.list.loaded": lambda: []})

    assert CommandsPlugin._api_plugin_list_formatted(stub) == ["No plugins found"]


def _command_list_stub(
    args: dict[str, str], valid: bool, command_data: dict[str, Any]
) -> MagicMock:
    stub = _stub(
        {
            f"{PID}:command.current.args.get": lambda: args,
            "libs.plugins.loader:plugin.id.is.valid": lambda _pid: valid,
            f"{PID}:plugin.list.formatted": lambda package: [f"plugins in {package}"],
            f"{PID}:command.list.formatted": lambda pid: [f"commands of {pid}"],
        }
    )
    stub.command_data = command_data
    return stub


def test_command_list_invalid_plugin_lists_plugins() -> None:
    """`list` with a name that is not a plugin lists plugins of that package."""
    stub = _command_list_stub({"plugin": "core", "command": ""}, False, {})

    assert CommandsPlugin._command_list(stub) == CommandResult(True, ["plugins in core"])


def test_command_list_plugin_without_commands() -> None:
    """A plugin with no commands says so."""
    stub = _command_list_stub({"plugin": "plugins.x", "command": ""}, True, {})

    result = CommandsPlugin._command_list(stub)
    ok = result.success
    message = result.message

    assert ok is True
    assert message == ["There are no commands in plugin plugins.x"]


def test_command_list_plugin_commands() -> None:
    """A plugin with commands lists them."""
    data = {"plugins.x": {"run": SimpleNamespace()}}
    stub = _command_list_stub({"plugin": "plugins.x", "command": ""}, True, data)

    assert CommandsPlugin._command_list(stub) == CommandResult(True, ["commands of plugins.x"])


def test_command_list_single_command_shows_its_help() -> None:
    """Naming a command shows that command's parser help."""
    parser = MagicMock()
    parser.format_help.return_value = "usage: run\nmore"
    data = {"plugins.x": {"run": SimpleNamespace(arg_parser=parser)}}
    stub = _command_list_stub({"plugin": "plugins.x", "command": "run"}, True, data)

    assert CommandsPlugin._command_list(stub) == CommandResult(True, ["usage: run", "more"])


def _pass_through(line: str, settings: dict[str, Any]) -> MagicMock:
    record = {"line": SimpleNamespace(line=line)}
    stub = _stub(
        {
            "plugins.core.events:event.current.record.get": lambda: record,
            "plugins.core.settings:setting.get": lambda _pid, key: settings[key],
            "plugins.core.settings:setting.set": lambda _pid, key, value: settings.update(
                {key: value}
            ),
        }
    )
    stub.no_multiple_commands = {}
    CommandsPlugin.pass_through_command_from_event(stub)
    return stub


def test_pass_through_new_line_resets_count_and_stores_last() -> None:
    """A line that differs from the last one resets the count and is remembered."""
    settings: dict[str, Any] = {"lastcmd": "look", "cmdcount": 3, "spamcount": 20}

    _pass_through("north", settings)

    assert settings["cmdcount"] == 0
    assert settings["lastcmd"] == "north"


def test_pass_through_repeated_line_counts_up() -> None:
    """The same line again raises the count while below the spam count."""
    settings: dict[str, Any] = {"lastcmd": "look", "cmdcount": 1, "spamcount": 20}

    _pass_through("look", settings)

    assert settings["cmdcount"] == 2
    assert settings["lastcmd"] == "look"


def test_pass_through_without_record_does_nothing() -> None:
    """With no current event record nothing is touched."""
    stub = _stub({"plugins.core.events:event.current.record.get": lambda: None})

    CommandsPlugin.pass_through_command_from_event(stub)
