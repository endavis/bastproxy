# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api.py
#
# File Description: create an api for use by plugins and modules
#
# By: Bast
"""
this module handles the api for all other modules

Most api functions will go in as a class api.

However, some api functions will need to be overloaded.
The main reason for overloading an api is when
a class instance calls an api function and needs to access itself,
or there are multiple instances of a class that will add the
same function to the api.

regular apis are in the class variable "api"
overloaded apis are in the instance variable "_instance_api"

See the BasePlugin class
"""
# Standard Library
import inspect
import pprint
import typing
from itertools import chain
import traceback
from pathlib import Path
from datetime import datetime

# Third Party

# Project

def stackdump(id='', msg='HERE') -> None:
    raw_tb = traceback.extract_stack()
    entries: list[str] = traceback.format_list(raw_tb)

    # Remove the last two entries for the call to extract_stack() and to
    # the one before that, this function. Each entry consists of single
    # string with consisting of two lines, the script file path then the
    # line of source code making the call to this function.
    del entries[-2:]

    # Split the stack entries on line boundaries.
    lines = list(chain.from_iterable(line.splitlines() for line in entries))
    lines.insert(0, msg)
    lines.insert(0, '\n')
    if msg:  # Append it to last line with name of caller function.
        lines.append('LEAVING STACK_DUMP' + (': '+id) if id else '')
    try:
        from libs.records import LogRecord
        LogRecord(lines, level='warning', sources=[__name__]).send()
    except ImportError:
        print('\n'.join(lines))
        print()

def get_args(api_function: typing.Callable) -> str:
    """
    Get the arguments of a given function from a it's function declaration.

    Parameters
    ----------
    api_function : Callable
        The function to get the arguments for.

    Returns
    -------
    str
        A string containing the function arguments.
    """
    sig = inspect.signature(api_function)
    argn: list[str] = []
    for i in sig.parameters:
        if str(i) == 'self':
            continue
        argn.append(f"@Y{str(i)}@w")

    args: str = ', '.join(argn)

    return args

def get_caller_owner_id(ignore_owner_list: list[str] | None = None) -> str:
    """
    Returns the owner ID of the plugin that called the current function.

    It goes through the stack and checks each frame for one of the following:
        an owner_id attribute
        an api attribute and gets the owner_id from that

    Args:
        ignore_owner_list (list[str]): A list of owner IDs to ignore if they are on the stack.

    Returns:
        str: The owner ID of the plugin on the stack.
    """
    ignore_owner_list = ignore_owner_list if ignore_owner_list else []

    caller_id = 'unknown'
    try:
        stack = inspect.stack()
    except IndexError:
        return caller_id

    for ifr in stack[1:]:
        parent_frame = ifr[0]
        if 'self' in parent_frame.f_locals and not isinstance(parent_frame.f_locals['self'], APIItem):
            tcs = parent_frame.f_locals['self']
            if hasattr(tcs, 'owner_id') and tcs.owner_id and tcs.owner_id not in ignore_owner_list:
                caller_id = tcs.owner_id
                break
            if hasattr(tcs, 'api'):
                if isinstance(tcs.api, API):
                    if tcs.api.owner_id and tcs.api.owner_id not in ignore_owner_list:
                        caller_id = tcs.api.owner_id
                        break

    del stack

    return caller_id

class APIStatItem:
    """
    This class is used to track the number of times that a particular
    API has been called by a particular caller.  The full_api_name is
    the full name of the API, including the full package, module,
    and name of the function, and the caller_id is the ID of
    the object/function that is making the call.
    """
    def __init__(self, full_api_name: str) -> None:
        """
        Initializes an APIStatItem object.

        Args:
            full_api_name (str): Full name of the API, including the full package,
                module, and name of the function.
        """
        self.full_api_name: str = full_api_name
        self.calls_by_caller: dict[str, int] = {}
        self.detailed_calls: dict[str, int] = {}
        self.count: int = 0  # Total number of calls to this API

    def add_call(self, caller_id: str) -> None:
        """
        Adds a call to the APIStatItem object.

        Args:
            caller_id (str): ID of the caller
        """
        self.count += 1
        if (not caller_id or caller_id == 'unknown'):
            stackdump(msg=f"------------ Unknown caller_id for API call: {self.full_api_name} -----------------")
        if caller_id not in self.detailed_calls:
            self.detailed_calls[caller_id] = 0
        self.detailed_calls[caller_id] += 1

        if ':' in caller_id:
            caller_id = caller_id.split(':')[0]
        if caller_id not in self.calls_by_caller:
            self.calls_by_caller[caller_id] = 0
        self.calls_by_caller[caller_id] += 1

