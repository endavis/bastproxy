# Project: bastproxy
# Filename: libs/api/_api.py
#
# File Description: create an api for use by plugins and modules
#
# By: Bast
"""Module for creating an API for use by plugins and modules.

This module provides the `API` class, which allows for the creation and management
of an API that can be used by plugins and modules. It includes methods for adding,
removing, and querying API functions, as well as tracking API usage statistics.

Key Components:
    - API: A class that provides an API for plugins and modules.
    - Methods for adding, removing, and querying API functions.
    - Utility methods for handling API function calls and tracking statistics.

Features:
    - Dynamic addition and removal of API functions.
    - Management of instance-specific and class-wide API functions.
    - Tracking and logging of API function calls and usage statistics.
    - Support for events related to the API state.

Usage:
    - Instantiate the `API` class to create an API object.
    - Use the `add` method to add functions to the API.
    - Query the API using the `get` and `has` methods.
    - Remove API functions using the `remove` method.
    - Track API usage statistics and details using provided methods.

Classes:
    - `API`: Represents a class that provides an API for plugins and modules.

"""

# Standard Library
import contextlib
import pprint
import types
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

from ._apiitem import APIItem

# Third Party
# Project
from ._apistats import APIStatItem
from ._functools import get_caller_owner_id, stackdump

APILOCATION = "libs.api"


