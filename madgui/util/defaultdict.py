from collections import MutableMapping


class DefaultDict(MutableMapping):

    """
    Like `collections.defaultdict`, but passes the key name to the constructor
    function.
    """

    def __init__(self, construct):
        self._construct = construct
        self._data = {}

    def __getitem__(self, key):
        if key not in self._data:
            self._data[key] = self._construct(key)
        return self._data[key]

    def __setitem__(self, key, val):
        self._data[key] = val

    def __delitem__(self, key):
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)
