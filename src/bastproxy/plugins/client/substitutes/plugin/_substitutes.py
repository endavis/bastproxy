# Project: bastproxy
# Filename: plugins/client/substitutes/plugin/_substitutes.py
#
# File Description: a plugin that rewrites text in MUD output before it reaches the client
#
# By: Bast
"""User substitutions: rewrite matching text of MUD lines, keeping their colour (ADR-0019)."""

# Standard Library
import logging
import re
from collections.abc import Callable
from typing import Any

# Third Party
import regex

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import log_to
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.plugins._baseplugin import BasePlugin, RegisterPluginHook
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult
from bastproxy.plugins.core.events import RegisterToEvent

NAME_RE = re.compile(r"[A-Za-z0-9_]+")
SUB_REF_RE = re.compile(r"%(%?)([1-9]|<[A-Za-z_][A-Za-z0-9_]*>)")
# a regex that backtracks catastrophically gives up after this long, in seconds (#697);
# plugins do not import plugins, so the value of the triggers plugin is repeated here
MATCH_TIMEOUT = 0.05
# runs after triggers (50) and line waiters (40), which see the original MUD text
SUBSTITUTE_PRIORITY = 60

Tokenizer = Callable[[str], list[tuple[str, str]]]
# visible text -> list of (start, end, replacement in colour-code syntax)
Finder = Callable[[str], list[tuple[int, int, str]]]


def expand_replacement(replacement: str, match: Any) -> str:
    """Substitute ``%1``-``%9`` and ``%<name>`` with the text the regex matched.

    ``%%`` before a reference makes it literal. A group that did not take part is
    empty. Matched text has ``@`` doubled, so MUD text is never read as a colour code.
    Substitution is one pass.
    """

    def _sub(ref_match: Any) -> str:
        if ref_match.group(1):
            return "%" + str(ref_match.group(2))
        ref = ref_match.group(2)
        try:
            value = match.group(ref[1:-1] if ref.startswith("<") else int(ref))
        except IndexError:
            value = None
        return "" if value is None else str(value).replace("@", "@@")

    return SUB_REF_RE.sub(_sub, replacement)


def _has_colour(text: str, tokenize: Tokenizer) -> bool:
    """Check if text holds a colour code (a token that shows nothing)."""
    return any(raw and not visible for raw, visible in tokenize(text))


def _track(state: list[str], raw: str) -> None:
    """Update the ``[foreground, background]`` colour state with one colour code."""
    if raw.startswith("@z"):
        state[1] = raw
    elif raw.startswith("@x"):
        state[0] = raw
    elif raw == "@w":
        state[0] = state[1] = ""
    elif len(raw) == 2 and raw.startswith("@"):
        state[0] = raw


def substitute_line(text: str, tokenize: Tokenizer, find: Finder) -> str | None:
    """Rewrite colour-coded text, keeping the colour of what is around the replaced text.

    ``find`` gets the visible text and returns ``(start, end, replacement)`` spans, in
    order and without overlap. Returns None when there is nothing to replace.

    Text outside a span keeps its raw form, so ``@@`` stays ``@@``. Colour codes inside a
    span move after a replacement that has none, so the colour after the span is
    unchanged. A replacement with colour codes drops them and is followed by a restore of
    the colour that was active at the end of the span.
    """
    tokens = tokenize(text)
    visible = "".join(vis for _, vis in tokens)
    limit = len(visible.rstrip("\r\n"))
    spans = [span for span in find(visible[:limit]) if span[1] > span[0]]
    if not spans:
        return None
    units: list[tuple[str, str]] = []
    for raw, vis in tokens:
        if vis and raw == vis:
            units.extend((char, char) for char in raw)
        else:
            units.append((raw, vis))
    out: list[str] = []
    state = ["", ""]
    held: list[str] = []
    pos = 0
    index = 0
    active: tuple[int, int, str] | None = None

    def _finish(span: tuple[int, int, str]) -> None:
        if _has_colour(span[2], tokenize):
            out.append("@w" + state[0] + state[1])
        else:
            out.extend(held)
        held.clear()

    for raw, vis in units:
        if active is not None and vis and pos >= active[1]:
            _finish(active)
            active = None
        if active is None and vis and index < len(spans) and pos >= spans[index][0]:
            active = spans[index]
            index += 1
            out.append(active[2])
        if not vis:
            _track(state, raw)
            if active is not None:
                held.append(raw)
            else:
                out.append(raw)
            continue
        if active is None:
            out.append(raw)
        pos += len(vis)
    if active is not None:
        _finish(active)
    return "".join(out)


