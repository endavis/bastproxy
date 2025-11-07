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

# 3rd Party
try:
    import dumper

    dumper.instance_dump = "all"
    dumps = dumper.dumps
except ImportError:
    print("Please install required libraries. dumper is missing.")
    print("From the root of the project: pip(3) install -r requirements.txt")
    sys.exit(1)

# Project
from libs.api import AddAPI
from plugins._baseplugin import BasePlugin

TIMELENGTH_REGEXP = re.compile(
    r"^(?P<days>((\d*\.\d+)|\d+)+d)?"
    r":?(?P<hours>((\d*\.\d+)|\d+)+h)?"
    r":?(?P<minutes>((\d*\.\d+)|\d+)+m)?"
    r":?(?P<seconds>\d+s)?$"
)


class UtilsPlugin(BasePlugin):
    """a plugin to handle ansi colors."""

    @AddAPI(
        "format.list.into.columns",
        description="formt the given list in evenly-spaced columns.",
    )
    def _api_format_list_into_columns(self, obj, cols=4, columnwise=True, gap=4):
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
        if columnwise:
            if len(plist[-1]) != number_of_columns:
                plist[-1].extend([""] * (len(list_of_strings) - len(plist[-1])))
            plist = zip(*plist, strict=False)
        return ["".join([c.ljust(max_len + gap) for c in p]) for p in plist]

    @AddAPI("dump.object.as.string", description="dump an object as a string")
    def _api_dump_object_as_string(self, object):
        """Dump an object as a string."""
        return dumps(object)

    @AddAPI(
        "get.keys.from.dict",
        description="get all keys from a dictionary and any nested dictionaries",
    )
    def _api_get_keys_from_dict(self, d):
        keys = []
        for k, v in d.items():
            keys.append(k)
            if isinstance(v, dict):
                keys.extend(self._api_get_keys_from_dict(v))
        return keys

    @AddAPI("dedent.list.of.strings", description="dedent a list of strings")
    def _api_dedent_list_of_strings(self, list_of_strings):
        """Dedent a list of strings."""
        if len(list_of_strings) == 0:
            return list_of_strings
        new_data = [list_of_strings[0].lstrip()]
        diff = len(list_of_strings[0]) - len(new_data[0])
        new_data.extend(line[diff:] for line in list_of_strings[1:])
        return new_data

    @AddAPI(
        "convert.timedelta.to.string",
        description="take two times and return a string of the difference",
    )
    def _api_convert_timedelta_to_string(
        self, start_time, end_time, fmin=False, colorn="", colors="", nosec=False
    ):
        """Take two times and return a string of the difference
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
        outar = out.split(":")
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
        "convert.to.readable.number",
        description="convert a number to a shorter readable number",
    )
    def _api_convert_to_readable_number(self, num, places=2):
        """Convert a number to a shorter readable number."""
        converted_string = ""
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
        "convert.seconds.to.dhms",
        description="convert seconds to years, days, hours, mins, secs",
    )
    def _api_convert_seconds_to_dhms(self, seconds):
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

    @AddAPI("format.time", description="format a length of time into a string")
    def _api_format_time(self, length, nosec=False):
        """Format a length of time into a string."""
        message = []
        converted_time = self.api(f"{self.plugin_id}:convert.seconds.to.dhms")(length)
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

    # verify a value to be a boolean
    def verify_bool(self, value):
        """Convert a value to a bool, also converts some string and numbers."""
        if value in [0, "0"]:
            return False
        if value in [1, "1"]:
            return True
        if isinstance(value, str):
            value = value.lower()
            if value in ["false", "no"]:
                return False
            if value in ["true", "yes"]:
                return True

        return bool(value)

    # verify a value to contain an @ color
    def verify_color(self, value):
        """Verify an @ color."""
        if self.api("plugins.core.colors:colorcode.is.valid")(value):
            return value

        raise ValueError

    # verify a time to be military
    def verify_miltime(self, mtime):
        """Verify a time like 0830 or 1850."""
        try:
            time.strptime(mtime, "%H%M")
        except Exception as e:
            raise ValueError from e

        return mtime

    # verfiy a time to be valid
    def verify_timelength(self, usertime):
        """Verify a user time length."""
        ttime = None

        try:
            ttime = int(usertime)
        except ValueError:
            ttime = self.api(f"{self.plugin_id}:convert.timelength.to.secs")(usertime)

        if ttime == 0 or ttime:
            return ttime
        raise ValueError

    @AddAPI("verify.value", description="verify that a value is of a certain type")
    def _api_verify_value(self, value, vtype):
        """Verify values."""
        vtab = {
            bool: self.verify_bool,
            "color": self.verify_color,
            "miltime": self.verify_miltime,
            "timelength": self.verify_timelength,
        }
        return vtab[vtype](value) if vtype in vtab else vtype(value)

    @AddAPI("center.colored.string", description="center a string with color codes")
    def _api_center_colored_string(
        self,
        string_to_center,
        filler_character="",
        length=80,
        filler_color="",
        endcaps=False,
        capchar="|",
    ):
        """Center a string with color codes."""
        converted_colors_string = self.api("plugins.core.colors:colorcode.to.ansicode")(
            string_to_center
        )
        noncolored_string = self.api("plugins.core.colors:ansicode.strip")(
            converted_colors_string
        )

        caplength = 0
        if endcaps:
            caplength = length
            length -= 4

        noncolored_string_length = len(noncolored_string) + 4
        length_difference = length - noncolored_string_length
        half_length = length_difference // 2

        filler = filler_character * half_length
        filler_color_end = "@w" if filler_color else ""

        new_str = f"{filler_color}{filler}{filler_color_end}  {string_to_center}  {filler_color}{filler}"

        new_length = (half_length * 2) + noncolored_string_length

        if new_length < length:
            new_str += filler_character * (length - new_length)

        if endcaps:
            new_str = self.api("plugins.core.utils:cap.line")(
                new_str,
                capchar,
                color=filler_color,
                line_length=caplength,
                space=True,
                fullcolor=False,
            )

        return f"{new_str}{filler_color_end}"


    @AddAPI("check.list.for.match", description="check a list for a match of arg")
    def _api_check_list_for_match(self, arg, item_list: list[str]) -> list[str]:
        """Check a list for a match of arg."""
        string_to_match = str(arg)
        match = f"{string_to_match}*"
        matches = {"partofstring": [], "frontofstring": []}
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

    @AddAPI(
        "convert.timelength.to.secs", description="converts a time length to seconds"
    )
    def _api_convert_timelength_to_secs(self, timel):
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
        converted_days = (
            int(days[:-1]) if days.endswith("d") else int(days) if days else 0
        )

        hours = timelength_match_groups["hours"]
        converted_hours = (
            int(hours[:-1]) if hours.endswith("h") else int(hours) if hours else 0
        )

        minutes = timelength_match_groups["minutes"]
        converted_minutes = (
            int(minutes[:-1])
            if minutes.endswith("m")
            else int(minutes)
            if minutes
            else 0
        )

        seconds = timelength_match_groups["seconds"]
        converted_seconds = (
            int(seconds[:-1])
            if seconds.endswith("s")
            else int(seconds)
            if seconds
            else 0
        )

        return (
            converted_days * 24 * 60 * 60
            + converted_hours * 60 * 60
            + converted_minutes * 60
            + converted_seconds
        )

    @AddAPI(
        "convert.data.to.output.table",
        description="converts a list of dicts to a table with a header",
    )
    def _api_convert_data_to_output_table(self, table_name, data, columns, color=""):
        """Columns is a list of dicts
        dict format:
            'name'  : string for the column name,
            'key'   : dictionary key,
            'width' : the width of the column.
        """
        line_length_default = self.api("plugins.core.settings:get")(
            "plugins.core.proxy", "linelen"
        )
        output_color = color or self.api("plugins.core.settings:get")(
            "plugins.core.commands", "output_subheader_color"
        )
        temp_data = [{item["key"]: item["name"] for item in columns}, *list(data)]
        color_end = "@w"

        for column in columns:
            column["width"] = max(len(str(item[column["key"]])) for item in temp_data)

        # build the template string
        template_strings = [
            "{" + item["key"] + ":<" + str(item["width"]) + "}" for item in columns
        ]
        template_string = f'{f" {output_color}|{color_end} ".join(template_strings)}'

        # build the header dict
        header_dict = {item["key"]: item["name"] for item in columns}

        subheader_msg = template_string.format(**header_dict)
        data_msg = [template_string.format(**item) for item in data]

        largest_line = max(
            [
                len(self.api("plugins.core.colors:colorcode.strip")(subheader_msg)),
                *[
                    len(self.api("plugins.core.colors:colorcode.strip")(line))
                    for line in data_msg
                ],
            ]
        )

        if largest_line > line_length_default:
            # Add 4 to account for the '| ' and ' |' that cap the lines
            line_length = largest_line + 4
        else:
            line_length = line_length_default

        return [
            *self.api("plugins.core.commands:format.header")(
                table_name, color=output_color, line_length=line_length
            ),
            self.api("plugins.core.utils:cap.line")(
                subheader_msg, "|", color=output_color, line_length=line_length
            ),
            self.api("plugins.core.utils:cap.line")(
                f'{"-" * (line_length - 2)}',
                "+",
                color=output_color,
                line_length=line_length,
                space=False,
                fullcolor=True,
            ),
            *[
                self.api("plugins.core.utils:cap.line")(
                    line, "|", color=output_color, line_length=line_length
                )
                for line in data_msg
            ],
            self.api("plugins.core.utils:cap.line")(
                f'{"-" * (line_length - 2)}',
                "+",
                color=output_color,
                line_length=line_length,
                space=False,
                fullcolor=True,
            ),
        ]

    @AddAPI("cap.line", description="caps the line with a character")
    def _api_cap_line(
        self, line, capchar="|", color="", line_length=None, space=True, fullcolor=False
    ):
        """Cap a line with delimiters."""
        color_end = "@w" if color else ""

        spacechar = " " if space else ""

        if not line_length:
            line_length = self.api("plugins.core.settings:get")(
                "plugins.core.proxy", "linelen"
            )

        capchar_len = len(capchar + spacechar)

        # account for the lines being capped with '| ' and ' |'
        line_length -= capchar_len * 2

        noncolored_string = self.api("plugins.core.colors:colorcode.strip")(line)

        missing = line_length - len(noncolored_string)

        return f'{color}{capchar}{"" if fullcolor else color_end}{spacechar}{line}{" " * missing}{spacechar}{color}{capchar}{color_end}'
