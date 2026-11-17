# Project: bastproxy
# Filename: plugins/core/colors/_colors.py
#
# File Description: a plugin to handle ansi and xterm colors
#
# By: Bast

# Standard Library
from bastproxy.libs.api import AddAPI
from bastproxy.libs.logger import get_logger
from bastproxy.plugins._baseplugin import BasePlugin

# 3rd Party
# Project
from bastproxy.plugins.core.colors.libs._colors import (
    COLORTABLE,
    CONVERTANSI,
    CONVERTCOLORS,
)
from bastproxy.plugins.core.colors.libs._tokenizer import (
    Token,
    TokenKind,
    strip_ansi,
    strip_colorcodes,
    tokenize,
)
from bastproxy.plugins.core.commands import AddArgument, AddParser, CommandResult

logger = get_logger(__name__)

_CODE_KINDS = (TokenKind.COLOR, TokenKind.XTERM_FG, TokenKind.XTERM_BG)
_VISIBLE_KINDS = (TokenKind.TEXT, TokenKind.ESCAPE)
# @w is the general reset: it clears the background as well as setting white
RESET_CODE = "w"


def convertcolorcodetohtml(colorcode: str | int) -> str:
    """Convert a color letter or xterm number to an html color."""
    key: str | int = colorcode
    if isinstance(colorcode, str) and colorcode.isdigit():
        key = int(colorcode)
    if key in COLORTABLE:
        red, green, blue = COLORTABLE[key]
        return f"#{red:02x}{green:02x}{blue:02x}"
    return "#000"


def createspan(foreground: str | None, background: str | None, text: str) -> str:
    """Create an html span for ``text``; plain text when there is no color.

    ``foreground`` and ``background`` are html colors such as ``#cd0000``.
    """
    styles = []
    if foreground:
        styles.append(f"color:{foreground}")
    if background:
        styles.append(f"background-color:{background}")
    if not styles:
        return text
    return f"<span style='{';'.join(styles)}'>{text}</span>"


def _html_line(tokens: list[Token]) -> str:
    """Build the html for the tokens of one line; colors reset at the start of each line."""
    foreground: str | None = None
    background: str | None = None
    out: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            out.append(createspan(foreground, background, "".join(buffer)))
            buffer.clear()

    for token in tokens:
        if token.kind in _VISIBLE_KINDS:
            buffer.append(token.visible)
        elif token.kind is TokenKind.COLOR:
            flush()
            foreground = None if token.value in ("w", "D") else convertcolorcodetohtml(token.value)
            if token.value == RESET_CODE:
                background = None
        elif token.kind is TokenKind.XTERM_FG:
            flush()
            foreground = convertcolorcodetohtml(token.value)
        elif token.kind is TokenKind.XTERM_BG:
            flush()
            background = convertcolorcodetohtml(token.value)
        elif token.kind is TokenKind.SGR:
            buffer.append(token.raw)
    flush()
    return "".join(out)


def _to_ansicode(tokens: list[Token]) -> str:
    """Convert the tokens to ansi, tracking the active background."""
    last_visible = -1
    for index, token in enumerate(tokens):
        if token.kind in _VISIBLE_KINDS or token.kind is TokenKind.SGR:
            last_visible = index
    out: list[str] = []
    background = ""
    emitted = False
    for index, token in enumerate(tokens):
        kind = token.kind
        if kind in _VISIBLE_KINDS:
            out.append(token.visible)
        elif kind is TokenKind.SGR:
            out.append(token.raw)
        elif kind in _CODE_KINDS and index < last_visible:
            if kind is TokenKind.XTERM_FG:
                params = f"38;5;{token.value}"
            elif kind is TokenKind.XTERM_BG:
                params = f"48;5;{token.value}"
                background = token.value
            else:
                params = CONVERTCOLORS[token.value]
                if token.value == RESET_CODE:
                    background = ""
                elif background and token.value.islower():
                    params = f"{params};48;5;{background}"
            out.append(f"\x1b[{params}m")
            emitted = True
    if emitted:
        out.append("\x1b[0m")
    return "".join(out)


