# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/api/_api.py
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
import pprint
import typing
import types
from pathlib import Path
from datetime import datetime
from functools import lru_cache
import contextlib

# Third Party

# Project
from ._apistats import APIStatItem
from ._functools import stackdump
from ._apiitem import APIItem
from ._functools import get_caller_owner_id

APILOCATION = 'libs.api'

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
        self.add(APILOCATION, 'add', self.add, instance=True)
        self.add(APILOCATION, 'has', self._api_has, instance=True)
        self.add(APILOCATION, 'add.apis.for.object', self._api_add_apis_for_object, instance=True)
        self.add(APILOCATION, 'remove', self._api_remove, instance=True)
        self.add(APILOCATION, 'get.children', self._api_get_children, instance=True)
        self.add(APILOCATION, 'detail', self._api_detail, instance=True)
        self.add(APILOCATION, 'list', self._api_list, instance=True)
        self.add(APILOCATION, 'list.data', self._api_list_data, instance=True,
                 description='return a dict of api data')
        self.add(APILOCATION, 'data.get', self._api_data_get, instance=True)
        self.add(APILOCATION, 'get.function.owner.plugin', self._api_get_function_owner_plugin, instance=True)
        self.add(APILOCATION, 'get.caller.owner', self._api_get_caller_owner, instance=True)
        self.add(APILOCATION, 'is.character.active', self._api_is_character_active_get, instance=True)
        self.add(APILOCATION, 'is.character.active:set', self._api_is_character_active_set, instance=True)
        self.add(APILOCATION, 'stackdump', stackdump, instance=True)

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
                    self(f"{APILOCATION}:add")(toplevel, api_name, func, description=description,
                                            instance=instance)
                else:
                    LogRecord(f"API {toplevel}:{api_name} already added", level=self.log_level,
                                sources=[__name__, toplevel])()

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
        self('plugins.core.events:add.event')('ev_libs.api_character_active', APILOCATION,
                                            description='An event for when the character is active and ready for commands',
                                            arg_descriptions={'is_character_active':'The state of the is_character_active flag'})
        self('plugins.core.events:add.event')('ev_libs.api_character_inactive', APILOCATION,
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
                                            calledfrom=APILOCATION)
        else:
            self('plugins.core.events:raise.event')('ev_libs.api_character_inactive',
                                            args={'is_character_active':self.is_character_active},
                                            calledfrom=APILOCATION)

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
        from libs.records import LogRecord
        LogRecord(f"libs.api:remove - {top_level_api}",
                level='debug', sources=[__name__, top_level_api])()
        api_toplevel = f"{top_level_api}:"

        class_keys = [item for item in self._class_api.keys() if item.startswith(api_toplevel)]
        LogRecord(f"libs.api:remove class api - {class_keys =}",
                level='debug', sources=[__name__, top_level_api])()
        for i in class_keys:
            func = self._class_api[i].tfunction
            api_name = func.api['name'].format(**func.__self__.__dict__)
            # clean up decorated functions so that subclasses APIs can be reloaded
            # this affects apis that are part of a subclass, such as the baseplugin APIs
            self._class_api[i].tfunction.api['addedin'][top_level_api].remove(api_name)
            del self._class_api[i]

        instance_keys = [item for item in self._instance_api.keys() if item.startswith(api_toplevel)]
        LogRecord(f"libs.api:remove instance api - {instance_keys =}",
                level='debug', sources=[__name__, top_level_api])()
        for i in instance_keys:
            func = self._instance_api[i].tfunction
            api_name = func.api['name'].format(**func.__self__.__dict__)
            # clean up decorated functions so that subclasses APIs can be reloaded
            # this affects apis that are part of a subclass, such as the baseplugin APIs
            self._instance_api[i].tfunction.api['addedin'][top_level_api].remove(api_name)
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
        return bool(
            not self('libs.pluginloader:is.plugin.id')(API_item.owner_id)
            or API_item.tfunction.__self__.is_instantiated_f
        )

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

    def _api_list_data(self, top_level_api: str = '') -> list[dict]:
        """
        return a dict of api data
        """
        all_api_data = []
        api_list = self.get_top_level_api_list(top_level_api) if top_level_api else self.get_full_api_list()
        for i in api_list:
            toplevel, api_name = i.split(':', 1)
            if api_data := self._api_data_get(i):
                all_api_data.append({
                    'toplevel': toplevel,
                    'name': api_name,
                    'full_api_name': i,
                    'called_count': api_data.count,
                    'description': ' '.join(api_data.description),
                })

        all_api_data.sort(key=lambda x: x['full_api_name'])
        return all_api_data

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
