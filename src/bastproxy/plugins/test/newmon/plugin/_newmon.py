# Project: bastproxy
# Filename: plugins/core/async/_async.py
#
# File Description: a plugin to inspect async internals
#
# By: Bast

# Standard Library
import logging
import traceback
from typing import Any, NoReturn

from pydatatracker import add_to_ignore_in_stack

# import pprint
# 3rd Party
# Project
from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.core.commands import AddParser
from bastproxy.plugins.test.newmon.types.trackedrecord import TrackedRecord

add_to_ignore_in_stack(["in run_expression"])


def test_expression(expression, **locals):
    locals["new_record"]._tracking_debug("    Testing begin")
    locals["new_record"]._tracking_debug(f"      Expresion: {expression}")
    retval = None
    try:
        retval = eval(expression, globals(), locals)
    except Exception:
        [
            locals["new_record"]._tracking_debug(f"      {line}")
            for line in traceback.format_exc().splitlines()
        ]
    locals["new_record"]._tracking_debug("    Testing end")
    return retval


def run_expression(command: dict, logger_func=logging.info, description=""):
    """Executes commands defined in a structured format using `getattr`.

    Args:
        command (dict): A dictionary defining the operation and its arguments.
        logger_func (callable): A function to log messages.
        description (str): A description of the command.

    Returns:
        Any: The result of the command.

    Raises:
        ValueError: If required fields are missing or invalid.

    {"operation": "append", "target": "my_list", "args": [4]},
    {"target": "my_list", "args": [1, 99]},  # Missing 'operation'
    {"operation": "pop", "args": []},       # Missing 'target'
    {"operation": "remove", "target": "nonexistent_list", "args": [2]},  # Invalid 'target'

    """
    logger_func("#" * 80)

    def _missing_required_field(field: str) -> NoReturn:
        msg = f"Missing required field: '{field}'"
        raise ValueError(msg)

    if description:
        logger_func(f"  {description}")
        logger_func("")
    logger_func(f"  Testing begin: {command}")
    if "operation" not in command:
        _missing_required_field("operation")
    if "target" not in command:
        _missing_required_field("target")

    operation = command["operation"]
    target = command["target"]
    args: list[Any] = command.get("args", [])  # Optional args default to empty list

    # Fetch and execute the method dynamically
    method = getattr(target, operation, None)
    if not callable(method):
        msg = f"Operation '{operation}' not supported on the target object."
        raise TypeError(msg)

    try:
        result = method(*args)
    except Exception as e:
        logger_func(f"    Error executing command: {e}")
    else:
        logger_func(f"    Operation result: {result}")
        return result

    finally:
        logger_func("  Testing end.")
        logger_func("#" * 80)