class StatsManager:
    """
    Holds the stats for all API items.
    """
    def __init__(self) -> None:
        """
        Initializes a StatsManager object.
        """
        self.stats: dict[str, APIStatItem] = {}

    def add_call(self, full_api_name: str, caller_id: str) -> None:
        """
        Adds a call to the StatsManager object.

        Args:
            full_api_name (str): Full name of the API, including the full package,
                module, and name of the function.
            caller_id (str): Id of what object is calling the function
        """
        if full_api_name not in self.stats:
            self.stats[full_api_name] = APIStatItem(full_api_name)
        self.stats[full_api_name].add_call(caller_id)

    def get_all_stats(self) -> dict[str, APIStatItem]:
        """
        Returns the stats held in the StatsManager object.

        Returns:
            dict: A dictionary of the stats held in the object.
        """
        return self.stats

    def get_stats(self, full_api_name) -> APIStatItem | None:
        """
        Returns the stats for a specific API.

        Args:
            full_api_name (str): Full name of the API, including the full package,
                module, and name of the function.

        Returns:
            dict: A dictionary of the stats for the API.
        """
        return self.stats.get(full_api_name, None)

STATS_MANAGER = StatsManager()

class APIItem:
    """
    Wraps an API function to track its use.
    """
    def __init__(self, full_api_name: str, tfunction: typing.Callable, owner_id: str | None) -> None:
        """
        Initializes an APIItem object.

        Args:
            full_api_name (str): Full name of the API, including the full package,
                module, and name of the function.
            tfunction (callable): The function to be wrapped.
            plugin_id (str): Unique ID of the plugin calling the function.
        """
        self.full_api_name: str = full_api_name
        self.owner_id: str = owner_id if owner_id else 'unknown'
        self.tfunction: typing.Callable = tfunction
        self.overloaded: bool = False
        self.overwritten_api: APIItem | None = None

    def __call__(self, *args, **kwargs):
        """
        Calls the wrapped function and adds a call to the StatsManager object.
        """
        caller_id: str = get_caller_owner_id()
        STATS_MANAGER.add_call(self.full_api_name, caller_id)
        return self.tfunction(*args, **kwargs)

    @property
    def count(self) -> int:
        """
        Returns the number of times the API has been called.

        Returns:
            int: The number of times the API has been called.
        """
        stats = STATS_MANAGER.stats.get(self.full_api_name, None)
        if stats:
            return stats.count
        return 0

    @property
    def stats(self) -> APIStatItem | None:
        """
        Returns the stats for the API.

        Returns:
            dict: A dictionary of the stats for the API.
        """
        stats = STATS_MANAGER.stats.get(self.full_api_name, None)
        if stats:
            return STATS_MANAGER.stats[self.full_api_name]
        else:
            return None

    def detail(self) -> list[str]:
        """
        create a detailed message for this item
        """
        tmsg: list[str] = []

        tmsg.append(f"@C{'API':<11}@w : {self.full_api_name}")
        tmsg.append(f"@C{'Function':<11}@w : {self.tfunction}")
        tmsg.append(f"@C{'Owner':<11}@w : {self.owner_id}")
        tmsg.append(f"@C{'Overloaded':<11}@w : {self.overloaded}")

        tmsg.append('')

        args = get_args(self.tfunction)

        location_split = self.full_api_name.split(':')
        name = location_split[0]
        command_name = ':'.join(location_split[1:])
        tdict = {'name':name, 'cmdname':command_name, 'api_location':self.full_api_name}

        tmsg.append(f"@G{self.full_api_name}@w({args})")
        if self.tfunction.__doc__:
            tmsg.append(self.tfunction.__doc__ % tdict)

        tmsg.append('')

        sourcefile = inspect.getsourcefile(self.tfunction)
        if sourcefile:
            tmsg.append(f"function defined in {sourcefile.replace(str(API.BASEPATH), '')}")

        tmsg.append('')

        if self.overwritten_api:
            tmsg.append('')
            tmsg.append(f"This API overwrote the following:")
            for line in self.overwritten_api.detail():
                tmsg.append(f"    {line}")

        return tmsg

    def __repr__(self) -> str:
        """
        Returns a string representation of the APIItem object.

        Returns:
            str: A string representation of the object.
        """
        return f"APIItem({self.full_api_name}, {self.owner_id}, {self.tfunction})"

    def __str__(self) -> str:
        """
        Returns a string representation of the APIItem object.

        Returns:
            str: A string representation of the object.
        """
        return f"APIItem({self.full_api_name}, {self.owner_id}, {self.tfunction})"

