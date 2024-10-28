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
            with contextlib.suppress(Exception):
                self._am_original_values[name] = value
        super().__setattr__(name, value)        

        if hasattr(self, '_attributes_to_monitor') and name in self._attributes_to_monitor:
                self._attribute_set(name, original_value, value)

    def _attribute_set(self, name, original_value, new_value):
        change_func = getattr(self, f"_onchange_{name}", None)
        if original_value not in ["#!NotSet", new_value]:
            if self.__class__.__name__ == 'ToClientLine':
                print(f"Attribute {name} changed from '{original_value}' to '{new_value}'")
                if type(original_value) != type(new_value):
                    print(f"Attribute {name} changed from '{type(original_value)}' to '{type(new_value)}'")            
            self._onchange__all(name, original_value, new_value)
            if change_func:
                change_func(original_value, new_value)

    def _am_get_original_value(self, name):
        return self._am_original_values.get(name, None)

    def _onchange__all(self, name, original_value, new_value):
        pass