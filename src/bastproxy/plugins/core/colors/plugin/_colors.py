# Project: bastproxy
# Filename: plugins/core/colors/_colors.py
#
# File Description: a plugin to handle ansi and xterm colors
#
# By: Bast

# Standard Library
import re

from bastproxy.libs.api import AddAPI
from bastproxy.libs.records import LogRecord
from bastproxy.plugins._baseplugin import BasePlugin

# 3rd Party
# Project
from bastproxy.plugins.core.colors.libs._colors import (
    COLORTABLE,
    CONVERTANSI,
    CONVERTCOLORS,
)
from bastproxy.plugins.core.commands import AddArgument, AddParser

XTERM_COLOR_REGEX = re.compile(r"^@[xz](?P<num>[\d]{1,3})$")
ANSI_COLOR_REGEX = re.compile(
    chr(27) + r"\[(?P<arg_1>\d+)(;(?P<arg_2>\d+)" r"(;(?P<arg_3>\d+))?)?m"
)

COLORCODE_REGEX = re.compile(r"(@[cmyrgbwCMYRGBWD|xz[\d{0:3}]])(?P<stuff>.*)")


def convertcolorcodetohtml(colorcode):
    """Convert a colorcode to an html color."""
    try:
        colorcode = int(colorcode)
        if colorcode in COLORTABLE:
            return f"#{COLORTABLE[colorcode][0]:02x}{COLORTABLE[colorcode][1]:02x}{COLORTABLE[colorcode][2]:02x}"
    except ValueError:
        if colorcode in COLORTABLE:
            return f"#{COLORTABLE[colorcode][0]:02x}{COLORTABLE[colorcode][1]:02x}{COLORTABLE[colorcode][2]:02x}"

    return "#000"


def createspan(color, text):
    """Create an html span.

    color = "@g"
    """
    background = False
    if color[0] == "@":
        if color[1] == "x":
            ncolor = convertcolorcodetohtml(color[2:])
        elif color[1] == "z":
            ncolor = convertcolorcodetohtml(color[2:])
            background = True
        else:
            ncolor = convertcolorcodetohtml(color[1])
    else:
        ncolor = convertcolorcodetohtml(color)

    if background:
        return f"<span style='background-color:{ncolor}'>{text}</span>"

    return f"<span style='color:{ncolor}'>{text}</span>"


def genrepl(match):
    """A general replace function."""
    return match.group(1)


def fixstring(tstr):
    """Fix a strings invalid colors."""
    # Thanks to Fiendish from the aardwolf mushclient package, see
    # http://code.google.com/p/aardwolfclientpackage/

    # fix tildes
    tstr = re.sub(r"@-", "~", tstr)
    # change @@ to \0
    tstr = re.sub(r"@@", "\0", tstr)
    # strip invalid xterm codes (non-number)
    tstr = re.sub(r"@[xz]([^\d])", genrepl, tstr)
    # strip invalid xterm codes (300+)
    tstr = re.sub(r"@[xz][3-9]\d\d", "", tstr)
    # strip invalid xterm codes (260+)
    tstr = re.sub(r"@[xz]2[6-9]\d", "", tstr)
    # strip invalid xterm codes (256+)
    tstr = re.sub(r"@[xz]25[6-9]", "", tstr)
    # rip out hidden garbage
    return re.sub(r"@[^xzcmyrgbwCMYRGBWD]", "", tstr)


