# Project: bastproxy
# Filename: plugins/core/utils/_utils.py
#
# File Description: a plugin with various utility functions
#
# By: Bast

# Standard Library
import datetime
import fnmatch
import math
import re
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

# 3rd Party
try:
    import dumper

    dumper.instance_dump = "all"
    dumps = dumper.dumps
except ImportError:
    print("Please install required libraries. dumper is missing.")
    print("From the root of the project: uv sync --all-extras")
    sys.exit(1)

# Project
from bastproxy.libs.api import AddAPI
from bastproxy.plugins._baseplugin import BasePlugin

TIMELENGTH_REGEXP = re.compile(
    r"^(?P<days>((\d*\.\d+)|\d+)+d)?"
    r":?(?P<hours>((\d*\.\d+)|\d+)+h)?"
    r":?(?P<minutes>((\d*\.\d+)|\d+)+m)?"
    r":?(?P<seconds>\d+s)?$"
)

_TRUE_WORDS = frozenset({"true", "yes", "on", "1"})
_FALSE_WORDS = frozenset({"false", "no", "off", "0"})


def to_bool(value: Any) -> bool:
    """Convert a bool, a 0/1 int or a true/false word to a bool, else raise ValueError."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
    raise ValueError(f"Cannot convert {value!r} to bool")


def to_int(value: Any) -> int:
    """Convert an int or an integer string to an int; a bool is rejected."""
    if isinstance(value, bool):
        raise ValueError(f"Cannot convert {value!r} to int")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError(f"Cannot convert {value!r} to int")


def to_str(value: Any) -> str:
    """Convert a value to a str."""
    return str(value)


def to_list(value: Any) -> list[Any]:
    """Convert a list or tuple to a new list; anything else raises ValueError."""
    if isinstance(value, (list, tuple)):
        return list(value)
    raise ValueError(f"Cannot convert {value!r} to list")


CONVERTERS: dict[Any, Callable[[Any], Any]] = {
    bool: to_bool,
    int: to_int,
    str: to_str,
    list: to_list,
}


# Characters a split word prefers to break after.
_BREAK_AFTER = (".", "/", "_", "-")


def fit_column_widths(
    natural: Sequence[int],
    word_mins: Sequence[int],
    header_mins: Sequence[int],
    available: int,
    header_word_mins: Sequence[int] | None = None,
) -> list[int]:
    """Shrink column widths until they fit in ``available`` columns, if they can.

    Each phase shrinks the widest column still above that phase's floor; a tie shrinks the
    rightmost column, which keeps the leftmost (usually the key) column intact.

    1. Floor ``word_mins`` (the longest word of the column's cells): cells wrap at spaces only.
    2. Floor ``header_mins`` (the header label's length): cell words are split.
    3. Floor ``header_word_mins`` (the longest word of the header label, default
       ``header_mins``): header labels wrap at spaces.
    4. Floor 1: header words are split too.

    Phases 3 and 4 only run when the table still does not fit, so a table that fits with
    unwrapped headers is never touched by them.
    """
    widths = list(natural)

    def shrink(floors: Sequence[int]) -> None:
        while sum(widths) > available:
            candidates = [i for i, w in enumerate(widths) if w > floors[i]]
            if not candidates:
                return
            widest = max(widths[i] for i in candidates)
            index = max(i for i in candidates if widths[i] == widest)
            widths[index] -= 1

    shrink(word_mins)
    shrink(header_mins)
    shrink(header_mins if header_word_mins is None else header_word_mins)
    shrink([1] * len(widths))
    return widths


def wrap_cell(text: str, width: int, tokenize: Callable[[str], list[tuple[str, str]]]) -> list[str]:
    """Wrap a cell that may hold color codes into lines of at most ``width`` visible columns.

    ``tokenize`` is the ``colorcode.to.tokens`` API: it splits the text into ``(raw, visible)``
    pairs and is the single source of what counts as visible. Lines
    break at single spaces (dropped at the break); a word longer than ``width`` is split. A
    color code stays with the text it precedes, and each continuation line starts with the
    color in effect at its start, unless that color is ``@w`` or there is none. A split word
    breaks after the last ``.``, ``/``, ``_`` or ``-`` that fits, else at ``width``.
    """
    visible: list[str] = []
    raw_visible: list[str] = []  # the raw token behind each visible character
    codes: list[tuple[int, str]] = []  # (visible index the code precedes, raw code)
    for raw, shown in tokenize(text):
        if shown == "":
            codes.append((len(visible), raw))
        else:
            visible.extend(shown)
            if raw == shown:  # plain text: one entry per character
                raw_visible.extend(shown)
            else:  # an escape: one visible character, its raw token
                raw_visible.append(raw)
                raw_visible.extend("" for _ in shown[1:])
    if width < 1 or len(visible) <= width:
        return [text]

    # Find the visible span (start, end) of each line.
    shown_text = "".join(visible)

    def cut_at(word_start: int, size: int) -> int:
        """Where to cut ``size`` characters off a word: after the last punctuation, if any."""
        piece = shown_text[word_start : word_start + size]
        index = max(piece.rfind(char) for char in _BREAK_AFTER)
        return word_start + (index + 1 if index >= 1 else size)

    spans: list[tuple[int, int]] = []
    start = end = -1  # -1: no current line
    for match in re.finditer(r"[^ ]+", shown_text):
        word_start, word_end = match.span()
        if start >= 0 and word_end - start <= width:
            end = word_end
            continue
        if start >= 0 and word_end - word_start > width:
            room = width - (end - start) - (word_start - end)
            if room > 0:
                end = cut_at(word_start, room)
                word_start = end
        if start >= 0:
            spans.append((start, end))
        start = end = -1
        while word_end - word_start > width:
            cut = cut_at(word_start, width)
            spans.append((word_start, cut))
            word_start = cut
        start, end = word_start, word_end
    if start >= 0:
        spans.append((start, end))
    if not spans:
        return [text]

    # Rebuild each line from the visible text and the codes that belong to it.
    lines: list[str] = []
    last_code = ""
    code_index = 0
    for number, (line_start, line_end) in enumerate(spans):
        is_last = number == len(spans) - 1
        next_start = spans[number + 1][0] if not is_last else line_end
        parts: list[str] = [last_code] if last_code and last_code != "@w" else []
        position = line_start
        while True:
            if code_index >= len(codes):
                break
            index, raw = codes[code_index]
            belongs = index < line_end or (index == line_end and (is_last or next_start > line_end))
            if not belongs:
                break
            if index > position:
                parts.append("".join(raw_visible[position:index]))
                position = index
            parts.append(raw)
            last_code = raw
            code_index += 1
        parts.append("".join(raw_visible[position:line_end]))
        lines.append("".join(parts))
    return lines


class UtilsPlugin(BasePlugin):
    """a plugin to handle ansi colors."""

    @AddAPI(
        "column.format",
        description="formt the given list in evenly-spaced columns.",
    )
    def _api_column_format(
        self, obj: list[Any], cols: int = 4, columnwise: bool = True, gap: int = 4
    ) -> list[str]:
        """Format the given list in evenly-spaced columns.

        Parameters
        ----------
        obj : list
            The list to be printed.
        cols : int
            The number of columns in which the list should be printed.
        columnwise : bool, default=True
            If True, the items in the list will be printed column-wise.
            If False the items in the list will be printed row-wise.
        gap : int
            The number of spaces that should separate the longest column
            item/s from the next column. This is the effective spacing
            between columns based on the maximum len() of the list items.
        """
        list_of_strings = [str(item) for item in obj]
        number_of_columns = min(cols, len(list_of_strings))
        max_len = max(len(item) for item in list_of_strings)
        if columnwise:
            number_of_columns = math.ceil(float(len(list_of_strings)) / float(number_of_columns))
        plist = [
            list_of_strings[i : i + number_of_columns]
            for i in range(0, len(list_of_strings), number_of_columns)
        ]
        rows: Iterable[Sequence[str]] = plist
        if columnwise:
            if len(plist[-1]) != number_of_columns:
                plist[-1].extend([""] * (len(list_of_strings) - len(plist[-1])))
            rows = zip(*plist, strict=False)
        return ["".join([c.ljust(max_len + gap) for c in p]) for p in rows]

    @AddAPI("object.dump", description="dump an object as a string")
    def _api_object_dump(self, object: Any) -> str:
        """Dump an object as a string."""
        dumped: str = dumps(object)
        return dumped

    @AddAPI(
        "dict.key.list",
        description="get all keys from a dictionary and any nested dictionaries",
    )
    def _api_dict_key_list(self, d: dict[str, Any]) -> list[Any]:
        keys = []
        for k, v in d.items():
            keys.append(k)
            if isinstance(v, dict):
                keys.extend(self._api_dict_key_list(v))
        return keys

    @AddAPI("string.dedent", description="dedent a list of strings")
    def _api_string_dedent(self, list_of_strings: list[str]) -> list[str]:
        """Dedent a list of strings."""
        if len(list_of_strings) == 0:
            return list_of_strings
        new_data = [list_of_strings[0].lstrip()]
        diff = len(list_of_strings[0]) - len(new_data[0])
        new_data.extend(line[diff:] for line in list_of_strings[1:])
        return new_data

    @AddAPI(
        "timedelta.to.string",
        description="take two times and return a string of the difference",
    )
    def _api_timedelta_to_string(
        self,
        start_time: Any,
        end_time: Any,
        fmin: bool = False,
        colorn: str = "",
        colors: str = "",
        nosec: bool = False,
    ) -> str:
        """Take two times and return a string of the difference.

        in the form ##d:##h:##m:##s.
        """
        # convert start_time to seconds
        if isinstance(start_time, time.struct_time):
            start_time = time.mktime(start_time)
        elif isinstance(start_time, datetime.datetime):
            start_time = start_time.timestamp()
        # convert end_time to seconds
        if isinstance(end_time, time.struct_time):
            end_time = time.mktime(end_time)
        elif isinstance(end_time, datetime.datetime):
            end_time = end_time.timestamp()
        delta = datetime.timedelta(seconds=abs(end_time - start_time))
        if delta.days > 0:
            temp_string = str(delta)
            temp_string = temp_string.replace(" day, ", ":")
            out = temp_string.replace(" days, ", ":")
        else:
            out = f"0:{delta!s}"
        outar: list[str] | list[int] = out.split(":")
        outar = [(int(float(x))) for x in outar]
        message = []
        days, hours = False, False
        if outar[0] != 0:
            days = True
            message.append(f"{colorn}{outar[0]:02d}{colors}d")
        if outar[1] != 0 or days:
            hours = True
            message.append(f"{colorn}{outar[1]:02d}{colors}h")
        if outar[2] != 0 or days or hours or fmin:
            message.append(f"{colorn}{outar[2]:02d}{colors}m")
        if not nosec:
            message.append(f"{colorn}{outar[3]:02d}{colors}s")

        return ":".join(message)

    @AddAPI(
        "number.to.readable",
        description="convert a number to a shorter readable number",
    )
    def _api_number_to_readable(self, num: float, places: int = 2) -> Any:
        """Convert a number to a shorter readable number."""
        converted_string: str | float = ""
        nform = f"%00.0{places}f"
        if not num:
            return 0
        if num >= 1000000000000:
            converted_string = nform % (num / 1000000000000.0) + " T"  # trillion
        elif num >= 1000000000:
            converted_string = nform % (num / 1000000000.0) + " B"  # billion
        elif num >= 1000000:
            converted_string = nform % (num / 1000000.0) + " M"  # million
        elif num >= 1000:
            converted_string = nform % (num / 1000.0) + " K"  # thousand
        else:
            converted_string = num  # hundreds
        return converted_string

    @AddAPI(
        "seconds.to.dhms",
        description="convert seconds to years, days, hours, mins, secs",
    )
    def _api_seconds_to_dhms(self, seconds: float) -> dict[str, int]:
        """Convert seconds to years, days, hours, mins, secs."""
        seconds = int(seconds)
        converted_time = {"years": 0, "days": 0, "hours": 0, "mins": 0, "secs": 0}
        if seconds == 0:
            return converted_time

        converted_time["years"] = math.floor(seconds / (3600 * 24 * 365))
        seconds -= converted_time["years"] * 3600 * 24 * 365
        converted_time["days"] = seconds // (3600 * 24)
        seconds -= converted_time["days"] * 3600 * 24
        converted_time["hours"] = seconds // 3600
        seconds -= converted_time["hours"] * 3600
        converted_time["mins"] = seconds // 60
        seconds -= converted_time["mins"] * 60
        converted_time["secs"] = int(seconds % 60)
        return converted_time

    @AddAPI("timelength.format", description="format a length of time into a string")
    def _api_timelength_format(self, length: float, nosec: bool = False) -> str:
        """Format a length of time into a string."""
        message = []
        converted_time = self.api(f"{self.plugin_id}:seconds.to.dhms")(length)
        years = False
        days = False
        hours = False
        mins = False
        if converted_time["years"] > 0:
            years = True
            message.append(f"{converted_time['years'] or 0}y")
        if converted_time["days"] > 0:
            if years:
                message.append(":")
            days = True
            message.append(f"{converted_time['days'] or 0:02d}d")
        if converted_time["hours"]:
            if years or days:
                message.append(":")
            hours = True
            message.append(f"{converted_time['hours'] or 0:02d}h")
        if converted_time["mins"] > 0:
            if years or days or hours:
                message.append(":")
            mins = True
            message.append(f"{converted_time['mins'] or 0:02d}m")
        if (converted_time["secs"] > 0 or not message) and not nosec:
            if years or days or hours or mins:
                message.append(":")
            message.append(f"{converted_time['secs'] or 0:02d}s")

        return "".join(message)

    # verify a value to contain an @ color
    def verify_color(self, value: Any) -> Any:
        """Verify an @ color."""
        if self.api("plugins.core.colors:colorcode.is.valid")(value):
            return value

        raise ValueError

    # verify a time to be military
    def verify_miltime(self, mtime: str) -> str:
        """Verify a time like 0830 or 1850."""
        try:
            time.strptime(mtime, "%H%M")
        except Exception as e:
            raise ValueError from e

        return mtime

    # verfiy a time to be valid
    def verify_timelength(self, usertime: str) -> Any:
        """Verify a user time length."""
        ttime = None

        try:
            ttime = int(usertime)
        except ValueError:
            ttime = self.api(f"{self.plugin_id}:timelength.to.seconds")(usertime)

        if ttime == 0 or ttime:
            return ttime
        raise ValueError

    @AddAPI("value.verify", description="verify that a value is of a certain type")
    def _api_value_verify(self, value: Any, vtype: Any) -> Any:
        """Convert a value to a setting type, raising ValueError if it cannot be.

        The type is looked up in CONVERTERS, then in the color, miltime and
        timelength handlers, then called if it is callable.
        """
        if vtype in CONVERTERS:
            return CONVERTERS[vtype](value)
        handlers = {
            "color": self.verify_color,
            "miltime": self.verify_miltime,
            "timelength": self.verify_timelength,
        }
        if isinstance(vtype, str) and vtype in handlers:
            return handlers[vtype](value)
        if callable(vtype):
            return vtype(value)
        raise ValueError(f"unknown setting type {vtype!r}")

    @AddAPI("string.center.colored", description="center a string with color codes")
    def _api_string_center_colored(
        self,
        string_to_center: str,
        filler_character: str = "",
        length: int | None = None,
        filler_color: str = "",
        endcaps: bool = False,
        capchar: str = "|",
    ) -> str:
        """Center a string with color codes.

        ``length`` defaults to the current client's line length.
        """
        if length is None:
            length = self.api("plugins.core.proxy:line.length.get")()
        converted_colors_string = self.api("plugins.core.colors:colorcode.to.ansicode")(
            string_to_center
        )
        noncolored_string = self.api("plugins.core.colors:ansicode.strip")(converted_colors_string)

        caplength = 0
        if endcaps:
            caplength = length
            length -= 4

        noncolored_string_length = len(noncolored_string) + 4
        length_difference = length - noncolored_string_length
        half_length = length_difference // 2

        filler = filler_character * half_length
        filler_color_end = "@w" if filler_color else ""

        new_str = (
            f"{filler_color}{filler}{filler_color_end}  {string_to_center}  {filler_color}{filler}"
        )

        new_length = (half_length * 2) + noncolored_string_length

        if new_length < length:
            new_str += filler_character * (length - new_length)

        if endcaps:
            new_str = self.api("plugins.core.utils:line.cap")(
                new_str,
                capchar,
                color=filler_color,
                line_length=caplength,
                space=True,
                fullcolor=False,
            )

        return f"{new_str}{filler_color_end}"

    @AddAPI("string.match.in.list", description="check a list for a match of arg")
    def _api_string_match_in_list(self, arg: str, item_list: list[str]) -> list[str]:
        """Check a list for a match of arg."""
        string_to_match = str(arg)
        match = f"{string_to_match}*"
        matches: dict[str, list[str]] = {"partofstring": [], "frontofstring": []}
        if arg in item_list or string_to_match in item_list:
            return [arg]

        for i in item_list:
            if fnmatch.fnmatch(i, match):
                matches["frontofstring"].append(i)
            elif isinstance(i, str) and string_to_match in i:
                matches["partofstring"].append(i)

        if matches["frontofstring"]:
            return matches["frontofstring"]

        return matches["partofstring"]

    @AddAPI("timelength.to.seconds", description="converts a time length to seconds")
    def _api_timelength_to_seconds(self, timel: str) -> int | None:
        """Converts a time length to seconds.

        Format is 1d:2h:30m:40s, any part can be missing
        """
        timelength_match = TIMELENGTH_REGEXP.match(timel)

        if not timelength_match:
            return None

        timelength_match_groups = timelength_match.groupdict()

        if all(
            [
                not timelength_match_groups["days"],
                not timelength_match_groups["hours"],
                not timelength_match_groups["minutes"],
                not timelength_match_groups["seconds"],
            ]
        ):
            return None

        days = timelength_match_groups["days"]
        converted_days = int(days[:-1]) if days.endswith("d") else int(days) if days else 0

        hours = timelength_match_groups["hours"]
        converted_hours = int(hours[:-1]) if hours.endswith("h") else int(hours) if hours else 0

        minutes = timelength_match_groups["minutes"]
        converted_minutes = (
            int(minutes[:-1]) if minutes.endswith("m") else int(minutes) if minutes else 0
        )

        seconds = timelength_match_groups["seconds"]
        converted_seconds = (
            int(seconds[:-1]) if seconds.endswith("s") else int(seconds) if seconds else 0
        )

        return (
            converted_days * 24 * 60 * 60
            + converted_hours * 60 * 60
            + converted_minutes * 60
            + converted_seconds
        )

    @AddAPI(
        "table.format",
        description="converts a list of dicts to a table with a header",
    )
    def _api_table_format(
        self, table_name: str, data: Any, columns: list[dict[str, Any]], color: str = ""
    ) -> list[str]:
        """Columns is a list of dicts.

        dict format:
            'name'  : string for the column name,
            'key'   : dictionary key,
            'width' : the width of the column.

        Widths and padding ignore color codes, so colored cells stay aligned. When the rows
        are wider than the line length, data cells wrap inside their columns (at spaces, then
        within a word) so the table keeps the line length. When that is still not enough, header
        labels wrap too (at spaces, then within a word, down to one column each); the table grows
        past the line length only when even that cannot fit.
        """
        line_length_default: int = self.api("plugins.core.proxy:line.length.get")()
        output_color = color or self.api("plugins.core.settings:setting.get")(
            "plugins.core.commands", "output_subheader_color"
        )
        temp_data = [{item["key"]: item["name"] for item in columns}, *list(data)]
        color_end = "@w"
        strip = self.api("plugins.core.colors:colorcode.strip")
        tokenize = self.api("plugins.core.colors:colorcode.to.tokens")

        data = list(data)
        header_dict = {item["key"]: item["name"] for item in columns}
        count = len(columns)
        natural = [
            max(len(strip(str(item[column["key"]]))) for item in temp_data) for column in columns
        ]
        header_mins = [max(1, len(strip(str(header_dict[column["key"]])))) for column in columns]
        header_word_mins = [
            max(
                1,
                max(
                    (len(word) for word in strip(str(header_dict[column["key"]])).split(" ")),
                    default=1,
                ),
            )
            for column in columns
        ]
        word_mins = []
        for column, header_min in zip(columns, header_mins, strict=True):
            longest = max(
                (len(word) for item in data for word in strip(str(item[column["key"]])).split(" ")),
                default=0,
            )
            word_mins.append(max(header_min, longest))

        # 4 for the '| ' and ' |' that cap the lines, 3 for each ' | ' between columns
        overhead = 4 + 3 * (count - 1)
        widths = fit_column_widths(
            natural, word_mins, header_mins, line_length_default - overhead, header_word_mins
        )
        for column, width in zip(columns, widths, strict=True):
            column["width"] = width

        separator = f" {output_color}|{color_end} "

        def build_line(item: Any) -> str:
            cells = []
            for column in columns:
                cell = str(item[column["key"]])
                cells.append(cell + " " * (column["width"] - len(strip(cell))))
            return separator.join(cells)

        def build_rows(item: Any) -> list[str]:
            wrapped = [
                wrap_cell(str(item[column["key"]]), column["width"], tokenize) for column in columns
            ]
            height = max(len(cell_lines) for cell_lines in wrapped)
            return [
                build_line(
                    {
                        column["key"]: cell_lines[row] if row < len(cell_lines) else ""
                        for column, cell_lines in zip(columns, wrapped, strict=True)
                    }
                )
                for row in range(height)
            ]

        subheader_msgs = build_rows(header_dict)
        data_msg = [row for item in data for row in build_rows(item)]

        # the table only grows past the line length when even one column per cell cannot fit
        line_length = max(line_length_default, sum(widths) + overhead)

        column_lines = [
            *[
                self.api("plugins.core.utils:line.cap")(
                    subheader_msg, "|", color=output_color, line_length=line_length
                )
                for subheader_msg in subheader_msgs
            ],
            self.api("plugins.core.utils:line.cap")(
                f"{'-' * (line_length - 2)}",
                "+",
                color=output_color,
                line_length=line_length,
                space=False,
                fullcolor=True,
            ),
        ]

        return [
            *self.api("plugins.core.commands:header.format")(
                table_name, color=output_color, line_length=line_length
            ),
            *column_lines,
            *[
                self.api("plugins.core.utils:line.cap")(
                    line, "|", color=output_color, line_length=line_length
                )
                for line in data_msg
            ],
            self.api("plugins.core.utils:line.cap")(
                f"{'-' * (line_length - 2)}",
                "+",
                color=output_color,
                line_length=line_length,
                space=False,
                fullcolor=True,
            ),
        ]

    @AddAPI("line.cap", description="caps the line with a character")
    def _api_line_cap(
        self,
        line: str,
        capchar: str = "|",
        color: str = "",
        line_length: int | None = None,
        space: bool = True,
        fullcolor: bool = False,
    ) -> str:
        """Cap a line with delimiters."""
        color_end = "@w" if color else ""

        spacechar = " " if space else ""

        if not line_length:
            line_length = self.api("plugins.core.proxy:line.length.get")()

        capchar_len = len(capchar + spacechar)

        # account for the lines being capped with '| ' and ' |'
        line_length -= capchar_len * 2

        noncolored_string = self.api("plugins.core.colors:colorcode.strip")(line)

        missing = line_length - len(noncolored_string)

        return (
            f"{color}{capchar}{'' if fullcolor else color_end}{spacechar}{line}"
            f"{' ' * missing}{spacechar}{color}{capchar}{color_end}"
        )
