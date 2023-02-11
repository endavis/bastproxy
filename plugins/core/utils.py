# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: plugins/core/utils.py
#
# File Description: a plugin with various utility functions
#
# By: Bast
"""
This plugin handles utility functions
"""
# Standard Library
import re
import datetime
import math
import time
import fnmatch

# 3rd Party

# Project
from plugins._baseplugin import BasePlugin

NAME = 'Utility functions'
SNAME = 'utils'
PURPOSE = 'Utility Functions'
AUTHOR = 'Bast'
VERSION = 1
REQUIRED = True

TIMELENGTH_REGEXP = re.compile(r"^(?P<days>((\d*\.\d+)|\d+)+d)?" \
                               r":?(?P<hours>((\d*\.\d+)|\d+)+h)?" \
                               r":?(?P<minutes>((\d*\.\d+)|\d+)+m)?" \
                               r":?(?P<seconds>\d+s)?$")


class Plugin(BasePlugin):
    """
    a plugin to handle ansi colors
    """
    def __init__(self, *args, **kwargs):
        """
        initialize the plugin
        """
        super().__init__(*args, **kwargs)

        # new api format
        self.api('libs.api:add')('convert:timedelta:to:string', self._api_convert_timedelta_to_string)
        self.api('libs.api:add')('convert:to:readable:number', self._api_convert_to_readable_number)
        self.api('libs.api:add')('convert:seconds:to:dhms', self._api_convert_seconds_to_dhms)
        self.api('libs.api:add')('format:time', self._api_format_time)
        self.api('libs.api:add')('center:colored:string', self._api_center_colored_string)
        self.api('libs.api:add')('check:list:for:match', self._api_check_list_for_match)
        self.api('libs.api:add')('convert:timelength:to:secs', self._api_convert_timelength_to_secs)
        self.api('libs.api:add')('verify:value', self._api_verify_value)
        self.api('libs.api:add')('format:list:into:columns', self._api_format_list_into_columns)

        self.dependencies = ['core.colors']

    def initialize(self):
        """
        initialize the plugin
        """
        BasePlugin.initialize(self)

    def _api_format_list_into_columns(self, obj, cols=4, columnwise=True, gap=4):
        """
        Print the given list in evenly-spaced columns.

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
        if cols > len(list_of_strings):
            number_of_columns = len(list_of_strings)
        else:
            number_of_columns = cols
        max_len = max([len(item) for item in list_of_strings])
        if columnwise:
            number_of_columns = int(math.ceil(float(len(list_of_strings)) / float(number_of_columns)))
        plist = [list_of_strings[i: i+number_of_columns] for i in range(0, len(list_of_strings), number_of_columns)]
        if columnwise:
            if not len(plist[-1]) == number_of_columns:
                plist[-1].extend(['']*(len(list_of_strings) - len(plist[-1])))
            plist = zip(*plist)
        printer = '\n'.join(
            [''.join([c.ljust(max_len + gap) for c in p]) for p in plist])
        return printer

    # return the difference of two times
    def _api_convert_timedelta_to_string(self, start_time, end_time, fmin=False, colorn='',
                                         colors='', nosec=False):
        """
        take two times and return a string of the difference
        in the form ##d:##h:##m:##s
        """
        # convert start_time to seconds
        if isinstance(start_time, time.struct_time):
            start_time = time.mktime(start_time)
        # convert end_time to seconds
        if isinstance(end_time, time.struct_time):
            end_time = time.mktime(end_time)
        delta = datetime.timedelta(seconds=abs(end_time - start_time))
        if delta.days > 0:
            temp_string = str(delta)
            temp_string = temp_string.replace(' day, ', ':')
            out = temp_string.replace(' days, ', ':')
        else:
            out = '0:' + str(delta)
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

    # convert a number to a shorter readable number
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

    # convert seconds to years, days, hours, mins, secs
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
        seconds = seconds - (converted_time['years'] * 3600 * 24 * 365)
        converted_time['days'] = int(math.floor(seconds/(3600 * 24)))
        seconds = seconds - (converted_time['days'] * 3600 * 24)
        converted_time['hours'] = int(math.floor(seconds/3600))
        seconds = seconds - (converted_time['hours'] * 3600)
        converted_time['mins'] = int(math.floor(seconds/60))
        seconds = seconds - (converted_time['mins'] * 60)
        converted_time['secs'] = int(seconds % 60)
        return converted_time

    # format a length of time into a string
    def _api_format_time(self, length, nosec=False):
        """
        format a length of time into a string
        """
        message = []
        converted_time = self.api('plugins.core.utils:convert:seconds:to:dhms')(length)
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
        if value == 0 or value == '0':
            return False
        elif value == 1 or value == '1':
            return True
        elif isinstance(value, str):
            value = value.lower()
            if value == 'false' or value == 'no':
                return False
            elif value == 'true' or value == 'yes':
                return True

        return bool(value)

    # verify a value to contain an @ color
    def verify_color(self, value):
        """
        verify an @ color
        """
        if self.api('plugins.core.colors:colorcode:is:valid')(value):
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
            ttime = self.api('plugins.core.utils:convert:timelength:to:secs')(usertime)

        if ttime != 0 and not ttime:
            raise ValueError

        return ttime

    # verify different types
    def _api_verify_value(self, value, vtype):
        """
        verify values
        """
        vtab = {}
        vtab[bool] = self.verify_bool
        vtab['color'] = self.verify_color
        vtab['miltime'] = self.verify_miltime
        vtab['timelength'] = self.verify_timelength

        if vtype in vtab:
            return vtab[vtype](value)

        return vtype(value)

    # center a string with color codes
    def _api_center_colored_string(self, string_to_center, filler_character, length):
        """
        center a string with color codes
        """
        converted_colors_string = self.api('plugins.core.colors:colorcode:to:ansicode')(string_to_center)
        noncolored_string = self.api('plugins.core.colors:ansicode:strip')(converted_colors_string)

        noncolored_string_length = len(noncolored_string) + 4
        length_difference = length - noncolored_string_length

        half_length = length_difference / 2
        new_str = "{filler}  {lstring}  {filler}".format(
            filler=filler_character * half_length,
            lstring=string_to_center)

        new_length = (half_length * 2) + noncolored_string_length

        if new_length < length:
            new_str = new_str + '-' * (length - new_length)

        return new_str

    # check a list for a match
    def _api_check_list_for_match(self, arg, tlist):
        """
        check a list for a match of arg
        """
        string_to_match = str(arg)
        matches = {}
        match = string_to_match + '*'
        matches['partofstring'] = []
        matches['frontofstring'] = []

        if arg in tlist or string_to_match in tlist:
            return [arg]

        for i in tlist:
            if fnmatch.fnmatch(i, match):
                matches['frontofstring'].append(i)
            elif isinstance(i, str) and string_to_match in i:
                matches['partofstring'].append(i)

        if matches['front']:
            return matches['front']

        return matches['part']

    # convert a time length to seconds
    def _api_convert_timelength_to_secs(self, timel):
        """
        converts a time length to seconds

        Format is 1d:2h:30m:40s, any part can be missing
        """
        timelength_match = TIMELENGTH_REGEXP.match(timel)

        if not timelength_match:
            return None

        timelength_match_groups = timelength_match.groupdict()

        if not timelength_match_groups['days'] \
             and not timelength_match_groups['hours'] \
             and not timelength_match_groups['minutes'] \
             and not timelength_match_groups['seconds']:
            return None

        days = timelength_match_groups['days']
        if not days:
            days = 0
        elif days.endswith('d'):
            days = float(days[:-1])

        hours = timelength_match_groups['hours']
        if not hours:
            hours = 0
        elif hours.endswith('h'):
            hours = float(hours[:-1])

        minutes = timelength_match_groups['minutes']
        if not minutes:
            minutes = 0
        elif minutes.endswith('m'):
            minutes = float(minutes[:-1])

        seconds = timelength_match_groups['seconds']
        if not seconds:
            seconds = 0
        elif seconds.endswith('s'):
            seconds = int(seconds[:-1])

        return days * 24 * 60 * 60 + hours * 60 * 60 + minutes * 60 + seconds
