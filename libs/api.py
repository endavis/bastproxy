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

However, some api functions will need to be put in the instance api.
This has been used for the api functions in the API since those apis need
to check the instance api for the api there were invoked against.

class apis are in the class variable "_class_api"
instance apis are in the instance variable "_instance_api"

See the BasePlugin class
"""
# Standard Library
import inspect
import pprint
import typing
import types
from itertools import chain
import traceback
from pathlib import Path
from datetime import datetime
from functools import lru_cache
import logging
import contextlib

# Third Party

# Project

class AddAPI:
    def __init__(self, api: str, description='', instance=False):
        """
        kwargs:
            event_name: the event to register to
            priority: the priority to register the function with (Default: 50)
        """
        self.api_name = api
        self.description = description
        self.instance = instance

    def __call__(self, func):
        func.api = {'name': self.api_name,
                    'description':self.description,
                    'instance':self.instance,
                    'addedin':{}}

        return func

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
        lines.append(f'LEAVING STACK_DUMP: {id}' if id else '')
    try:
        from libs.records import LogRecord
        LogRecord(lines, level='warning', sources=[__name__])()
    except ImportError:
        print('\n'.join(lines))
        print()

@lru_cache(maxsize=128)
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
    argn: list[str] = [f"@Y{str(i)}@w" for i in sig.parameters if str(i) != 'self']
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
    ignore_list = ignore_owner_list or []

    caller_id = 'unknown'

    if frame := inspect.currentframe():
        while frame := frame.f_back:
            if 'self' in frame.f_locals and not isinstance(frame.f_locals['self'], APIItem):
                tcs = frame.f_locals['self']
                if (
                    hasattr(tcs, 'owner_id')
                    and tcs.owner_id
                    and tcs.owner_id not in ignore_list
                ):
                    caller_id = tcs.owner_id
                    break
                if (
                    hasattr(tcs, 'api')
                    and isinstance(tcs.api, API)
                    and tcs.api.owner_id
                    and tcs.api.owner_id not in ignore_list
                ):
                    caller_id = tcs.api.owner_id
                    break

    if caller_id == 'unknown':
        logger = logging.getLogger(__name__)
        logger.warn(f"Unknown caller_id for API call: {inspect.stack()[1][3]}")

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
    def __init__(self, full_api_name: str, tfunction: typing.Callable, owner_id: str | None,
                 description: list | str ='') -> None:
        """
        Initializes an APIItem object.

        Args:
            full_api_name (str): Full name of the API, e.g. 'plugins.core.log:reset
            tfunction (callable): The function to be wrapped.
            owner_id (str): Unique id of the owner calling the function.
        """
        self.full_api_name: str = full_api_name
        self.owner_id: str = owner_id or 'unknown'
        self.tfunction: typing.Callable = tfunction
        self.instance: bool = False
        self.overwritten_api: APIItem | None = None
        if not description:
            comments = inspect.getcomments(self.tfunction)
            comments = comments[2:].strip() if comments else ''
            description = comments.split('\n')
        elif isinstance(description, str):
            description = description.split('\n')

        self.description: list = description

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
        if stats := STATS_MANAGER.stats.get(self.full_api_name, None):
            return stats.count
        return 0

    @property
    def stats(self) -> APIStatItem | None:
        """
        Returns the stats for the API.

        Returns:
            dict: A dictionary of the stats for the API.
        """
        if stats := STATS_MANAGER.stats.get(self.full_api_name, None):
            return STATS_MANAGER.stats[self.full_api_name]
        else:
            return None

    def detail(self, show_function_code=False) -> list[str]:
        """
        create a detailed message for this item
        """
        description = []
        for i, line in enumerate(self.description):
            if not line:
                continue
            if i == 0:
                description.append(f"@C{'Description':<11}@w : {line}")
            else:
                description.append(f"{'':<13}   {line}")

        tmsg: list[str] = [
            f"@C{'API':<11}@w : {self.full_api_name}",
            *description,
            f"@C{'Function':<11}@w : {self.tfunction}",
            f"@C{'Owner':<11}@w : {self.owner_id}",
            f"@C{'Instance':<11}@w : {self.instance}",
            '',
        ]

        args = get_args(self.tfunction)

        location_split = self.full_api_name.split(':')
        name = location_split[0]
        command_name = ':'.join(location_split[1:])
        tdict = {'name':name, 'cmdname':command_name, 'api_location':self.full_api_name}

        tmsg.append(f"@G{self.full_api_name}@w({args})")
        if self.tfunction.__doc__:
            tmsg.append(self.tfunction.__doc__ % tdict)

        if sourcefile := inspect.getsourcefile(self.tfunction):
            tmsg.append('')
            tmsg.append(f"function defined in {sourcefile.replace(str(API.BASEPATH), '')}")

        if show_function_code:
            tmsg.append('')
            text_list, _ = inspect.getsourcelines(self.tfunction)
            tmsg.extend([i.replace('@', '@@').rstrip('\n') for i in text_list])

        if self.overwritten_api:
            tmsg.append('')
            tmsg.extend(('', "This API overwrote the following:"))
            tmsg.extend(f"    {line}" for line in self.overwritten_api.detail())

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
        # apis that have been add to this specific instance
        self._instance_api: dict[str, APIItem] = {}

        self.log_level: str = 'debug'

        # the format for the time
        self.time_format: str = '%a %b %d %Y %H:%M:%S %Z'

        # this is the parent of the API, couild be a plugin or a module
        self.owner_id: str = owner_id or 'unknown'

        # added functions
        self.add('libs.api', 'add', self.add, instance=True)
        self.add('libs.api', 'has', self._api_has, instance=True)
        self.add('libs.api', 'add.apis.for.object', self._api_add_apis_for_object, instance=True)
        self.add('libs.api', 'remove', self._api_remove, instance=True)
        self.add('libs.api', 'get.children', self._api_get_children, instance=True)
        self.add('libs.api', 'detail', self._api_detail, instance=True)
        self.add('libs.api', 'list', self._api_list, instance=True)
        self.add('libs.api', 'data.get', self._api_data_get, instance=True)
        self.add('libs.api', 'get.function.owner.plugin', self._api_get_function_owner_plugin, instance=True)
        self.add('libs.api', 'get.caller.owner', self._api_get_caller_owner, instance=True)
        self.add('libs.api', 'is.character.active', self._api_is_character_active_get, instance=True)
        self.add('libs.api', 'is.character.active:set', self._api_is_character_active_set, instance=True)

    # scan the object for api decorated functions
    def _api_add_apis_for_object(self, toplevel, item):
        """
        scan an object for api decorated functions
        """
        from libs.records import LogRecord
        LogRecord(f"_api_add_apis_for_object: {item} {toplevel}", level=self.log_level,
                    sources=[__name__, toplevel])()
        api_functions = self.get_api_functions_in_object(item)
        LogRecord(f"_api_add_apis_for_object: {toplevel}:{item} has {len(api_functions)} api functions", level=self.log_level,
                    sources=[__name__, toplevel])()
        if api_functions:
            names = [item.__name__ for item in api_functions]
            LogRecord(f"_api_add_apis_for_object {names = }", level=self.log_level,
                        sources=[__name__, toplevel])()
            for func in api_functions:
                if toplevel not in func.api['addedin']:
                    func.api['addedin'][toplevel] = []
                api_name = func.api['name'].format(**func.__self__.__dict__)
                if api_name not in func.api['addedin'][toplevel]:
                    LogRecord(f"Adding API {toplevel}:{api_name} with {func.__name__}", level=self.log_level,
                                sources=[__name__, toplevel])()
                    description = func.api['description'].format(**func.__self__.__dict__)
                    instance = func.api['instance']
                    if not instance:
                        func.api['addedin'][toplevel].append(api_name)
                    self(f"{__name__}:add")(toplevel, api_name, func, description=description,
                                            instance=instance)

    def get_api_functions_in_object(self, base, recurse=True):
        """
        recursively search for functions that are commands in a plugin instance
        and it's attributes
        """
        if not recurse and base == self:
            return []
        function_list = []
        for item in dir(base):
            if item.startswith('__'):
                continue
            try:
                item = getattr(base, item)
            except AttributeError:
                continue
            if isinstance(item, types.MethodType) and item.__name__.startswith('_api_') and hasattr(item, 'api'):
                function_list.append(item)
            elif recurse:
                function_list.extend(self.get_api_functions_in_object(item, recurse=False))

        return function_list

    def add_events(self) -> None:
        """
        add events for the api
        """
        self('plugins.core.events:add.event')('ev_libs.api_character_active', __name__,
                                            description='An event for when the character is active and ready for commands',
                                            arg_descriptions={'is_character_active':'The state of the is_character_active flag'})
        self('plugins.core.events:add.event')('ev_libs.api_character_inactive', __name__,
                                            description='An event for when the character is inactive and not ready for commands',
                                            arg_descriptions={'is_character_active':'The state of the is_character_active flag'})

    # get the firstactive flag
    def _api_is_character_active_get(self) -> bool:
        """
        returns the is_character_active flag
        """
        return self.is_character_active

    # set the is_character_active flag
    def _api_is_character_active_set(self, flag:bool) -> None:
        """
        set the is_character_active flag
        """
        self.__class__.is_character_active = flag

        if flag:
            self('plugins.core.events:raise.event')('ev_libs.api_character_active',
                                            args={'is_character_active':self.is_character_active},
                                            calledfrom='libs.api')
        else:
            self('plugins.core.events:raise.event')('ev_libs.api_character_inactive',
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
    def add(self, top_level_api: str, name: str, tfunction: typing.Callable, instance: bool = False, force: bool = False,
            description='') -> bool:
        """  add a function to the api
        @Ytop_level_api@w  = the toplevel that the api should be under
        @Yname@w  = the name of the api
        @Yfunction@w  = the function
        @Yinstance@w  = bool, True to add to instance api, false to add to class api

        the function is added as toplevel.name into the api

        if the api already exists, it is added to the instance api

        this function returns no values"""
        full_api_name: str = f'{top_level_api}:{name}'

        api_item = APIItem(full_api_name, tfunction, self.owner_id, description=description)

        if instance:
            return self._api_instance(api_item, force)

        if api_item.full_api_name in self._class_api:
            if api_item.tfunction == self._class_api[api_item.full_api_name].tfunction:
                return True
            if force:
                api_item.overwritten_api = self._class_api[full_api_name]
                self._class_api[full_api_name] = api_item
            else:
                try:
                    from libs.records import LogRecord
                    added_in = self._class_api[api_item.full_api_name].owner_id
                    LogRecord(f"libs.api:add - {api_item.full_api_name} already exists from plugin {added_in}",
                                level='error', sources=[__name__, self.owner_id])()
                except ImportError:
                    print(f"libs.api:add - {api_item.full_api_name} already exists")
                    return False
        else:
            self._class_api[api_item.full_api_name] = api_item

        return True

    # add a function to the instance api
    def _api_instance(self, api_item: APIItem, force: bool = False) -> bool:
        """  add a function to the instance api
        @Yapi_data@w  = the api data dictionary

        the function is added as api_data['full_api_name'] into the instance api

        this function returns True if added, False otherwise"""
        if api_item.full_api_name in self._instance_api:
            if api_item.tfunction == self._instance_api[api_item.full_api_name].tfunction:
                return True

            if force:
                api_item.overwritten_api = self._instance_api[api_item.full_api_name]
                api_item.instance = True
                self._instance_api[api_item.full_api_name] = api_item
            else:
                try:
                    from libs.records import LogRecord
                    LogRecord(f"libs.api:instance - {api_item.full_api_name} already exists from plugin: {api_item.owner_id}",
                            level='error', sources=[__name__, api_item.owner_id])()
                except ImportError:
                    print(f"libs.api:instance - {api_item.full_api_name} already exists")

                return False

        else:
            api_item.instance = True
            self._instance_api[api_item.full_api_name] = api_item

        return True

    # find the caller of this api
    def _api_get_caller_owner(self, ignore_owner_list: list[str] | None=None) -> str:
        """  get the plugin on the top of the frame stack
        @Yignore_plugin_list@w  = ignore the plugins (by plugin_id) in this list if they are on the stack

        check to see if the caller is a plugin, if so return the plugin id

        this is so plugins can figure out who gave them data and keep up with it.

        it will return the first plugin found when going through the stack
            it checks for a BasePlugin instance of self
            if it doesn't find that, it checks for an attribute of plugin

        returns the plugin_id of the plugin on the stack"""
        return get_caller_owner_id(ignore_owner_list)

    @lru_cache(maxsize=128)
    # get the plugin_id of the plugin that owns the function
    def _api_get_function_owner_plugin(self, function: typing.Callable) -> str:
        """  get the plugin_id of the plugin that owns the function
        @Yfunction@w  = the function

        this function returns the plugin_id of the plugin that owns the function"""
        plugin_id = 'unknown'
        with contextlib.suppress(AttributeError):
            plugin_id = function.__self__.plugin_id
        return plugin_id

    # remove a toplevel api
    def _api_remove(self, top_level_api: str) -> None:
        """  remove a toplevel api
        @Ytop_level_api@w  = the toplevel of the api to remove

        this function returns no values"""
        api_toplevel = f"{top_level_api}:"

        tkeys = sorted(self._class_api.keys())
        for i in tkeys:
            if i.startswith(api_toplevel):
                del self._class_api[i]

        tkeys = sorted(self._instance_api.keys())
        for i in tkeys:
            if i.startswith(api_toplevel):
                del self._instance_api[i]

    def get(self, api_location: str, get_class: bool = False) -> typing.Callable:
        """
        get an api function

        get_class = get the class instance
        """
        # check overloaded api
        if (
            not get_class
            and api_location in self._instance_api
            and self._instance_api[api_location]
        ):
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
        if parent_api[-1] != ':':
            parent_api += ':'

        tkeys = sorted(self._class_api.keys())
        api_list: list[str] = [
            full_api_name[len(parent_api) :]
            for full_api_name in tkeys
            if full_api_name.startswith(parent_api)
        ]
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
            API_item = self.get(api_location)
        except AttributeError:
            return False

        if not API_item:
            return False

        # return False for apis in plugins that have not been instantiated
        if (self('libs.pluginloader:is.plugin.id')(API_item.owner_id) and
             not API_item.tfunction.__self__.is_instantiated_f):
                return False

        return True

    # get the details for an api function
    def _api_detail(self, api_location: str, stats_by_plugin: bool = False, stats_by_caller: str | None = None,
                    show_function_code: bool = False) -> list[str]:     # pylint: disable=too-many-locals,too-many-branches
        # parsing a function declaration and figuring out where the function
        # resides is intensive, so disabling pylint warning
        """
        return the detail of an api function
        """
        tmsg: list[str] = []
        api_class = None
        api_instance = None

        if ':' not in api_location:
            tmsg.append(f"{api_location} is not a : api format")
            return tmsg

        if api_location:
            with contextlib.suppress(KeyError):
                api_class = self._class_api[api_location]

            with contextlib.suppress(KeyError):
                api_instance = self._instance_api[api_location]

            if not api_class and not api_instance:
                tmsg.append(f"{api_location} is not in the api")
                return tmsg

            if api_class:
                tmsg.extend(('Class API', '============'))
                tmsg.extend(api_class.detail(show_function_code=show_function_code))

            if api_instance:
                tmsg.extend(('Instance API', '============'))
                tmsg.extend(api_instance.detail(show_function_code=show_function_code))

            if stats_by_plugin or stats_by_caller:
                api_data = self._api_data_get(api_location)

                if api_data and api_data.stats:
                    if stats_by_plugin:
                        tmsg.append('')
                        tmsg.append(self('plugins.core.utils:center.colored.string')('Stats', '-', 70, '@B'))
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
                        tmsg.append(self('plugins.core.utils:center.colored.string')(f"Stats for {stats_by_caller}", '-', 70, '@B'))
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
        api_list: list[str] = [
            i for i in self._class_api if i.startswith(top_level_api)
        ]
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

        return sorted(set(api_list))

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
            toplevel, _ = i.split(':', 1)
            if toplevel not in top_levels:
                if top_levels:
                    tmsg.append('@B' + '-' * 50 + '@w')
                top_levels.append(toplevel)
                tmsg.extend((f"@G{toplevel:<10}@w", '@B' + '-' * 50 + '@w'))

            if api_data := self._api_data_get(i):
                tmsg.extend(
                    (
                        f"   @C{i:<60}@w : called {api_data.count} times @w",
                        f"        {api_data.description[0]}@w",
                    )
                )
        return tmsg

def test():
    """
    do some testing for the api
    """
    # some generic description
    def testapi(msg):
        """
        a test class api
        """
        return f'{msg} (class)'

    def instancetestapi(msg):
        """
        a test instance api
        """
        return f'{msg} (instance)'

    def instancetestapi2(msg):
        """
        a 1nd test instance api
        """
        return f'{msg} (instance)'



    print('-' * 80)
    api = API()
    print('adding a.test:api')
    api('libs.api:add')('a.test', 'api', testapi)
    print('adding a.test:instance')
    api('libs.api:add')('a.test', 'instance', testapi)
    print('adding a.test:some:api')
    api('libs.api:add')('a.test', 'some:api', testapi)
    print('called api a.test:api', api('a.test:api')('success'))
    print('called api a.test:instance', api('a.test:instance')('success'))
    print('called api a.test:some.api', api('a.test:some.api')('success'))
    print('dict api._class_api:\n', pprint.pformat(api._class_api))
    print('dict api._instance_api:\n', pprint.pformat(api._instance_api))
    print('adding a.instance.api in instance api')
    api('libs.api:add')('a.instance', 'api', instancetestapi, instance=True)
    print('adding a.test.instance in instance api')
    api('libs.api:add')('a.test', 'instance', instancetestapi, instance=True)
    print('dict api._instance_api:\n', pprint.pformat(api._instance_api))
    print('called api a.instance:api', api('a.instance:api')('success'))
    print('called api a.test:instance', api('a.test:instance')('success'))
    print('called api a.test:api', api('a.test:api')('success'))
    print('api.has a.test:instance', api('libs.api:has')('a.test:instance'))
    print('api.has a.test:instance2', api('libs.api:has')('a.test:instance2'))
    print('api.has a.instance:api', api('libs.api:has')('a.instance:api'))
    print('api.has a.test:some.api', api('libs.api:has')('a.test:some.api'))
    print('dict api._class_api:\n', pprint.pformat(api._class_api))
    print('dict api._instance_api:\n', pprint.pformat(api._instance_api))
    print('\n'.join(api('libs.api:list')(top_level_api="test")))
    print('--------------------')
    print('\n'.join(api('libs.api:list')()))
    print('--------------------')
    print('\n'.join(api('libs.api:detail')('a.test:instance')))
    print('--------------------')


    print('-' * 80)
    api2 = API()
    print('api: ', api)
    print('api2: ', api2)
    print('dict api._class_api:\n', pprint.pformat(api._class_api))
    print('dict api._instance_api:\n', pprint.pformat(api._instance_api))
    print('api2 dict api2.api:\n', pprint.pformat(api2._class_api))
    print('api2 dict api2._instance_api:\n', pprint.pformat(api2._instance_api))
    print('api2 api_has a.instance:api', api2('libs.api:has')('a.instance:api'))
    print('api2 api_has a.instance:api', api2('libs.api:has')('a.test:instance'))
    print('api2 called a.test:api', api2('a.test:api')('success'))
    print('api2 called a.test:instance', api2('a.test:instance')('success'))
    print('api2 adding a.instance.api in instance api')
    api2('libs.api:add')('a.instance', 'api', instancetestapi2, instance=True)
    print('api2 dict api._instance_api:\n', pprint.pformat(api2._instance_api))
    print('api2 called a.instance:api', api2('a.instance:api')('success'))
    print('api2 adding a.test.instance in instance api')
    api2('libs.api:add')('a.test', 'instance', instancetestapi2, instance=True)
    print('api2 dict api2:class api:\n', pprint.pformat(api2._class_api))
    print('api2 dict api2:instance api:\n', pprint.pformat(api2._instance_api))
    print('api2 called a.test:instance', api2('a.test:instance')('success'))
    print('api2 called a.test:api', api2('a.test:api')('success'))
    print('api2 api_has a.test:three', api2('libs.api:has')('a.test:three'))
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