class ColorsPlugin(BasePlugin):
    """a plugin to handle ansi colors."""

    @AddAPI("colorcode.to.html", description="convert colorcodes to html")
    def _api_colorcode_to_html(self, sinput):
        # pylint: disable=no-self-use,too-many-branches
        """Convert colorcodes to html."""
        tinput = sinput.splitlines()

        olist = []
        lastchar = ""
        for line in tinput:
            lastchar = "\n" if line and line[-1] == "\n" else ""
            stripped_line = line.rstrip()
            # line = fixstring(line)
            if "@@" in stripped_line:
                stripped_line = stripped_line.replace("@@", "\0")
            tlist = re.split(r"(@[cmyrgbwCMYRGBWD]|@[xz]\d\d\d|@[xz]\d\d|@[xz]\d)", stripped_line)

            nlist = []
            color = "w"
            tstart = 0
            tend = 0

            for i in range(len(tlist)):
                # print 'checking %s, i = %s' % (tlist[i], i)
                if tlist[i]:
                    if tlist[i][0] == "@" and tlist[i][1] in "xzcmyrgbwCMYRGBWD":
                        # print 'found color'
                        words = tlist[tstart:tend]
                        if color not in ["x", "D", "w"]:
                            # print 'would put %s in a %s span' % (words, color)
                            nlist.append(createspan(color, "".join(words)))
                        else:
                            # print 'would just add %s' % words
                            nlist.append("".join(words))
                        color = tlist[i][1] if tlist[i][1] in ["x", "z"] else tlist[i]
                        tstart = i + 1
                        tend = i + 1
                    else:
                        tend = tend + 1
                else:
                    tend = tend + 1
                if i == len(tlist) - 1:
                    words = tlist[tstart:]
                    if color not in ["x", "D", "w"]:
                        # print 'would put %s in a %s span' % (words, color)
                        nlist.append(createspan(color, "".join(words)))
                    else:
                        # print 'would just add %s' % words
                        nlist.append("".join(words))
            tstring = "".join(nlist)
            if "\0" in tstring:
                tstring = tstring.replace("\0", "@")

            olist.append(tstring + lastchar)

        return "\n".join(olist) + lastchar

    @AddAPI(
        "color.length.difference",
        description="get the length difference of a colored string and its noncolor equivalent",
    )
    def _api_color_length_difference(self, colorstring):
        """Get the length difference of a colored string and its noncolor equivalent."""
        lennocolor = len(self.api(f"{self.plugin_id}:colorcode.strip")(colorstring))
        lencolor = len(colorstring)
        return lencolor - lennocolor

    # check if a string is an @@ color, either xterm or ansi
    @AddAPI(
        "colorcode.is.valid",
        description="check if a string is a @@ color, either xterm or ansi",
    )
    def _api_colorcode_is_valid(self, color):
        # pylint: disable=no-self-use
        """Check if a string is a @ color, either xterm or ansi."""
        if re.match(r"^@[cmyrgbwCMYRGBWD]$", color):
            return True
        if mat := XTERM_COLOR_REGEX.match(color):
            num = int(mat.groupdict()["num"])
            if num >= 0 and num < 257:
                return True

        return False

    @AddAPI("colorcode.to.ansicode", description="convert @@ colors in a string")
    def _api_colorcode_to_ansicode(self, tstr):
        """Convert @ colors in a string."""
        if "@" in tstr:
            if tstr[-2:] != "@w":
                tstr = f"{tstr}@w"
            tstr = fixstring(tstr)
            tmat = re.search(r"@(\w)([^@]+)", tstr)
            tstr2 = tstr[: tmat.start()] if tmat and tmat.start() != 0 else ""
            for tmatch in re.finditer(r"@(\w)([^@]+)", tstr):
                color, text = tmatch.groups()
                if color == "x":
                    tcolor, newtext = re.findall(r"^(\d\d?\d?)(.*)$", text)[0]
                    color = f"38;5;{tcolor}"
                    tstr2 = tstr2 + self.api(f"{self.plugin_id}:ansicode.to.string")(color, newtext)
                elif color == "z":
                    tcolor, newtext = re.findall(r"^(\d\d?\d?)(.*)$", text)[0]
                    color = f"48;5;{tcolor}"
                    tstr2 = tstr2 + self.api(f"{self.plugin_id}:ansicode.to.string")(color, newtext)
                else:
                    tstr2 = tstr2 + self.api(f"{self.plugin_id}:ansicode.to.string")(
                        CONVERTCOLORS[color], text
                    )

            if tstr2:
                tstr = tstr2 + f"{chr(27)}[0m"
        return re.sub("\0", "@", tstr)  # put @ back in

    @AddAPI("colorcode.escape", description="escape colorcodes so they are not interpreted")
    def _api_colorcode_escape(self, tstr):
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
    def _api_ansicode_to_colorcode(self, text):
        # pylint: disable=no-self-use
        """Convert ansi color escape sequences to @@ colors."""

        def single_sub(match) -> str:
            """Do a single substitution."""
            argsdict = match.groupdict()
            tstr = ""
            tstr += argsdict["arg_1"]
            if argsdict["arg_2"]:
                tstr = tstr + f";{int(argsdict['arg_2'])}"

            if argsdict["arg_3"]:
                tstr = tstr + f";{int(argsdict['arg_3'])}"

            try:
                return f"@{CONVERTANSI[tstr]}"
            except KeyError:
                LogRecord(
                    f"could not lookup color {tstr} for text {text!r}",
                    level="error",
                    plugin=self.plugin_id,
                )()
                return ""

        return ANSI_COLOR_REGEX.sub(single_sub, text)

    @AddAPI("ansicode.to.string", description="return an ansi coded string")
    def _api_ansicode_to_string(self, color, data):
        # pylint: disable=no-self-use
        """Return an ansi coded string."""
        return f"{chr(27)}[{color}m{data}"

    @AddAPI("ansicode.strip", description="strip all ansi from a string")
    def _api_ansicode_strip(self, text):
        # pylint: disable=no-self-use
        """Strip all ansi from a string."""
        return ANSI_COLOR_REGEX.sub("", text)

    @AddAPI("colorcode.strip", description="strip @@ colors")
    def _api_colorcode_strip(self, text):
        """Strip @@ colors."""
        return self.api(f"{self.plugin_id}:ansicode.strip")(
            self.api(f"{self.plugin_id}:colorcode.to.ansicode")(text)
        )

    @AddParser(description="show colors")
    @AddArgument("-c", "--compact", help="show a compact version", action="store_true")
    def _command_show(self):
        """@G%(name)s@w - @B%(cmdname)s@w.

        Show xterm colors
        @CUsage@w: show @Y"compact"@w
          @Y"compact"@w    = The original string to be replaced.
        """
        args = self.api("plugins.core.commands:get.current.command.args")()
        message = [""]
        row_message = []
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

        return True, message

    @AddParser(description="show color examples")
    def _command_example(self):
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
        return True, message