class API:  # sourcery skip: upper-camel-case-classes
    """Provide an API for plugins and modules.

    This class allows for the creation and management of an API that can be used
    by plugins and modules. It includes methods for adding, removing, and querying
    API functions, as well as tracking API usage statistics.

    """

    # where the main api resides
    _class_api: ClassVar[dict[str, APIItem]] = {}

    # stats for the api
    stats: ClassVar[dict[str, APIStatItem]] = {}

    # the basepath that the proxy was run from, will be dynamically set in
    # bastproxy.py
    BASEPATH: Path = Path()
    BASEDATAPATH: Path = Path()
    BASEDATAPLUGINPATH: Path = Path()
    BASEDATALOGPATH: Path = Path()
    BASEPLUGINPATH: Path = Path()

    LOG_IN_UTC_TZ: bool = True

    # a flag to show that bastproxy is starting up
    startup: bool = False

    # a flag to suppress console output (logs still go to file)
    quiet_mode: bool = False

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

    def __init__(self, owner_id: str | None = None) -> None:
        """Initialize the API instance.

        This method initializes the API instance by setting up instance-specific
        attributes and adding default API callables to the instance.

        Args:
            owner_id: The identifier of the owner of this API instance.

        Returns:
            None

        Raises:
            None

        """
        # apis that have been add to this specific instance
        self._instance_api: dict[str, APIItem] = {}

        self.log_level: str = "debug"

        # the format for the time
        self.time_format: str = "%a %b %d %Y %H:%M:%S %Z"

        # this is the parent of the API, couild be a plugin or a module
        self.owner_id: str = owner_id or "unknown"

        # added functions
        self.add(
            APILOCATION,
            "add",
            self.add,
            instance=True,
            description="add a function to the api",
        )
        self.add(
            APILOCATION,
            "has",
            self._api_has,
            instance=True,
            description="check to see if something exists in the api",
        )
        self.add(
            APILOCATION,
            "add.apis.for.object",
            self._api_add_apis_for_object,
            instance=True,
            description="add apis for an object",
        )
        self.add(
            APILOCATION,
            "remove",
            self._api_remove,
            instance=True,
            description="remove a toplevel api",
        )
        self.add(
            APILOCATION,
            "get.children",
            self._api_get_children,
            instance=True,
            description="return a list of apis in a toplevel api",
        )
        self.add(
            APILOCATION,
            "detail",
            self._api_detail,
            instance=True,
            description="return the detail of an api function",
        )
        self.add(
            APILOCATION,
            "list",
            self._api_list,
            instance=True,
            description="return a formatted list of functions in an api",
        )
        self.add(
            APILOCATION,
            "list.data",
            self._api_list_data,
            instance=True,
            description="return a dict of api data",
        )
        self.add(
            APILOCATION,
            "data.get",
            self._api_data_get,
            instance=True,
            description="return the data for an api",
        )
        self.add(
            APILOCATION,
            "get.function.owner.plugin",
            self._api_get_function_owner_plugin,
            instance=True,
            description="get the plugin_id of the plugin that owns the function",
        )
        self.add(
            APILOCATION,
            "get.caller.owner",
            self._api_get_caller_owner,
            instance=True,
            description="get the plugin on the top of the frame stack",
        )
        self.add(
            APILOCATION,
            "is.character.active",
            self._api_is_character_active_get,
            instance=True,
            description="returns the is_character_active flag",
        )
        self.add(
            APILOCATION,
            "is.character.active:set",
            self._api_is_character_active_set,
            instance=True,
            description="set the is_character_active flag",
        )
        self.add(
            APILOCATION,
            "stackdump",
            stackdump,
            instance=True,
            description="return a stackdump",
        )

    def _api_add_apis_for_object(self, toplevel, item) -> None:
        """Add APIs for an object to a top-level API.

        This method adds all API callables found in the given object to the specified
        top-level API. It logs the addition of each API callable and ensures that
        callables are not added multiple times.

        Args:
            toplevel: The top-level API to which the callables should be added.
            item: The object containing the API callable to add.

        Returns:
            None

        Raises:
            None

        """
        from bastproxy.libs.records import LogRecord

        if isinstance(toplevel, str):
            package_root = self.owner_id.split(".")[0] if self.owner_id else ""
            if package_root == "bastproxy":
                prefix = f"{package_root}."
                if toplevel.startswith(prefix):
                    toplevel = toplevel.removeprefix(prefix)

        LogRecord(
            f"_api_add_apis_for_object: {item} {toplevel}",
            level=self.log_level,
            sources=[__name__, toplevel],
        )()
        api_functions = self.get_api_functions_in_object(item)
        LogRecord(
            f"_api_add_apis_for_object: {toplevel}:{item} has {len(api_functions)} api functions",
            level=self.log_level,
            sources=[__name__, toplevel],
        )()
        if api_functions:
            names = [item.__name__ for item in api_functions]
            LogRecord(
                f"_api_add_apis_for_object {names = }",
                level=self.log_level,
                sources=[__name__, toplevel],
            )()
            for func in api_functions:
                if toplevel not in func.api["addedin"]:  # type: ignore
                    func.api["addedin"][toplevel] = []  # type: ignore
                api_name = func.api["name"].format(**func.__self__.__dict__)  # type: ignore
                if api_name not in func.api["addedin"][toplevel]:  # type: ignore
                    LogRecord(
                        f"Adding API {toplevel}:{api_name} with {func.__name__}",
                        level=self.log_level,
                        sources=[__name__, toplevel],
                    )()
                    description = func.api["description"].format(  # type: ignore
                        **func.__self__.__dict__
                    )
                    instance = func.api["instance"]  # type: ignore
                    if not instance:
                        func.api["addedin"][toplevel].append(api_name)  # type: ignore
                    self(f"{APILOCATION}:add")(
                        toplevel,
                        api_name,
                        func,
                        description=description,
                        instance=instance,
                    )
                else:
                    LogRecord(
                        f"API {toplevel}:{api_name} already added",
                        level=self.log_level,
                        sources=[__name__, toplevel],
                    )()

    def get_api_functions_in_object(
        self, base: Any, recurse: bool = True
    ) -> list[types.MethodType]:
        """Get API functions in an object.

        This method retrieves all API callables found in the given object. It can
        optionally recurse into nested objects to find additional API callables.

        Args:
            base: The object to search for API callables.
            recurse: Whether to recurse into nested objects.

        Returns:
            A list of API callables found in the object.

        Raises:
            None

        """
        if not recurse and base == self:
            return []
        functions: list = []
        for item in dir(base):
            if item.startswith("__"):
                continue
            try:
                attr = getattr(base, item)
            except AttributeError:
                continue
            if (
                isinstance(attr, types.MethodType)
                and attr.__name__.startswith("_api_")
                and hasattr(attr, "api")
            ):
                functions.append(attr)
            elif recurse:
                functions.extend(self.get_api_functions_in_object(attr, recurse=False))

        return functions

    def add_events(self) -> None:
        """Add events related to the character's active state.

        This method adds event to the API that are related to the character's
        active state. These events can be used to notify other parts of the
        system when the character becomes active or inactive.

        Args:
            None

        Returns:
            None

        Raises:
            None

        """
        self("plugins.core.events:add.event")(
            "ev_libs.api_character_active",
            APILOCATION,
            description=("An event for when the character is active and ready for commands"),
            arg_descriptions={"is_character_active": "The state of the is_character_active flag"},
        )
        self("plugins.core.events:add.event")(
            "ev_libs.api_character_inactive",
            APILOCATION,
            description=("An event for when the character is inactive and not ready for commands"),
            arg_descriptions={"is_character_active": "The state of the is_character_active flag"},
        )

    def _api_is_character_active_get(self) -> bool:
        """Return the is_character_active flag.

        This method returns the current state of the is_character_active flag,
        indicating whether the character is active and ready for commands.

        Args:
            None

        Returns:
            The state of the is_character_active flag.

        Raises:
            None

        """
        return self.is_character_active

    def _api_is_character_active_set(self, flag: bool) -> None:
        """Set the is_character_active flag.

        This method sets the is_character_active flag to the given value and raises
        events to notify other parts of the system about the change in the character's
        active state.

        Args:
            flag: The new state of the is_character_active flag.

        Returns:
            None

        Raises:
            None

        """
        self.__class__.is_character_active = flag

        if flag:
            self("plugins.core.events:raise.event")(
                "ev_libs.api_character_active",
                event_args={"is_character_active": self.is_character_active},
                calledfrom=APILOCATION,
            )
        else:
            self("plugins.core.events:raise.event")(
                "ev_libs.api_character_inactive",
                event_args={"is_character_active": self.is_character_active},
                calledfrom=APILOCATION,
            )

    def _api_data_get(self, api_name: str, base: bool = False) -> APIItem | None:
        """Return the data for an API.

        This method retrieves the data associated with the specified API name. It
        checks both the instance-specific and class-wide APIs to find the requested
        data.

        Args:
            api_name: The name of the API to retrieve data for.
            base: Whether to retrieve data from the base class API.

        Returns:
            The APIItem associated with the specified API name, or None if not found.

        Raises:
            None

        """
        if api_name in self._instance_api and not base:
            return self._instance_api[api_name]
        if api_name in self._class_api:
            return self._class_api[api_name]

        return None

    def add(
        self,
        top_level_api: str,
        name: str,
        tfunction: Callable,
        instance: bool = False,
        force: bool = False,
        description: str = "",
    ) -> bool:
        """Add a function to the API.

        This method adds a callable to the API, either to the instance-specific API
        or the class-wide API. It ensures that callables are not added multiple times
        unless forced.

        Args:
            top_level_api: The top-level API to which the callable should be added.
            name: The name of the callable to add.
            tfunction: The callable to add to the API.
            instance: Whether to add the callable to the instance-specific API.
            force: Whether to force the addition of the callable, overwriting existing
                callables if necessary.
            description: A description of the callable being added.

        Returns:
            True if the callable was added successfully, False otherwise.

        Raises:
            None

        """
        full_api_name: str = f"{top_level_api}:{name}"

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
                    from bastproxy.libs.records import LogRecord

                    added_in = self._class_api[api_item.full_api_name].owner_id
                    LogRecord(
                        f"libs.api:add - {api_item.full_api_name} already exists from "
                        f"plugin {added_in}",
                        level="error",
                        sources=[__name__, self.owner_id],
                    )()
                except ImportError:
                    print(f"libs.api:add - {api_item.full_api_name} already exists")
                    return False
        else:
            self._class_api[api_item.full_api_name] = api_item

        return True

    def _api_instance(self, api_item: APIItem, force: bool = False) -> bool:
        """Add a callable to the instance-specific API.

        This method adds an APIItem to the instance-specific API. It ensures that
        the callable represented by the APIITem is not added multiple times unless
        forced.

        Args:
            api_item: The APIItem representing the callable to add.
            force: Whether to force the addition of the callable, overwriting
            existing callables if necessary.

        Returns:
            True if the callable was added successfully, False otherwise.

        Raises:
            None

        """
        if api_item.full_api_name in self._instance_api:
            if api_item.tfunction == self._instance_api[api_item.full_api_name].tfunction:
                return True

            if force:
                api_item.overwritten_api = self._instance_api[api_item.full_api_name]
                api_item.instance = True
                self._instance_api[api_item.full_api_name] = api_item
            else:
                try:
                    from bastproxy.libs.records import LogRecord

                    LogRecord(
                        f"libs.api:instance - {api_item.full_api_name} already exists "
                        f"from plugin: {api_item.owner_id}",
                        level="error",
                        sources=[__name__, api_item.owner_id],
                    )()
                except ImportError:
                    print(f"libs.api:instance - {api_item.full_api_name} already exists")

                return False

        else:
            api_item.instance = True
            self._instance_api[api_item.full_api_name] = api_item

        return True

    # find the caller of this api
    def _api_get_caller_owner(self, ignore_owner_list: list[str] | None = None) -> str:
        """Get the plugin on the top of the frame stack.

        This method retrieves the owner identifier of the caller at the top of the
        frame stack, ignoring any owners specified in the ignore_owner_list.

        Args:
            ignore_owner_list: A list of owner identifiers to ignore.

        Returns:
            The owner identifier of the caller at the top of the frame stack.

        Raises:
            None

        """
        return get_caller_owner_id(ignore_owner_list)

    @lru_cache(maxsize=128)
    def _api_get_function_owner_plugin(self, tcallable: Callable) -> str:
        """Get the plugin ID of the plugin that owns the function.

        This method retrieves the plugin identifier of the plugin that owns the
        specified callable. It suppresses any AttributeError that might occur
        during the retrieval process.

        Args:
            tcallable: The callable whose owning plugin's ID is to be retrieved.

        Returns:
            The plugin ID of the plugin that owns the callable.

        Raises:
            None

        """
        plugin_id = "unknown"
        with contextlib.suppress(AttributeError):
            plugin_id = tcallable.__self__.plugin_id  # type: ignore
        return plugin_id

    def _api_remove(self, top_level_api: str) -> None:
        """Remove a top-level API.

        This method removes all API callables associated with the specified top-level
        API from both the instance-specific and class-wide APIs. It ensures that
        callables are properly cleaned up and logs the removal process.

        Args:
            top_level_api: The top-level API to remove.

        Returns:
            None

        Raises:
            None

        """
        from bastproxy.libs.records import LogRecord

        LogRecord(
            f"libs.api:remove - {top_level_api}",
            level="debug",
            sources=[__name__, top_level_api],
        )()
        api_toplevel = f"{top_level_api}:"

        class_keys = [item for item in self._class_api if item.startswith(api_toplevel)]
        LogRecord(
            f"libs.api:remove class api - {class_keys =}",
            level="debug",
            sources=[__name__, top_level_api],
        )()
        for i in class_keys:
            func = self._class_api[i].tfunction
            api_name = func.api["name"].format(**func.__self__.__dict__)  # type: ignore
            # clean up decorated functions so that subclasses APIs can be reloaded
            # this affects apis that are part of a subclass, such as the baseplugin APIs
            self._class_api[i].tfunction.api["addedin"][top_level_api].remove(api_name)  # type: ignore
            del self._class_api[i]

        instance_keys = [item for item in self._instance_api if item.startswith(api_toplevel)]
        LogRecord(
            f"libs.api:remove instance api - {instance_keys =}",
            level="debug",
            sources=[__name__, top_level_api],
        )()
        for i in instance_keys:
            func = self._instance_api[i].tfunction
            api_name = func.api["name"].format(**func.__self__.__dict__)  # type: ignore
            # clean up decorated functions so that subclasses APIs can be reloaded
            # this affects apis that are part of a subclass, such as the baseplugin APIs
            self._instance_api[i].tfunction.api["addedin"][top_level_api].remove(  # type: ignore
                api_name
            )
            del self._instance_api[i]

    def get(self, api_location: str, get_class: bool = False) -> APIItem:
        """Get a callable from the API.

        This method retrieves a callable from the API based on the specified
        API location. It checks both the instance-specific and class-wide APIs
        to find the requested callable.

        Args:
            api_location: The location of the API to retrieve.
            get_class: Whether to retrieve the callable from the class-wide API.

        Returns:
            The callable associated with the specified API location.

        Raises:
            AttributeError: If the API location is not found in the API.

        """
        if "." in api_location:
            package_root = (self.owner_id or "").split(".")[0]
            prefix = f"{package_root}."
            if package_root == "bastproxy" and api_location.startswith(prefix):
                api_location = api_location.removeprefix(prefix)

        # check overloaded api
        if (
            not get_class
            and api_location in self._instance_api
            and self._instance_api[api_location]
        ):
            return self._instance_api[api_location]

        # check api
        if self._class_api.get(api_location):
            return self._class_api[api_location]

        msg = f"{self.owner_id} : {api_location} is not in the api"
        raise AttributeError(msg)

    __call__ = get

    def _api_get_children(self, parent_api: str) -> list[str]:
        """Return a list of APIs in a top-level API.

        This method retrieves a list of all API callables that are part of the
        specified top-level API. It checks both the instance-specific and class-wide
        APIs to find the relevant callables.

        Args:
            parent_api: The top-level API to search for child APIs.

        Returns:
            A list of API names that are part of the specified top-level API.

        Raises:
            None

        """
        if parent_api[-1] != ":":
            parent_api += ":"

        tkeys = sorted(self._class_api.keys())
        api_data: list[str] = [
            full_api_name[len(parent_api) :]
            for full_api_name in tkeys
            if full_api_name.startswith(parent_api)
        ]
        tkeys = sorted(self._instance_api.keys())
        for full_api_name in tkeys:
            if full_api_name.startswith(parent_api):
                api_data.append(full_api_name[len(parent_api) :])

        return list(set(api_data))

    def _api_has(self, api_location: str) -> bool:
        """Check if an API location exists.

        This method checks whether the specified API location exists in the API.
        It verifies the presence of the API location in both the instance-specific
        and class-wide APIs.

        Args:
            api_location: The location of the API to check.

        Returns:
            True if the API location exists, False otherwise.

        Raises:
            None

        """
        try:
            API_item = self.get(api_location)
        except AttributeError:
            return False

        if not API_item:
            return False

        # return False for apis in plugins that have not been instantiated
        return bool(
            not self("libs.plugins.loader:is.plugin.id")(API_item.owner_id)
            or self("libs.plugins.loader:is.plugin.instantiated")(API_item.owner_id)
        )

    def _api_detail(
        self,
        api_location: str,
        stats_by_plugin: bool = False,
        stats_by_caller: str = "",
        show_function_code: bool = False,
    ) -> list[str]:
        """Return the detail of an API item.

        This method retrieves detailed information about the specified API item,
        including its class and instance details, and optionally its usage statistics
        and function code.

        Args:
            api_location: The location of the API Item to retrieve details for.
            stats_by_plugin: Whether to include usage statistics by plugin.
            stats_by_caller: Whether to include usage statistics by caller.
            show_function_code: Whether to include the function code in the details.

        Returns:
            A list of strings containing the detailed information about the API item.

        Raises:
            None

        """
        tmsg: list[str] = []
        api_class = None
        api_instance = None

        if ":" not in api_location:
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
                tmsg.extend(("Class API", "============"))
                tmsg.extend(api_class.detail(show_function_code=show_function_code))

            if api_instance:
                tmsg.extend(("Instance API", "============"))
                tmsg.extend(api_instance.detail(show_function_code=show_function_code))

            if stats_by_plugin or stats_by_caller:
                tmsg.extend(self.format_stats(api_location, stats_by_plugin, stats_by_caller))

        else:
            tmsg.append(f"{api_location} is not in the api")

        return tmsg

    def format_stats(
        self, api_location: str, stats_by_plugin: bool, stats_by_caller: str
    ) -> list[str]:
        """Format the statistics for an API location.

        This method formats the statistics for the specified API location, including
        overall statistics and statistics for specific callers if requested.

        Args:
            api_location: The location of the API to format statistics for.
            stats_by_plugin: Whether to include usage statistics by plugin.
            stats_by_caller: The caller identifier to include usage statistics for.

        Returns:
            A list of strings containing the formatted statistics.

        Raises:
            None

        """
        api_data = self._api_data_get(api_location)

        if not api_data or not api_data.stats:
            return []

        tmsg = []

        if stats_by_plugin:
            self._stats_overall(tmsg, api_data)
        if stats_by_caller:
            self._stats_for_specific_caller(tmsg, stats_by_caller, api_data)
            # tmsg.extend(
            #     f"{i or 'unknown':<65}: {api_data.stats.detailed_calls[i]}"
            #     for i in stats_keys
            # )
        return tmsg

    def _stats_for_specific_caller(
        self, tmsg: list[str], stats_by_caller: str, api_data: APIItem
    ) -> None:
        """Format statistics for a specific caller.

        This method formats the statistics for a specific caller, including the
        number of times the caller has invoked the API. It generates a table
        representation of the statistics for easy viewing.

        Args:
            tmsg: The list to which the formatted statistics will be appended.
            stats_by_caller: The caller identifier to include usage statistics for.
            api_data: The API data containing the statistics.

        Returns:
            None

        Raises:
            None

        """
        stats_keys = [k for k in api_data.stats.detailed_calls if k.startswith(stats_by_caller)]
        stats_keys = sorted(stats_keys)
        stats_caller_data = [
            {"caller": i, "count": api_data.stats.detailed_calls[i]} for i in stats_keys
        ]
        stats_caller_columns = [
            {"name": "Caller", "key": "caller", "width": 20},
            {"name": "Count", "key": "count", "width": 11},
        ]
        tmsg.extend(
            [
                "",
                *self("plugins.core.utils:convert.data.to.output.table")(
                    f"Stats for {stats_by_caller} (Unique Callers: {len(stats_keys)})",
                    stats_caller_data,
                    stats_caller_columns,
                ),
            ]
        )

    def _stats_overall(self, tmsg: list[str], api_data: APIItem) -> None:
        """Format overall statistics for an API location.

        This method formats the overall statistics for the specified API location,
        including the total number of calls and a breakdown of calls by caller.
        It generates a table representation of the statistics for easy viewing.

        Args:
            tmsg: The list to which the formatted statistics will be appended.
            api_data: The API data containing the statistics.

        Returns:
            None

        Raises:
            None

        """
        stats_keys = api_data.stats.calls_by_caller.keys()
        stats_keys = sorted(stats_keys)
        stats_caller_data = [
            {"caller": i, "count": api_data.stats.calls_by_caller[i]} for i in stats_keys
        ]
        stats_caller_columns = [
            {"name": "Caller", "key": "caller", "width": 20},
            {"name": "Count", "key": "count", "width": 11},
        ]
        tmsg.extend(
            [
                "",
                *self("plugins.core.utils:convert.data.to.output.table")(
                    f"Callers (Total Calls {api_data.stats.count})",
                    stats_caller_data,
                    stats_caller_columns,
                ),
            ]
        )

    def get_top_level_api_list(self, top_level_api: str) -> list[str]:
        """Get a list of APIs in a top-level API.

        This method retrieves a list of all API callables that are part of the
        specified top-level API. It checks both the instance-specific and class-wide
        APIs to find the relevant callables.

        Args:
            top_level_api: The top-level API to search for child APIs.

        Returns:
            A list of API names that are part of the specified top-level API.

        Raises:
            None

        """
        api_data: list[str] = [i for i in self._class_api if i.startswith(top_level_api)]
        for i in self._instance_api:
            if i.startswith(top_level_api):
                api_data.append(i)

        return list(set(api_data))

    def get_full_api_list(self) -> list[str]:
        """Get a list of all APIs.

        This method retrieves a list of all API callables, including both
        instance-specific and class-wide APIs.

        Args:
            None

        Returns:
            A list of all API names.

        Raises:
            None

        """
        api_data: list[str] = []
        api_data.extend(self._class_api.keys())
        api_data.extend(self._instance_api.keys())

        return sorted(set(api_data))

    def _api_list_data(self, top_level_api: str = "") -> list[dict]:
        """Return a dict of API data.

        This method retrieves a dictionary containing data for all API callables,
        either for a specified top-level API or for all APIs if no top-level API
        is specified. The data includes the top-level API name, the API name,
        the full API name, the number of times the API has been called, and the
        description of the API.

        Args:
            top_level_api: The top-level API to retrieve data for.

        Returns:
            A list of dictionaries containing data for each API callable.

        Raises:
            None

        """
        all_api_data = []
        api_data = (
            self.get_top_level_api_list(top_level_api)
            if top_level_api
            else self.get_full_api_list()
        )
        for i in api_data:
            toplevel, api_name = i.split(":", 1)
            if api_data := self._api_data_get(i):
                all_api_data.append(
                    {
                        "toplevel": toplevel,
                        "name": api_name,
                        "full_api_name": i,
                        "called_count": api_data.count,
                        "description": " ".join(api_data.description),
                    }
                )

        all_api_data.sort(key=lambda x: x["full_api_name"])
        return all_api_data

    def _api_list(self, top_level_api: str = "") -> list[str]:
        """Return a formatted list of functions in an API.

        This method retrieves a list of all API callables, either for a specified
        top-level API or for all APIs if no top-level API is specified. The list
        includes the API name, the number of times the API has been called, and
        the description of the API.

        Args:
            top_level_api: The top-level API to retrieve functions for.

        Returns:
            A list of strings containing the formatted list of functions in the API.

        Raises:
            None

        """
        tmsg: list[str] = []
        api_data = (
            self.get_top_level_api_list(top_level_api)
            if top_level_api
            else self.get_full_api_list()
        )

        api_data.sort()

        top_levels: list[str] = []
        for i in api_data:
            toplevel, _ = i.split(":", 1)
            if toplevel not in top_levels:
                if top_levels:
                    tmsg.append("@B" + "-" * 50 + "@w")
                top_levels.append(toplevel)
                tmsg.extend((f"@G{toplevel:<10}@w", "@B" + "-" * 50 + "@w"))

            if api_data := self._api_data_get(i):
                tmsg.extend(
                    (
                        f"   @C{i:<60}@w : called {api_data.count} times @w",
                        f"        {api_data.description[0]}@w",
                    )
                )
        return tmsg