class NewMonPlugin(BasePlugin):
    """a plugin to inspect records"""

    @AddParser(description="test new tracking records")
    def _command_rectest(self):
        """Test new record tracking"""
        new_record = TrackedRecord(owner_id="test record")

        new_record._tracking_debug_flag = True

        def observer_print(change_log_entry):
            new_record._tracking_debug("      ------------------------")
            for line in change_log_entry.format_detailed():
                new_record._tracking_debug(f"      {line}")
            new_record._tracking_debug("      ------------------------")

        new_record.tracking_add_observer(observer_print, priority=100)

        run_expression(
            {
                "operation": "tracking_add_attribute_to_monitor",
                "target": new_record,
                "args": ["tracked_attr"],
            },
            logger_func=new_record._tracking_debug,
            description="start tracking attribute tracked_attr",
        )

        run_expression(
            {
                "operation": "tracking_add_attribute_to_monitor",
                "target": new_record,
                "args": ["tracked_list"],
            },
            logger_func=new_record._tracking_debug,
            description="start tracking attribute tracked_list",
        )

        run_expression(
            {
                "operation": "tracking_add_attribute_to_monitor",
                "target": new_record,
                "args": ["tracked_dict"],
            },
            logger_func=new_record._tracking_debug,
            description="start tracking attribute tracked_dict",
        )

        # run_expression({"operation": "lock",
        #                 "target": new_record, "args": []},
        #                 logger_func=new_record._tracking_debug,
        #                 description="locking new_record")

        run_expression(
            {
                "operation": "__setattr__",
                "target": new_record,
                "args": ["tracked_attr", "changed string"],
            },
            logger_func=new_record._tracking_debug,
            description="setting tracked_attr to 'changed string'",
        )

        run_expression(
            {
                "operation": "__setattr__",
                "target": new_record,
                "args": ["tracked_attr", "changed string again"],
            },
            logger_func=new_record._tracking_debug,
            description="setting tracked_attr to 'changed string again'",
        )

        # run_expression({"operation": "lock",
        #                 "target": new_record, "args": ['tracked_attr]},
        #                 logger_func=new_record._tracking_debug,
        #                 description="locking new_record.tracked_attr")

        run_expression(
            {"operation": "lock", "target": new_record},
            logger_func=new_record._tracking_debug,
            description="locking new_record",
        )

        run_expression(
            {
                "operation": "__setattr__",
                "target": new_record,
                "args": ["tracked_attr", "should not show up"],
            },
            logger_func=new_record._tracking_debug,
            description="modifying locked attribute tracked_attr",
        )

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  modifying locked attribute tracked_attr")
        # test_expression("setattr(new_record, 'tracked_attr', 'should not show up')", new_record=new_record)
        # new_record._tracking_debug(f'  {new_record.tracked_attr = }') # type: ignore

        run_expression(
            {"operation": "unlock", "target": new_record},
            logger_func=new_record._tracking_debug,
            description="unlocking new_record",
        )

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  unlocking new_record")
        # new_record.unlock()

        new_record._tracking_debug_flag = False

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("unlocking attribute tracked_attr")
        # new_record._tracking_unlock_attribute('tracked_attr')

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  appending 'first item' to attribute tracked_list")
        # # new_record.tracked_list.append('first item')
        # test_expression("new_record.tracked_list.append('first item')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  appending "second_item" to attribute tracked_list')
        # # new_record.tracked_list.append('second item')
        # test_expression("new_record.tracked_list.append('second item')", new_record=new_record)
        # new_record._tracking_debug(f"{  new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  changing index 0 of attribute tracked_list to "changed first item"')
        # # new_record.tracked_list[0] = 'changed first item'
        # test_expression("new_record.tracked_list.__setitem__(0, 'changed first item')", new_record=new_record)
        # new_record._tracking_debug(f"{  new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  changing index 1 of attribute tracked_list to "changed second item"')
        # # new_record.tracked_list[1] = 'changed second item'
        # test_expression("new_record.tracked_list.__setitem__(1, 'changed second item')", new_record=new_record)
        # new_record._tracking_debug(f"{  new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  extending attribute tracked_list with ["third item", "fourth item"]')
        # # new_record.tracked_list.extend(['third item', 'fourth item'])
        # test_expression("new_record.tracked_list.extend(['third item', 'fourth item'])", new_record=new_record)
        # new_record._tracking_debug(f"{  new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  inserting "inserted item" at index 0 of attribute tracked_list')
        # # new_record.tracked_list.insert(0, 'inserted item')
        # test_expression("new_record.tracked_list.insert(0, 'inserted item')", new_record=new_record)
        # new_record._tracking_debug(f"{  new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  sorting attribute tracked_list')
        # # new_record.tracked_list.sort()
        # test_expression("new_record.tracked_list.sort()", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  reversing attribute tracked_list')
        # # new_record.tracked_list.reverse()
        # test_expression("new_record.tracked_list.reverse()", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  popping index -1 of attribute tracked_list')
        # # new_record.tracked_list.pop()
        # test_expression("new_record.tracked_list.pop()", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  popping index 1 of attribute tracked_list')
        # # new_record.tracked_list.pop(1)
        # test_expression("new_record.tracked_list.pop(1)", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  removing "changed first item" from attribute tracked_list')
        # # new_record.tracked_list.remove('changed second item')
        # test_expression("new_record.tracked_list.remove('changed second item')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  clearing attribute tracked_list')
        # # new_record.tracked_list.clear()
        # test_expression("new_record.tracked_list.clear()", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  locking attribute tracked_list')
        # new_record.tracked_list.lock() # type: ignore

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  appending "should not show up" to locked attribute tracked_list')
        # # new_record.tracked_list.append('should not show up')
        # test_expression("new_record.tracked_list.append('should not show up')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('unlocking attribute tracked_list')
        # new_record.tracked_list.unlock() # type: ignore
        # new_record._tracking_debug_flag = False

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  appending "should show up" to unlocked attribute tracked_list')
        # # new_record.tracked_list.append('should show up')
        # test_expression("new_record.tracked_list.append('should show up')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  appending list ["appended list"] to unlocked attribute tracked_list')
        # # new_record.tracked_list.append(['appended list'])
        # test_expression("new_record.tracked_list.append(['appended list'])", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  appending ["new list", {"some new key": ["some new list"]} to unlocked attribute tracked_list')
        # # new_record.tracked_list.append(['new list', {'some new key': ['some new list']}])
        # test_expression("new_record.tracked_list.append(['new list', {'some new key': ['some new list']}])", new_record=new_record)

        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # for item in new_record._tracking_known_uuids_tree():
        #     new_record._tracking_debug(f"  {item}")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  appending dict {{"some key": ["some list"]}} to unlocked attribute tracked_list')
        # # new_record.tracked_list.append({'some key': ['some list']})
        # test_expression("new_record.tracked_list.append({'some key': ['some list']})", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  tracked_list tree')
        # for item in new_record._tracking_known_uuids_tree(attribute_name='tracked_list'):
        #     new_record._tracking_debug(f"  {item}")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  locking attribute tracked_list')
        # new_record.tracked_list.lock() # type: ignore
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  setting key1 in attribute tracked_dict to "value1"')
        # # new_record.tracked_dict['key1'] = 'value1'
        # test_expression("new_record.tracked_dict.__setitem__('key1', 'value1')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  setting key2 in attribute tracked_dict to "value2"')
        # # new_record.tracked_dict['key2'] = 'value2'
        # test_expression("new_record.tracked_dict.__setitem__('key2', 'value2')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  changing key1 in attribute tracked_dict to "changed value1"')
        # # new_record.tracked_dict['key1'] = 'changed value1'
        # test_expression("new_record.tracked_dict.__setitem__('key1', 'changed value1')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  deleting key1 from attribute tracked_dict')
        # # del new_record.tracked_dict['key1']
        # test_expression("new_record.tracked_dict.__delitem__('key1')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  locking attribute tracked_dict')
        # new_record.tracked_dict.lock() # type: ignore

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  deleting key2 from locked attribute tracked_dict')
        # # del new_record.tracked_dict['key2']
        # test_expression("new_record.tracked_dict.__delitem__('key2')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  add key3 to a locked dictionary with value value3')
        # # new_record.tracked_dict['key3'] = 'value3'
        # test_expression("new_record.tracked_dict.__setitem__('key3', 'value3')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('unlock dictionary tracked_dict')
        # new_record.tracked_dict.unlock() # type: ignore

        # # new_record._tracking_debug_flag = True
        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  add child_dict with initial value {'child_key1': 'child_value1'}")
        # # new_record.tracked_dict['child_dict'] = {'child_key1': 'child_value1'}
        # test_expression("new_record.tracked_dict.__setitem__('child_dict', {'child_key1': 'child_value1'})", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_dict'] = }")
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_dict']._tracking_uuid = }") # type: ignore
        # except KeyError:
        #     new_record._tracking_debug("  child_dict key does not exist")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  change child_dict['child_key1']")
        # # new_record.tracked_dict['child_dict']['child_key1'] = 'changed child_value1'
        # test_expression("new_record.tracked_dict['child_dict'].__setitem__('child_key1', 'changed child_value1')", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_dict'] = }")
        # except KeyError:
        #     new_record._tracking_debug("  child_dict key does not exist")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  add 'child_key2' to child_dict with value 'child_value2'")
        # # new_record.tracked_dict['child_dict']['child_key2'] = 'child_value2'
        # test_expression("new_record.tracked_dict['child_dict'].__setitem__('child_key2', 'child_value2')", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_dict'] = }")
        # except KeyError:
        #     new_record._tracking_debug("  child_dict key does not exist")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  delete 'child_key1' from child_dict")
        # # del new_record.tracked_dict['child_dict']['child_key1']
        # test_expression("new_record.tracked_dict['child_dict'].__delitem__('child_key1')", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_dict'] = }")
        # except KeyError:
        #     new_record._tracking_debug("  child_dict key does not exist")
        # new_record._tracking_debug_flag = False
        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  add child_list with initial value ["child_list_item1"]')
        # # new_record.tracked_dict['child_list'] = ['child_list_item1']
        # test_expression("new_record.tracked_dict.__setitem__('child_list', ['child_list_item1'])", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_list'] = }")
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_list']._tracking_uuid = }") # type: ignore
        # except KeyError:
        #     new_record._tracking_debug("  child_list key does not exist")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  append to child_list with "child_list_append_item2"')
        # # new_record.tracked_dict['child_list'].append('child_list_append_item2')
        # test_expression("new_record.tracked_dict['child_list'].append('child_list_append_item2')", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict['child_list'] = }")
        # except KeyError:
        #     new_record._tracking_debug("  child_list key does not exist")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  tracked_list tree')
        # for item in new_record._tracking_known_uuids_tree(attribute_name='tracked_list'):
        #     new_record._tracking_debug(f"  {item}")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug("  assigning a new list [0, 1, 2, 3, 4, 5, 6] to tracked_list")
        # new_record._tracking_debug(f"  {new_record.tracked_list._tracking_uuid = }") # type: ignore
        # # new_record.tracked_list = [0, 1, 2, 3, 4, 5, 6]
        # test_expression("setattr(new_record, 'tracked_list', [0, 1, 2, 3, 4, 5, 6])", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_list = }")
        # new_record._tracking_debug(f"  {new_record.tracked_list._tracking_uuid = }") # type: ignore

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug(f'  {new_record.tracked_dict._tracking_uuid = }') # type: ignore
        # new_record._tracking_debug("  assigning a new dict {'newkey1': 'value1', 'newkey2': 'value2'} to tracked_dict")
        # # new_record.tracked_dict = {'newkey1': 'value1', 'newkey2': 'value2'}
        # test_expression("setattr(new_record, 'tracked_dict', {'newkey1': 'value1', 'newkey2': 'value2'})", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")
        # new_record._tracking_debug(f"  {new_record.tracked_dict._tracking_uuid = }") # type: ignore

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing set default, key growlist doesnt exist, and appending "new item" to list')
        # # new_record.tracked_dict.setdefault('growlist', []).append('new item') # type: ignore
        # test_expression("new_record.tracked_dict.setdefault('growlist', []).append('new item')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing set default, key growlist exists, and appending "another new item" to list')
        # # new_record.tracked_dict.setdefault('growlist', []).append('another new item') # type: ignore
        # test_expression("new_record.tracked_dict.setdefault('growlist', []).append('another new item')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing set default, key growlist exists, and appending "another new item" to list')
        # # new_record.tracked_dict.setdefault('growlist', []).append('a third new item') # type: ignore
        # test_expression("new_record.tracked_dict.setdefault('growlist', []).append('a 3rd new item')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing update to tracked_dict, argument: {"update1_key": "value3", "update1_key2": "value4"}')
        # # new_record.tracked_dict.update({'update1_key': 'value3', 'update1_key2': 'value4'}) # type: ignore
        # test_expression("new_record.tracked_dict.update({'update1_key': 'value3', 'update1_key2': 'value4'})", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing update to tracked_dict, argument: (update2_key="value5", update2_key2="value6")')
        # # new_record.tracked_dict.update(update2_key='value5', update2_key2='value6') # type: ignore
        # test_expression("new_record.tracked_dict.update(update2_key='value5', update2_key2='value6')", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing update to tracked_dict, argument: [("update3_key", 200), ("update3_key2", 400)]')
        # # new_record.tracked_dict.update([('update3_key', 200), ('update3_key2', 400)]) # type: ignore
        # test_expression("new_record.tracked_dict.update([('update3_key', 200), ('update3_key2', 400)])", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing update to tracked_dict, argument: [("update3_key", [100, 200, 300]), ("update3_key2", {"child_key": "child_value"})]')
        # # new_record.tracked_dict.update([('update3_key', [100, 200, 300]), ('update3_key2', {'child_key': 'child_value'})]) # type: ignore
        # test_expression("new_record.tracked_dict.update([('update3_key', [100, 200, 300]), ('update3_key2', {'child_key': 'child_value'})])", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing |= to tracked_dict, argument: [("update3_key", [100, 200, 300]), ("update3_key2", {"child_key": "child_value"})]')
        # test_expression("new_record.tracked_dict.__ior__([('update3_key', [100, 200, 300]), ('update3_key2', {'child_key': 'child_value'})])", new_record=new_record)
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  testing | to tracked_dict, argument: [("update3_key", 200), ("update3_key2", 400)]')
        # # test_dict = new_record.tracked_dict | {'update1_key': 'value3', 'update1_key2': [1000, 2000, 3000]}
        # test_dict = test_expression("new_record.tracked_dict | {'update1_key': 'value3', 'update1_key2': [1000, 2000, 3000]}", new_record=new_record)

        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")
        # new_record._tracking_debug(f"  {test_dict = }")

        # new_record._tracking_debug('#' * 80)
        # new_record._tracking_debug('  adding a int(key) to tracked_dict')
        # new_record._tracking_debug(f"  {new_record.tracked_dict = }")
        # # new_record.tracked_dict[2] = [] # type: ignore
        # test_expression("new_record.tracked_dict.__setitem__(2, [])", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict[2] = }") # type: ignore
        # except KeyError:
        #     new_record._tracking_debug("  key 2 does not exist")
        # # new_record.tracked_dict[2].append('new item') # type: ignore
        # test_expression("new_record.tracked_dict[2].append('new item')", new_record=new_record)
        # try:
        #     new_record._tracking_debug(f"  {new_record.tracked_dict[2] = }") # type: ignore
        # except KeyError:
        #     new_record._tracking_debug("  key 2 does not exist")

        # new_record._tracking_debug('#' * 80)
        new_record._tracking_debug_flag = False

        return True, ["see log"]