class API():
    """
    A class that exports an api for plugins and modules to use
    """
    # where the main api resides
    _class_api: dict[str, APIItem] = {}

    # stats for the api
    stats: dict[str, APIStatItem] = {}

    # the basepath that the proxy was run from, will be dynamically set in
    # bastproxy.py
    BASEPATH: Path = Path('')
    BASEDATAPATH: Path = Path('')
    BASEDATAPLUGINPATH: Path = Path('')
    BASEDATALOGPATH: Path = Path('')
    BASEPLUGINPATH: Path = Path('')

    TIMEZONE: str = ''

    # a flag to show that bastproxy is starting up
    startup: bool = False

    # a flag to show that bastproxy is shutting down
    shutdown: bool = False

    # a dictionary of managers that could not be made into plugins
    MANAGERS: dict[str, typing.Any] = {}
    MANAGERS['api_stats'] = STATS_MANAGER

    # the proxy start time, will be dynamically set in bastproxy.py
    proxy_start_time: datetime | None = None

    # the regex to use to split commands, the seperator is configured in
    # the proxy plugin
    command_split_regex: str | None = None

    # flag to set the character active flag for connecting.
    # set this after the mud has been connected to and
    # is available for active commands to be sent
    is_character_active: bool = False

    def __init__(self, owner_id: str | None=None) -> None:
        """
        initialize the class
        """
        # apis that have been overloaded will be put here
        self._instance_api: dict[str, APIItem] = {}

        # the format for the time
        self.time_format: str = '%a %b %d %Y %H:%M:%S %Z'

        # this is the parent of the API, couild be a plugin or a module
        self.owner_id: str = owner_id if owner_id else 'unknown'

        # added functions
        self.add('libs.api', 'add', self.add, overload=True)
        self.add('libs.api', 'has', self._api_has, overload=True)
        if not self('libs.api:has')('libs.api:remove'):
            self.add('libs.api', 'remove', self._api_remove, overload=True)
        if not self('libs.api:has')('libs.api:get:children'):
            self.add('libs.api', 'get:children', self._api_get_children, overload=True)
        if not self('libs.api:has')('libs.api:run:as:plugin'):
            self.add('libs.api', 'run:as:plugin', self._api_run_as_plugin, overload=True)
        if not self('libs.api:has')('libs.api:detail'):
            self.add('libs.api', 'detail', self._api_detail, overload=True)
        if not self('libs.api:has')('libs.api:list'):
            self.add('libs.api', 'list', self._api_list, overload=True)
        if not self('libs.api:has')('libs.api:data:get'):
            self.add('libs.api', 'api:data:get', self._api_data_get, overload=True)
        if not self('libs.api:has')('libs.api:get:function:owner:plugin'):
            self.add('libs.api', 'get:function:owner:plugin', self._api_get_function_plugin_owner, overload=True)
        if not self('libs.api:has')('libs.api:get:caller:owner'):
            self.add('libs.api', 'get:caller:owner', self._api_caller_owner, overload=True)
        if not self('libs.api:has')('libs.api:is_character_active'):
            self.add('libs.api', 'is_character_active', self._api_is_character_active_get, overload=True)
        if not self('libs.api:has')('libs.api:is_character_active:set'):
            self.add('libs.api', 'is_character_active:set', self._api_is_character_active_set, overload=True)

    def add_events(self) -> None:
        """
        add events for the api
        """
        self('plugins.core.events:add:event')('ev_libs.api_character_active', __name__,
                                            description='An event for when the character is active and ready for commands',
                                            arg_descriptions={'is_character_active':'The state of the is_character_active flag'})
        self('plugins.core.events:add:event')('ev_libs.api_character_inactive', __name__,
                                            description='An event for when the character is inactive and not ready for commands',
                                            arg_descriptions={'is_character_active':'The state of the is_character_active flag'})

    # get the firstactive flag
    def _api_is_character_active_get(self) -> bool:
        """
        returns the is_character_active flag
        """
        return self.is_character_active

    def _api_is_character_active_set(self, flag:bool) -> None:
        """
        set the is_character_active flag
        """
        self.__class__.is_character_active = flag

        if flag:
            self('plugins.core.events:raise:event')('ev_libs.api_character_active',
                                            args={'is_character_active':self.is_character_active},
                                            calledfrom='libs.api')
        else:
            self('plugins.core.events:raise:event')('ev_libs.api_character_inactive',
                                            args={'is_character_active':self.is_character_active},
                                            calledfrom='libs.api')

    # return the data for an api
    def _api_data_get(self, api_name: str, base: bool = False) -> APIItem | None:
        """
        return the data for an api
        """
        if api_name in self._instance_api and not base:
            return self._instance_api[api_name]
        elif api_name in self._class_api:
            return self._class_api[api_name]

        return None

    # add a function to the api
    def add(self, top_level_api: str, name: str, tfunction: typing.Callable, overload: bool = False, force: bool = False) -> bool:
        """  add a function to the api
        @Ytop_level_api@w  = the toplevel that the api should be under
        @Yname@w  = the name of the api
        @Yfunction@w  = the function
        @Yoverload@w  = bool, True to add to instance api, false to add to class api

        the function is added as toplevel.name into the api

        if the api already exists, it is added to the overloaded

        this function returns no values"""
        full_api_name: str = top_level_api + ':' + name

        api_item = APIItem(full_api_name, tfunction, self.owner_id)

        if not overload:
            if full_api_name in self._class_api:
                if force:
                    api_item.overwritten_api = self._class_api[full_api_name]
                    self._class_api[full_api_name] = api_item
                else:
                    try:
                        from libs.records import LogRecord
                        added_in = self._class_api[full_api_name].owner_id
                        LogRecord(f"libs.api:add - {full_api_name} already exists from plugin {added_in}",
                                    level='error', sources=[__name__, self.owner_id]).send()
                    except ImportError:
                        print(f"libs.api:add - {full_api_name} already exists")
                        return False
            else:
                self._class_api[full_api_name] = api_item

        else:
            return self._api_overload(api_item, force)

        return False

    # overload a function in the api
    def _api_overload(self, api_item: APIItem, force: bool = False) -> bool:
        """  overload a function in the api
        @Yapi_data@w  = the api data dictionary

        the function is added as api_data['full_api_name'] into the overloaded api

        this function returns True if added, False otherwise"""
        if api_item.full_api_name in self._instance_api:
            if force:
                api_item.overwritten_api = self._instance_api[api_item.full_api_name]
                api_item.overloaded = True
                self._instance_api[api_item.full_api_name] = api_item
            else:
                try:
                    from libs.records import LogRecord
                    LogRecord(f"libs.api:overload - {api_item.full_api_name} already exists from plugin: {api_item.owner_id}",
                            level='error', sources=[__name__, api_item.owner_id]).send()
                except ImportError:
                    print(f"libs.api:overload - {api_item.full_api_name} already exists")

                return False
        else:
            api_item.overloaded = True
            self._instance_api[api_item.full_api_name] = api_item

        return True

    # find the caller of this api
    def _api_caller_owner(self, ignore_owner_list: list[str] | None=None) -> str:
        """  get the plugin on the top of the frame stack
        @Yignore_plugin_list@w  = ignore the plugins (by plugin_id) in this list if they are on the stack

        check to see if the caller is a plugin, if so return the plugin id

        this is so plugins can figure out who gave them data and keep up with it.

        it will return the first plugin found when going through the stack
            it checks for a BasePlugin instance of self
            if it doesn't find that, it checks for an attribute of plugin

        returns the plugin_id of the plugin on the stack"""
        return get_caller_owner_id(ignore_owner_list)

    def _api_get_function_plugin_owner(self, function: typing.Callable) -> str:
        """  get the plugin_id of the plugin that owns the function
        @Yfunction@w  = the function

        this function returns the plugin_id of the plugin that owns the function"""
        plugin_id = 'unknown'
        try:
            plugin_id = function.__self__.plugin_id
        except AttributeError:
            pass

        return plugin_id

    # remove a toplevel api
    def _api_remove(self, top_level_api: str) -> None:
        """  remove a toplevel api
        @Ytop_level_api@w  = the toplevel of the api to remove

        this function returns no values"""
        api_toplevel = top_level_api + ":"

        tkeys = sorted(self._class_api.keys())
        for i in tkeys:
            if i.startswith(api_toplevel):
                del self._class_api[i]

        tkeys = sorted(self._instance_api.keys())
        for i in tkeys:
            if i.startswith(api_toplevel):
                del self._instance_api[i]

    def _api_run_as_plugin(self, plugin_id: str, api_location: str):
        """
        run an api as another plugin
        """
        plugin_instance = self('plugins.core.plugins:get:plugin:instance')(plugin_id)

        if plugin_instance:
            return plugin_instance.api(api_location)
        else:
            try:
                from libs.records import LogRecord
                LogRecord(f"_api_run_as_plugin: {plugin_id} plugin does not exist",
                          level='error', sources=[__name__]).send()
            except ImportError:
                print(f"_api_run_as_plugin: {plugin_id} plugin does not exist")

    def get(self, api_location: str, do_not_overload: bool = False) -> typing.Callable:
        """
        get an api function

        do_not_overload = get the non overloaded api
        """
        # all apis should have a . in the first part
        # if not, we add the parent plugin id to the api
        if '.' not in api_location:
            if self.owner_id.lower() != 'unknown':
                api_location = self.owner_id + ':' + api_location
            else:
                try:
                    from libs.records import LogRecord
                    LogRecord(f"api lookup: {api_location} : did not contain a .",
                              level='error', sources=[__name__]).send()
                except ImportError:
                    print(f"api lookup: {api_location} : did not contain a .")

        # check overloaded api
        if not do_not_overload:
            if api_location in self._instance_api and self._instance_api[api_location]:
                return self._instance_api[api_location]

        # check api
        if api_location in self._class_api and self._class_api[api_location]:
            return self._class_api[api_location]

        raise AttributeError(f"{self.owner_id} : {api_location} is not in the api")

    __call__ = get

    # return a list of api functions in a toplevel api
    def _api_get_children(self, parent_api: str) -> list[str]:
        """
        return a list of apis in a toplevel api
        """
        api_list: list[str] = []
        if parent_api[-1] != ':':
            parent_api = parent_api + ':'

        tkeys = sorted(self._class_api.keys())
        for full_api_name in tkeys:
            if full_api_name.startswith(parent_api):
                api_list.append(full_api_name[len(parent_api):])

        tkeys = sorted(self._instance_api.keys())
        for full_api_name in tkeys:
            if full_api_name.startswith(parent_api):
                api_list.append(full_api_name[len(parent_api):])

        return list(set(api_list))

    # check to see if something exists in the api
    def _api_has(self, api_location: str) -> bool:
        """
        see if something exists in the api
        """
        try:
            self.get(api_location)
            return True
        except AttributeError:
            return False

    # get the details for an api function
    def _api_detail(self, api_location: str, stats_by_plugin: bool = False, stats_by_caller: str | None = None) -> list[str]:     # pylint: disable=too-many-locals,too-many-branches
        # parsing a function declaration and figuring out where the function
        # resides is intensive, so disabling pylint warning
        """
        return the detail of an api function
        """
        tmsg: list[str] = []
        api_original = None
        api_overloaded = None

        if ':' not in api_location:
            tmsg.append(f"{api_location} is not a : api format")
            return tmsg

        if api_location:
            try:
                api_original = self._class_api[api_location]
            except KeyError:
                pass

            try:
                api_overloaded = self._instance_api[api_location]
            except KeyError:
                pass

            if not api_original and not api_overloaded:
                tmsg.append(f"{api_location} is not in the api")
                return tmsg

            if api_original:
                tmsg.append('Original API')
                tmsg.append('============')
                tmsg.extend(api_original.detail())

            if api_overloaded:
                tmsg.append('Overloaded API')
                tmsg.append('============')
                tmsg.extend(api_overloaded.detail())

            if stats_by_plugin or stats_by_caller:
                api_data = self._api_data_get(api_location)

                if api_data and api_data.stats:
                    if stats_by_plugin:
                        tmsg.append('')
                        tmsg.append(self('plugins.core.utils:center:colored:string')('Stats', '-', 70, '@B'))
                        tmsg.append('Total Calls: %s' % api_data.stats.count)
                        tmsg.append('@B' + '-' * 50)
                        tmsg.append('Stats by caller')
                        tmsg.append('@B' + '-' * 50)
                        stats_keys = api_data.stats.calls_by_caller.keys()
                        stats_keys = sorted(stats_keys)
                        for i in stats_keys:
                            tmsg.append(f"{i or 'unknown':<30}: {api_data.stats.calls_by_caller[i]}")

                    if stats_by_caller:
                        tmsg.append('')
                        tmsg.append(self('plugins.core.utils:center:colored:string')(f"Stats for {stats_by_caller}", '-', 70, '@B'))
                        stats_keys = [k for k in api_data.stats.detailed_calls.keys() if k.startswith(stats_by_caller)]
                        tmsg.append(f"Unique Callers: {len(stats_keys)}")
                        stats_keys = sorted(stats_keys)
                        for i in stats_keys:
                            tmsg.append(f"{i or 'unknown':<22}: {api_data.stats.detailed_calls[i]}")

        else:
            tmsg.append(f"{api_location} is not in the api")

        return tmsg

    def get_top_level_api_list(self, top_level_api: str) -> list[str]:
        """
        build a list of apis in toplevel
        """
        api_list: list[str] = []

        for i in self._class_api:
            if i.startswith(top_level_api):
                api_list.append(i)

        for i in self._instance_api:
            if i.startswith(top_level_api):
                api_list.append(i)

        return list(set(api_list))

    def get_full_api_list(self) -> list[str]:
        """
        build a list of all apis
        """
        api_list: list[str] = []
        api_list.extend(self._class_api.keys())
        api_list.extend(self._instance_api.keys())

        api_list = list(set(api_list))
        api_list.sort()
        return api_list

    # return a formatted list of functions in a toplevel api
    def _api_list(self, top_level_api: str = '') -> list[str]:
        """
        return a formatted list of functions in an api
        """
        tmsg: list[str] = []
        api_list = self.get_top_level_api_list(top_level_api) if top_level_api else self.get_full_api_list()

        api_list.sort()

        top_levels: list[str] = []
        for i in api_list:
            toplevel, therest = i.split(':', 1)
            if toplevel not in top_levels:
                if len(top_levels) > 0:
                    tmsg.append('@B' + '-' * 50 + '@w')
                top_levels.append(toplevel)
                tmsg.append(f"@G{toplevel:<10}@w")
                tmsg.append('@B' + '-' * 50 + '@w')
            api_data: APIItem | None = self._api_data_get(i)

            if api_data:
                comments = inspect.getcomments(api_data.tfunction)
                comments = comments.strip() if comments else ''
                added_by = ''
                if api_data.owner_id:
                    added_by = f"- added in {api_data.owner_id} "
                tmsg.append(f"   @C{therest:<30}@w - {comments}@w")
                tmsg.append(f"        {added_by} - called {api_data.count} times @w")

        return tmsg