def test() -> None:  # sourcery skip: no-long-functions
    """Test the API class functionality.

    This function tests various functionalities of the API class, including adding,
    querying, and removing API callables, as well as checking the presence of API
    locations and retrieving detailed information about API items.

    Args:
        None

    Returns:
        None

    Raises:
        None

    """

    # some generic description
    def testapi(msg: str) -> str:
        """Test the class api."""
        return f"{msg} (class)"

    def instancetestapi(msg: str) -> str:
        """Test the instance api."""
        return f"{msg} (instance)"

    def instancetestapi2(msg: str) -> str:
        """TEst the instance api 2nd version."""
        return f"{msg} (instance (2))"

    print("-" * 80)
    api = API()
    print("adding a.test:api")
    api("libs.api:add")("a.test", "api", testapi)
    print("adding a.test:instance")
    api("libs.api:add")("a.test", "instance", testapi)
    print("adding a.test:some:api")
    api("libs.api:add")("a.test", "some:api", testapi)
    print("called api a.test:api", api("a.test:api")("success"))
    print("called api a.test:instance", api("a.test:instance")("success"))
    print("called api a.test:some.api", api("a.test:some.api")("success"))
    print("dict api._class_api:\n", pprint.pformat(api._class_api))
    print("dict api._instance_api:\n", pprint.pformat(api._instance_api))
    print("adding a.instance.api in instance api")
    api("libs.api:add")("a.instance", "api", instancetestapi, instance=True)
    print("adding a.test.instance in instance api")
    api("libs.api:add")("a.test", "instance", instancetestapi, instance=True)
    print("dict api._instance_api:\n", pprint.pformat(api._instance_api))
    print("called api a.instance:api", api("a.instance:api")("success"))
    print("called api a.test:instance", api("a.test:instance")("success"))
    print("called api a.test:api", api("a.test:api")("success"))
    print("api.has a.test:instance", api("libs.api:has")("a.test:instance"))
    print("api.has a.test:instance2", api("libs.api:has")("a.test:instance2"))
    print("api.has a.instance:api", api("libs.api:has")("a.instance:api"))
    print("api.has a.test:some.api", api("libs.api:has")("a.test:some.api"))
    print("dict api._class_api:\n", pprint.pformat(api._class_api))
    print("dict api._instance_api:\n", pprint.pformat(api._instance_api))
    print("\n".join(api("libs.api:list")(top_level_api="test")))
    print("--------------------")
    print("\n".join(api("libs.api:list")()))
    print("--------------------")
    print("\n".join(api("libs.api:detail")("a.test:instance")))
    print("--------------------")

    print("-" * 80)
    api2 = API()
    print("api: ", api)
    print("api2: ", api2)
    print("dict api._class_api:\n", pprint.pformat(api._class_api))
    print("dict api._instance_api:\n", pprint.pformat(api._instance_api))
    print("api2 dict api2.api:\n", pprint.pformat(api2._class_api))
    print("api2 dict api2._instance_api:\n", pprint.pformat(api2._instance_api))
    print("api2 api_has a.instance:api", api2("libs.api:has")("a.instance:api"))
    print("api2 api_has a.instance:api", api2("libs.api:has")("a.test:instance"))
    print("api2 called a.test:api", api2("a.test:api")("success"))
    print("api2 called a.test:instance", api2("a.test:instance")("success"))
    print("api2 adding a.instance.api in instance api")
    api2("libs.api:add")("a.instance", "api", instancetestapi2, instance=True)
    print("api2 dict api._instance_api:\n", pprint.pformat(api2._instance_api))
    print("api2 called a.instance:api", api2("a.instance:api")("success"))
    print("api2 adding a.test.instance in instance api")
    api2("libs.api:add")("a.test", "instance", instancetestapi2, instance=True)
    print("api2 dict api2:class api:\n", pprint.pformat(api2._class_api))
    print("api2 dict api2:instance api:\n", pprint.pformat(api2._instance_api))
    print("api2 called a.test:instance", api2("a.test:instance")("success"))
    print("api2 called a.test:api", api2("a.test:api")("success"))
    print("api2 api_has a.test:three", api2("libs.api:has")("a.test:three"))
    try:
        print("api2 called a.test:three", api2("a.test:three")("success"))
    except AttributeError:
        print("a.test:three was not in the api")
    try:
        print("doesn't exist", api2("a.test:four")("success"))
    except AttributeError:
        print("a.test:four was not in the api")


if __name__ == "__main__":
    test()
