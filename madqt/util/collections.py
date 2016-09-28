# encoding: utf-8
"""
Observable collection classes.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import MutableSequence
from contextlib import contextmanager
from threading import Lock

from madqt.core.base import Object, Signal


__all__ = [
    'List',
    'UpdateNotifications',
]


class List(MutableSequence):

    """A list-like class that can be observed for changes."""

    def __init__(self, items=None):
        """Use the items object by reference."""
        self._items = [] if items is None else items
        self.update_notify = UpdateNotifications(self)

    # Sized

    def __len__(self):
        return len(self._items)

    # Iterable

    def __iter__(self):
        return iter(self._items)

    # Container

    def __contains__(self, value):
        return value in self._items

    # Sequence

    def __getitem__(self, index):
        return self._items[index]

    def __reversed__(self):
        return reversed(self._items)

    def index(self, value):
        return self._items.index(value)

    def count(self, value):
        return self._items.count(value)

    # MutableSequence

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            value = list(value)
        else:
            index = slice(index, index+1)
            value = (value,)
        with self.update_notify(index, value):
            self._items[index] = value

    def __delitem__(self, index):
        if not isinstance(index, slice):
            index = slice(index, index+1)
        with self.update_notify(index, ()):
            del self._items[index]

    def insert(self, index, value):
        with self.update_notify(slice(index, index), (value,)):
            self._items.insert(index, value)

    append = MutableSequence.append
    reverse = MutableSequence.reverse

    def extend(self, values):
        end = len(self._items)
        self[end:end] = values

    pop = MutableSequence.pop
    remove = MutableSequence.remove
    __iadd__ = MutableSequence.__iadd__

    # convenience

    def clear(self):
        del self[:]


class UpdateNotifications(Object):

    """
    Provides notifications before/after an update operation.
    """

    # parameters: (slice, old_values, new_values)
    before = Signal([object, object, object])
    after = Signal([object, object, object])

    def __init__(self, obj):
        super(UpdateNotifications, self).__init__()
        self.lock = Lock()
        self.obj = obj

    @contextmanager
    def __call__(self, slice, new_values):
        """Emit update signals, only when ."""
        with self.lock:
            old_values = self.obj[slice]
            num_del, num_ins = len(old_values), len(new_values)
            if slice.step not in (None, 1) and num_del != num_ins:
                # This scenario is forbidden by `list` as well (even step=-1).
                # Catch it before emitting the event.
                raise ValueError(
                    "attempt to assign sequence of size {} to extended slice of size {}"
                    .format(num_ins, num_del))
            self.before.emit(slice, old_values, new_values)
            try:
                yield None
            finally:
                self.after.emit(slice, old_values, new_values)