def test():
    """
    do some testing for the api
    """
    # some generic description
    def testapi(msg):
        """
        a test api
        """
        return msg + ' (orig)'

    def overloadtestapi(msg):
        """
        a overload test api
        """
        return msg + ' (overload)'

    def overloadtestapi2(msg):
        """
        a overload test api
        """
        return msg + ' (overload2)'


    print('-' * 80)
    api = API()
    print('adding test:api')
    api('libs.api:add')('a.test', 'api', testapi)
    print('adding test:over')
    api('libs.api:add')('a.test', 'over', testapi)
    print('adding test:some:api')
    api('libs.api:add')('a.test', 'some:api', testapi)
    print('called api a.test:api', api('a.test:api')('success'))
    print('called api a.test:over', api('a.test:over')('success'))
    print('called api a.test:some:api', api('a.test:some:api')('success'))
    print('dict api._class_api:\n', pprint.pformat(api._class_api))
    print('dict api._instance_api:\n', pprint.pformat(api._instance_api))
    print('overloading over.api')
    api('libs.api:add')('a.over', 'api', overloadtestapi, overload=True)
    print('overloading test.over')
    api('libs.api:add')('a.test', 'over', overloadtestapi, overload=True)
    print('dict api._instance_api:\n', pprint.pformat(api._instance_api))
    print('called api over:api', api('a.over:api')('success'))
    print('called api test:over', api('a.test:over')('success'))
    print('called api test:api', api('a.test:api')('success'))
    print('api.has test:over', api('libs.api:has')('a.test:over'))
    print('api.has test:over2', api('libs.api:has')('a.test:over2'))
    print('api.has over:api', api('libs.api:has')('a.over:api'))
    print('api.has test:some:api', api('libs.api:has')('a.test:some.api'))
    print('dict api._class_api:\n', pprint.pformat(api._class_api))
    print('dict api.overloadapi:\n', pprint.pformat(api._instance_api))
    print('\n'.join(api('libs.api:list')(top_level_api="test")))
    print('--------------------')
    print('\n'.join(api('libs.api:list')()))
    print('--------------------')
    print('\n'.join(api('libs.api:detail')('a.test:over')))
    print('--------------------')


    print('-' * 80)
    api2 = API()
    print('api: ', api)
    print('api2: ', api2)
    print('dict api._class_api:\n', pprint.pformat(api._class_api))
    print('dict api._instance_api:\n', pprint.pformat(api._instance_api))
    print('api2 dict api2.api:\n', pprint.pformat(api2._class_api))
    print('api2 dict api2._instance_api:\n', pprint.pformat(api2._instance_api))
    print('api2 api_has over:api', api2('libs.api:has')('a.over:api'))
    print('api2 api_has over:api', api2('libs.api:has')('a.test:over'))
    print('api2 called test:api', api2('a.test:api')('success'))
    print('api2 called test:over', api2('a.test:over')('success'))
    print('api2 overloading over.api')
    api2('libs.api:add')('a.over', 'api', overloadtestapi2, overload=True)
    print('api2 dict api._instance_api:\n', pprint.pformat(api2._instance_api))
    print('api2 called over:api', api2('a.over:api')('success'))
    print('api2 overloading test.over')
    api2('libs.api:add')('a.test', 'over', overloadtestapi2, overload=True)
    print('api2 dict api2:api:\n', pprint.pformat(api2._class_api))
    print('api2 dict api2:overloadapi:\n', pprint.pformat(api2._instance_api))
    print('api2 called a.test:over', api2('a.test:over')('success'))
    print('api2 called a.test:api', api2('a.test:api')('success'))
    print('api2 api_has a.test:three', api2('libs.api:has')('a.test.three'))
    try:
        print('api2 called a.test:three', api2('a.test:three')('success'))
    except AttributeError:
        print('a.test:three was not in the api')
    try:
        print("doesn't exist", api2('a.test:four')('success'))
    except AttributeError:
        print('a.test:four was not in the api')

if __name__ == '__main__':
    test()
