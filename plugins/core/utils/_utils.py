# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/utils/_utils.py
#
# File Description: a plugin with various utility functions
#
# By: Bast

# Standard Library
import re
import datetime
import math
import time
import fnmatch

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin
from libs.api import AddAPI

TIMELENGTH_REGEXP = re.compile(r"^(?P<days>((\d*\.\d+)|\d+)+d)?" \
                               r":?(?P<hours>((\d*\.\d+)|\d+)+h)?" \
                               r":?(?P<minutes>((\d*\.\d+)|\d+)+m)?" \
                               r":?(?P<seconds>\d+s)?$")

class UtilsPlugin(BasePlugin):
    """
    a plugin to handle ansi colors
    """
    @AddAPI('format.list.into.columns', description='formt the given list in evenly-spaced columns.',)
    def _api_format_list_into_columns(self, obj, cols=4, columnwise=True, gap=4):
        """
        format the given list in evenly-spaced columns.

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
            number_of_columns = int(math.ceil(float(len(list_of_strings)) / float(number_of_columns)))
        plist = [list_of_strings[i: i+number_of_columns] for i in range(0, len(list_of_strings), number_of_columns)]
        if columnwise:
            if len(plist[-1]) != number_of_columns:
                plist[-1].extend(['']*(len(list_of_strings) - len(plist[-1])))
            plist = zip(*plist)
        return '\n'.join(
            [''.join([c.ljust(max_len + gap) for c in p]) for p in plist]
        )

    @AddAPI('convert.timedelta.to.string', description='take two times and return a string of the difference')
    def _api_convert_timedelta_to_string(self, start_time, end_time, fmin=False, colorn='',
                                         colors='', nosec=False):
        """
        take two times and return a string of the difference
        in the form ##d:##h:##m:##s
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
            temp_string = temp_string.replace(' day, ', ':')
            out = temp_string.replace(' days, ', ':')
        else:
            out = f'0:{str(delta)}'
        outar = out.split(':')
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

        out = ":".join(message)
        return out

    @AddAPI('convert.to.readable.number', description='convert a number to a shorter readable number')
    def _api_convert_to_readable_number(self, num, places=2):
        """
        convert a number to a shorter readable number
        """
        converted_string = ''
        nform = "%%00.0%sf" % places
        if not num:
            return 0
        elif num >= 1000000000000:
            converted_string = nform % (num / 1000000000000.0) + " T" # trillion
        elif num >= 1000000000:
            converted_string = nform % (num / 1000000000.0) + " B" # billion
        elif num >= 1000000:
            converted_string = nform % (num / 1000000.0) + " M" # million
        elif num >= 1000:
            converted_string = nform % (num / 1000.0) + " K" # thousand
        else:
            converted_string = num # hundreds
        return converted_string

    @AddAPI('convert.seconds.to.dhms', description='convert seconds to years, days, hours, mins, secs')
    def _api_convert_seconds_to_dhms(self, seconds):
        """
        convert seconds to years, days, hours, mins, secs
        """
        seconds = int(seconds)
        converted_time = {
            'years' : 0,
            'days' : 0,
            'hours' : 0,
            'mins': 0,
            'secs': 0
            }
        if seconds == 0:
            return converted_time

        converted_time['years'] = int(math.floor(seconds/(3600 * 24 * 365)))
        seconds -= converted_time['years'] * 3600 * 24 * 365
        converted_time['days'] = seconds // (3600 * 24)
        seconds -= converted_time['days'] * 3600 * 24
        converted_time['hours'] = seconds // 3600
        seconds -= converted_time['hours'] * 3600
        converted_time['mins'] = seconds // 60
        seconds -= converted_time['mins'] * 60
        converted_time['secs'] = int(seconds % 60)
        return converted_time

    @AddAPI('format.time', description='format a length of time into a string')
    def _api_format_time(self, length, nosec=False):
        """
        format a length of time into a string
        """
        message = []
        converted_time = self.api(f"{self.plugin_id}:convert.seconds.to.dhms")(length)
        years = False
        days = False
        hours = False
        mins = False
        if converted_time['years'] > 0:
            years = True
            message.append(f"{converted_time['years'] or 0}y")
        if converted_time['days'] > 0:
            if years:
                message.append(':')
            days = True
            message.append(f"{converted_time['days'] or 0:02d}d")
        if converted_time['hours']:
            if years or days:
                message.append(':')
            hours = True
            message.append(f"{converted_time['hours'] or 0:02d}h")
        if converted_time['mins'] > 0:
            if years or days or hours:
                message.append(':')
            mins = True
            message.append(f"{converted_time['mins'] or 0:02d}m")
        if (converted_time['secs'] > 0 or not message) and not nosec:
            if years or days or hours or mins:
                message.append(':')
            message.append(f"{converted_time['secs'] or 0:02d}s")

        return ''.join(message)

    # verify a value to be a boolean
    def verify_bool(self, value):
        """
        convert a value to a bool, also converts some string and numbers
        """
        if value in [0, '0']:
            return False
        elif value in [1, '1']:
            return True
        elif isinstance(value, str):
            value = value.lower()
            if value in ['false', 'no']:
                return False
            elif value in ['true', 'yes']:
                return True

        return bool(value)

    # verify a value to contain an @ color
    def verify_color(self, value):
        """
        verify an @ color
        """
        if self.api('plugins.core.colors:colorcode.is.valid')(value):
            return value

        raise ValueError

    # verify a time to be military
    def verify_miltime(self, mtime):
        """
        verify a time like 0830 or 1850
        """
        try:
            time.strptime(mtime, '%H%M')
        except:
            raise ValueError

        return mtime

    # verfiy a time to be valid
    def verify_timelength(self, usertime):
        """
        verify a user time length
        """
        ttime = None

        try:
            ttime = int(usertime)
        except ValueError:
            ttime = self.api(f"{self.plugin_id}:convert.timelength.to.secs")(usertime)

        if ttime == 0 or ttime:
            return ttime
        else:
            raise ValueError

    @AddAPI('verify.value', description='verify that a value is of a certain type')
    def _api_verify_value(self, value, vtype):
        """
        verify values
        """
        vtab = {
            bool: self.verify_bool,
            'color': self.verify_color,
            'miltime': self.verify_miltime,
            'timelength': self.verify_timelength,
        }
        return vtab[vtype](value) if vtype in vtab else vtype(value)

    @AddAPI('center.colored.string', description='center a string with color codes')
    def _api_center_colored_string(self, string_to_center, filler_character='',
                                   length=80, filler_color='', endcaps=False):
        """
        center a string with color codes
        """
        converted_colors_string = self.api('plugins.core.colors:colorcode.to.ansicode')(string_to_center)
        noncolored_string = self.api('plugins.core.colors:ansicode.strip')(converted_colors_string)

        if endcaps:
            length -= 2

        noncolored_string_length = len(noncolored_string) + 4
        length_difference = length - noncolored_string_length
        half_length = length_difference // 2

        filler=filler_character * half_length
        filler_color_end='@w' if filler_color else ''

        new_str = "{filler_color}{filler}{filler_color_end}  {lstring}  {filler_color}{filler}".format(
            filler_color=filler_color,
            filler=filler,
            filler_color_end=filler_color_end,
            lstring=string_to_center)

        new_length = (half_length * 2) + noncolored_string_length

        if new_length < length:
            new_str += filler_character * (length - new_length)

        if endcaps:
            new_str = f'{filler_color}|{filler_color_end}{new_str}{filler_color}|{filler_color_end}'

        new_str = f"{new_str}{filler_color_end}"

        return new_str

    @AddAPI('check.list.for.match', description='check a list for a match of arg')
    def _api_check_list_for_match(self, arg, item_list: list[str]) -> list[str]:
        """
        check a list for a match of arg
        """
        string_to_match = str(arg)
        match = f'{string_to_match}*'
        matches = {'partofstring': [], 'frontofstring': []}
        if arg in item_list or string_to_match in item_list:
            return [arg]

        for i in item_list:
            if fnmatch.fnmatch(i, match):
                matches['frontofstring'].append(i)
            elif isinstance(i, str) and string_to_match in i:
                matches['partofstring'].append(i)

        if matches['frontofstring']:
            return matches['frontofstring']

        return matches['partofstring']

    @AddAPI('convert.timelength.to.secs', description='converts a time length to seconds')
    def _api_convert_timelength_to_secs(self, timel):
        """
        converts a time length to seconds

        Format is 1d:2h:30m:40s, any part can be missing
        """
        timelength_match = TIMELENGTH_REGEXP.match(timel)

        if not timelength_match:
            return None

        timelength_match_groups = timelength_match.groupdict()

        if all([not timelength_match_groups['days'],
                not timelength_match_groups['hours'],
                not timelength_match_groups['minutes'],
                not timelength_match_groups['seconds']]):
            return None

        days = timelength_match_groups['days']
        converted_days = (
            int(days[:-1]) if days.endswith('d') else int(days) if days else 0
        )

        hours = timelength_match_groups['hours']
        converted_hours = (
            int(hours[:-1]) if hours.endswith('h') else int(hours) if hours else 0
        )

        minutes = timelength_match_groups['minutes']
        converted_minutes = (
            int(minutes[:-1])
            if minutes.endswith('m')
            else int(minutes)
            if minutes
            else 0
        )

        seconds = timelength_match_groups['seconds']
        converted_seconds = (
            int(seconds[:-1])
            if seconds.endswith('s')
            else int(seconds)
            if seconds
            else 0
        )

        return converted_days * 24 * 60 * 60 + converted_hours * 60 * 60 + converted_minutes * 60 + converted_seconds

    @AddAPI('convert.data.to.output.table', description='converts a list of dicts to a table, the first list item is the header')
    def _api_convert_data_to_output_table(self, table_name, data, columns, color=''):
        """
        columns is a list of dicts
            dict format:
                'name'  : string for the column name,
                'key'   : dictionary key,
                'width' : the width of the column
        """
        line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')
        output_color = color or self.api('plugins.core.settings:get')('plugins.core.commands', 'output_subheader_color')
        temp_data = [{item['key']: item['name'] for item in columns}, *list(data)]
        color_end = '@w'

        for column in columns:
            column['width'] = max(len(str(item[column['key']])) for item in temp_data)

        # build the template string
        template_strings = [
            "{" + item['key'] + ":<" + str(item['width']) + "}" for item in columns
        ]
        template_string = f'{f" {output_color}|{color_end} ".join(template_strings)}'

        # build the header dict
        header_dict = {item['key']: item['name'] for item in columns}

        subheader_msg = template_string.format(**header_dict)
        data_msg = [template_string.format(**item) for item in data]

        largest_line = max([len(self.api('plugins.core.colors:colorcode.strip')(subheader_msg)),
                           *[len(self.api('plugins.core.colors:colorcode.strip')(line)) for line in data_msg]])

        line_length = max(line_length, largest_line)

        return [
            *self.api('plugins.core.commands:format.header')(table_name, color=output_color, line_length=line_length),
            self.api('plugins.core.utils:cap.line')(subheader_msg, '|', color=output_color, line_length=line_length),
            f'{output_color}{"-" * line_length}',
            *[self.api('plugins.core.utils:cap.line')(line, '|', color=output_color, line_length=line_length) for line in data_msg],
            f'{output_color}{"-" * line_length}',
        ]

    @AddAPI('cap.line', description='caps the line with a character')
    def _api_cap_line(self, line, capchar, color='', line_length=None):
        """
        cap a line with delimiters
        """
        color_end = '@w' if color else ''

        if not line_length:
            line_length = self.api('plugins.core.settings:get')('plugins.core.proxy', 'linelen')

        line_length -= 4
        noncolored_string = self.api('plugins.core.colors:colorcode.strip')(line)

        missing = line_length - len(noncolored_string)

        return f'{color}{capchar}{color_end} {line}{" " * missing} {color}{capchar}{color_end}'