class SubstitutesPlugin(BasePlugin):
    """a plugin that rewrites text in MUD output before it reaches the client."""

    @RegisterPluginHook("__init__")
    def _phook_init_plugin(self) -> None:
        """Initialize the instance."""
        self.substitutes = PersistentDict(
            self.plugin_id, self.plugin_info.data_directory / "substitutes.txt", "c"
        )
        self._compiled: dict[str, Any] = {}
        self._timeout_warned: set[str] = set()

    @RegisterPluginHook("save")
    def _phook_substitutes_save(self) -> None:
        """Save the substitutions."""
        self.substitutes.sync()

    def _regex_for(self, name: str) -> Any:
        """Return the compiled regex of a regex substitution, compiling it once."""
        item = self.substitutes[name]
        cached = self._compiled.get(name)
        if cached is None or cached[0] != item["pattern"]:
            cached = (item["pattern"], regex.compile(item["pattern"]))
            self._compiled[name] = cached
        return cached[1]

    def _refs_fit(self, replacement: str, compiled: Any) -> bool:
        """Check that every reference in the replacement exists in the regex."""
        for match in SUB_REF_RE.finditer(replacement):
            if match.group(1):
                continue
            ref = match.group(2)
            if ref.startswith("<"):
                if ref[1:-1] not in compiled.groupindex:
                    return False
            elif int(ref) > compiled.groups:
                return False
        return True

    @AddAPI("substitute.add", description="add a substitution or replace an existing one")
    def _api_substitute_add(
        self, name: str, pattern: str, replacement: str, regex_mode: bool = False
    ) -> bool:
        """Add a substitution or replace an existing one.

        @Yname@w          = the substitution name, letters, digits and underscores
        @Ypattern@w       = the text, or the regex, to find in MUD output
        @Yreplacement@w   = the text to show instead, may be empty
        @Yregex_mode@w    = True to read the pattern as a regex

        This function returns True when the substitution was stored. It returns False,
        changing nothing, for a bad name, pattern or replacement.
        """
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            log_to([self.plugin_id], logging.WARNING, "_api_substitute_add: bad name")
            return False
        for value in (pattern, replacement):
            if not isinstance(value, str) or "\r" in value or "\n" in value:
                log_to(
                    [self.plugin_id], logging.WARNING, "_api_substitute_add: bad text for %s", name
                )
                return False
        if not pattern:
            log_to([self.plugin_id], logging.WARNING, "_api_substitute_add: empty pattern")
            return False
        if regex_mode:
            try:
                compiled = regex.compile(pattern)
            except regex.error:
                log_to(
                    [self.plugin_id], logging.WARNING, "_api_substitute_add: bad regex for %s", name
                )
                return False
            if not self._refs_fit(replacement, compiled):
                log_to(
                    [self.plugin_id],
                    logging.WARNING,
                    "_api_substitute_add: replacement for %s references a group the regex lacks",
                    name,
                )
                return False
        self.substitutes[name] = {
            "pattern": pattern,
            "replacement": replacement,
            "regex": bool(regex_mode),
        }
        self._compiled.pop(name, None)
        self._timeout_warned.discard(name)
        self.substitutes.sync()
        return True

    @AddAPI("substitute.remove", description="remove a substitution")
    def _api_substitute_remove(self, name: str) -> bool:
        """Remove a substitution.

        @Yname@w   = the substitution name

        This function returns True when removed, False when it was not defined.
        """
        if name not in self.substitutes:
            return False
        del self.substitutes[name]
        self._compiled.pop(name, None)
        self._timeout_warned.discard(name)
        self.substitutes.sync()
        return True

    @AddAPI("substitute.get", description="get a substitution")
    def _api_substitute_get(self, name: str) -> dict[str, Any] | None:
        """Get a copy of a substitution.

        @Yname@w   = the substitution name

        This function returns a dict with pattern, replacement and regex, or None.
        """
        item = self.substitutes.get(name)
        return dict(item) if item is not None else None

    @AddAPI("substitute.exists", description="check if a substitution is defined")
    def _api_substitute_exists(self, name: str) -> bool:
        """Check if a substitution is defined.

        @Yname@w   = the substitution name
        """
        return name in self.substitutes

    @AddAPI("substitute.list", description="get all substitutions")
    def _api_substitute_list(self) -> dict[str, dict[str, Any]]:
        """Get a copy of all substitutions as a name to substitution dict."""
        return {name: dict(item) for name, item in self.substitutes.items()}

    @AddAPI("substitute.clear", description="remove every substitution")
    def _api_substitute_clear(self) -> int:
        """Remove every substitution.

        This function returns how many were removed.
        """
        count = len(self.substitutes)
        self.substitutes.clear()
        self._compiled.clear()
        self._timeout_warned.clear()
        self.substitutes.sync()
        return count

    def _finder(self, name: str) -> Finder:
        """Return the function that finds the spans of one substitution in visible text."""
        item = self.substitutes[name]
        pattern = item["pattern"]
        replacement = item["replacement"]
        if not item.get("regex"):

            def _plain(text: str) -> list[tuple[int, int, str]]:
                spans = []
                start = text.find(pattern)
                while start != -1:
                    spans.append((start, start + len(pattern), replacement))
                    start = text.find(pattern, start + len(pattern))
                return spans

            return _plain

        def _regex(text: str) -> list[tuple[int, int, str]]:
            compiled = self._regex_for(name)
            try:
                matches = list(compiled.finditer(text, timeout=MATCH_TIMEOUT))
            except TimeoutError:
                if name not in self._timeout_warned:
                    self._timeout_warned.add(name)
                    log_to(
                        [self.plugin_id],
                        logging.WARNING,
                        "substitution %s: match timed out, line left as it was",
                        name,
                    )
                return []
            return [
                (m.start(), m.end(), expand_replacement(replacement, m))
                for m in matches
                if m.end() > m.start()
            ]

        return _regex

    @RegisterToEvent(event_name="ev_to_client_data_modify", priority=SUBSTITUTE_PRIORITY)
    def _eventcb_substitute_line(self) -> None:
        """Rewrite the text of a MUD line that matches a substitution."""
        if not self.substitutes:
            return
        if not (event_record := self.api("plugins.core.events:event.current.record.get")()):
            return
        line = event_record["line"]
        if (
            line.internal
            or not line.is_io
            or not isinstance(line.line, str)
            or not line.send
            or line.mxp_mode is not None
        ):
            return
        colorcoded = line.colorcoded
        if not isinstance(colorcoded, str):
            return
        tokenize = self.api("plugins.core.colors:colorcode.to.tokens")
        text = colorcoded
        changed = False
        for name in sorted(self.substitutes):
            new_text = substitute_line(text, tokenize, self._finder(name))
            if new_text is not None:
                text = new_text
                changed = True
        if changed:
            line.line = self.api("plugins.core.colors:colorcode.to.ansicode")(text)

    @AddParser(description="add a substitution or change it")
    @AddArgument("-r", "--regex", help="read the pattern as a regex", action="store_true")
    @AddArgument(
        "-o",
        "--overwrite",
        help="replace the substitution when the name exists",
        action="store_true",
    )
    @AddArgument("name", help="the substitution name")
    @AddArgument("pattern", help="the text to find in MUD output, quote it")
    @AddArgument("replacement", help="the text to show instead, '' to delete the match", nargs="+")
    def _command_add(self) -> CommandResult:
        """Add a substitution or change it."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = args["name"]
        if name in self.substitutes and not args.get("overwrite", False):
            return CommandResult(False, [f"substitution {name} exists, use -o to replace it"])
        pattern = args["pattern"]
        replacement = " ".join(args["replacement"])
        # a typed line is split on the command separator before this command runs,
        # so a doubled separator is how a user types one; store it single
        separator = self.api.command_separator
        if separator:
            pattern = pattern.replace(separator * 2, separator)
            replacement = replacement.replace(separator * 2, separator)
        if self.api(f"{self.plugin_id}:substitute.add")(name, pattern, replacement, args["regex"]):
            return CommandResult(True, [f"substitution {name} set"])
        return CommandResult(
            False,
            [
                f"could not set {name}: the name needs letters, digits and underscores, the "
                "pattern cannot be empty, a regex must compile, the replacement can only "
                "reference groups the regex has, and neither can contain a line break"
            ],
        )

    @AddParser(description="remove a substitution")
    @AddArgument("name", help="the substitution name")
    def _command_remove(self) -> CommandResult:
        """Remove a substitution."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        name = args["name"]
        if self.api(f"{self.plugin_id}:substitute.remove")(name):
            return CommandResult(True, [f"substitution {name} removed"])
        return CommandResult(False, [f"substitution {name} does not exist"])

    @AddParser(description="list substitutions")
    @AddArgument(
        "match",
        help="list only substitutions that have this argument in their name",
        default="",
        nargs="?",
    )
    def _command_list(self) -> CommandResult:
        """List substitutions."""
        args = self.api("plugins.core.commands:command.current.args.get")()
        match = args["match"]
        names = sorted(name for name in self.substitutes if not match or match in name)
        if not names:
            return CommandResult(True, ["No substitutions defined"])
        escape = self.api("plugins.core.colors:colorcode.escape")
        lines = []
        for name in names:
            item = self.substitutes[name]
            suffix = " (regex)" if item.get("regex") else ""
            lines.append(
                f"{escape(name)} : {escape(item['pattern'])} -> "
                f"{escape(item['replacement'])}{suffix}"
            )
        return CommandResult(True, lines)

    @AddParser(description="remove every substitution")
    def _command_clear(self) -> CommandResult:
        """Remove every substitution."""
        count = self.api(f"{self.plugin_id}:substitute.clear")()
        return CommandResult(True, [f"{count} substitutions removed"])