class ColorsPlugin(BasePlugin):
    """a plugin to handle ansi colors."""

    @AddAPI(
        "colorcode.to.tokens",
        description="split a string into (raw, visible) pairs, one per colorcode token",
    )
    def _api_colorcode_to_tokens(self, text: str) -> list[tuple[str, str]]:
        # pylint: disable=no-self-use
        """Split text into ``(raw, visible)`` pairs.

        ``visible`` is empty for color codes and ansi sequences, the text itself for plain text
        and the single shown character for an escape such as ``@@``.
        """
        return [(token.raw, token.visible) for token in tokenize(text)]

    @AddAPI("colorcode.to.html", description="convert colorcodes to html")
    def _api_colorcode_to_html(self, sinput: str) -> str:
        # pylint: disable=no-self-use
        """Convert colorcodes to html."""
        return "\n".join(_html_line(tokenize(line.rstrip())) for line in sinput.splitlines())

    @AddAPI(
        "color.length.difference.get",
        description="get the length difference of a colored string and its noncolor equivalent",
    )
    def _api_color_length_difference_get(self, colorstring: str) -> int:
        # pylint: disable=no-self-use
        """Get the length difference of a colored string and its noncolor equivalent."""
        return len(colorstring) - len(strip_colorcodes(colorstring))

    # check if a string is an @@ color, either xterm or ansi
    @AddAPI(
        "colorcode.is.valid",
        description="check if a string is a @@ color, either xterm or ansi",
    )
    def _api_colorcode_is_valid(self, color: str) -> bool:
        # pylint: disable=no-self-use
        """Check if a string is a @ color, either xterm or ansi."""
        tokens = tokenize(color)
        return len(tokens) == 1 and tokens[0].kind in _CODE_KINDS

    @AddAPI("colorcode.to.ansicode", description="convert @@ colors in a string")
    def _api_colorcode_to_ansicode(self, tstr: str) -> str:
        # pylint: disable=no-self-use
        """Convert @ colors in a string."""
        if "@" not in tstr:
            return tstr
        return _to_ansicode(tokenize(tstr))

    @AddAPI("colorcode.escape", description="escape colorcodes so they are not interpreted")
    def _api_colorcode_escape(self, tstr: str) -> str:
        """Escape colorcodes."""
        tinput = tstr.splitlines()

        olist = []
        for line in tinput:
            escaped_line = line.replace("@@", "\0")
            escaped_line = escaped_line.replace("@", "@@")
            escaped_line = escaped_line.replace("\0", "@@@@")

            olist.append(escaped_line)

        return "\n".join(olist)

    @AddAPI(
        "ansicode.to.colorcode",
        description="convert ansi color escape sequences to @@ colors",
    )
    def _api_ansicode_to_colorcode(self, text: str) -> str:
        # pylint: disable=no-self-use
        """Convert ansi color escape sequences to @@ colors."""
        if "\x1b" not in text:
            return text
        out: list[str] = []
        for token in tokenize(text):
            if token.kind is not TokenKind.SGR:
                out.append(token.raw)
                continue
            parts = token.value.split(";")
            if len(parts) > 3 or not all(part.isdecimal() for part in parts):
                logger.debug("no colorcode for ansi sequence %r in text %r", token.raw, text)
                continue
            key = ";".join([parts[0], *(str(int(part)) for part in parts[1:])])
            try:
                out.append(f"@{CONVERTANSI[key]}")
            except KeyError:
                # SGR codes with no colorcode (22, 1, 4, 39, 49, ...) are dropped quietly
                logger.debug("no colorcode for ansi code %s in text %r", key, text)
        return "".join(out)

    @AddAPI("ansicode.to.string", description="return an ansi coded string")
    def _api_ansicode_to_string(self, color: str, data: str) -> str:
        # pylint: disable=no-self-use
        """Return an ansi coded string."""
        return f"{chr(27)}[{color}m{data}"

    @AddAPI("ansicode.strip", description="strip all ansi from a string")
    def _api_ansicode_strip(self, text: str) -> str:
        # pylint: disable=no-self-use
        """Strip all ansi from a string."""
        return strip_ansi(text)

    @AddAPI("colorcode.strip", description="strip @@ colors")
    def _api_colorcode_strip(self, text: str) -> str:
        # pylint: disable=no-self-use
        """Strip @@ colors."""
        return strip_colorcodes(text)

    @AddParser(description="show colors")
    @AddArgument("-c", "--compact", help="show a compact table", action="store_true")
    def _command_show(self) -> CommandResult:
        """@G%(name)s@w - @B%(cmdname)s@w.

        Show xterm colors
        @CUsage@w: show @Y"compact"@w
          @Y"compact"@w    = The original string to be replaced.
        """
        args = self.api("plugins.core.commands:command.current.args.get")()
        message = [""]
        row_message: list[str] = []
        compact = False
        joinc = " "
        if args["compact"]:
            compact = True
            colors = "@z%s  @w"
            joinc = ""
        else:
            colors = "@B%-3s : @z%s    @w"
        for i in range(16):
            if i % 8 == 0 and i != 0:
                message.append(joinc.join(row_message))
                row_message = []

            if compact:
                row_message.append(colors % (i))
            else:
                row_message.append(colors % (i, i))

        row_message.append("\n")
        message.append(joinc.join(row_message))

        row_message = []

        for i in range(16, 256):
            if (i - 16) % 36 == 0 and i != 16 and i <= 233:
                row_message.append("\n")

            if (i - 16) % 6 == 0 and i != 16:
                message.append(joinc.join(row_message))
                row_message = []

            if compact:
                row_message.append(colors % (i))
            else:
                row_message.append(colors % (i, i))

        message.append(joinc.join(row_message))
        row_message = []

        message.append("")

        return CommandResult(True, message)

    @AddParser(description="show color examples")
    def _command_example(self) -> CommandResult:
        # pylint: disable=no-self-use
        """@G%(name)s@w - @B%(cmdname)s@w.

        Show examples of how to use colors
        @CUsage@w: example.
        """
        message = [
            "",
            "Examples",
            "Raw   : @@z165Regular text with color 165 Background@@w",
            "Color : @z165Regular text with color 165 Background@w",
            "Raw   : @@x165@zcolor 165 text with regular Background@@w",
            "Color : @x165color 165 text with regular Background@w",
            "Raw   : @@z255@@x0color 0 text with color 255 Background@@w",
            "Color : @z255@x0color 0 text with color 255 Background@w",
            "Note: see the show command to show the table of colors",
            "",
        ]
        return CommandResult(True, message)
