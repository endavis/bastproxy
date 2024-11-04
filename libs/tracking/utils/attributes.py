import contextlib
class AttributeMonitor:
    def __init__(self):
        self._attributes_to_monitor = []
        self._am_original_values = {}

    def __setattr__(self, name, value):
        try:
            original_value = getattr(self, name)
        except AttributeError:
            original_value = '#!NotSet'
        super().__setattr__(name, value)

        if hasattr(self, '_attributes_to_monitor') and name in self._attributes_to_monitor:
                self._attribute_set(name, original_value, value)

    def _attribute_set(self, name, original_value, new_value):
        change_func = getattr(self, f"_am_onchange_{name}", None)
        if original_value == '#!NotSet':
            with contextlib.suppress(Exception):
                self._am_original_values[name] = new_value
        if original_value not in ["#!NotSet", new_value]:
            self._am_onchange__all(name, original_value, new_value)
            if change_func:
                change_func(original_value, new_value)

    def _am_get_original_value(self, name):
        return self._am_original_values.get(name, None)

    def _am_onchange__all(self, name, original_value, new_value):
        pass