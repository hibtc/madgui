"""
Observable collection classes.
"""

from collections import MutableSequence
from contextlib import contextmanager
from functools import wraps
from threading import Lock
import operator

from madgui.core.base import Object, Signal


__all__ = [
    'List',
    'Selection'
]


def _operator(get, rtype=None):
    @wraps(get)
    def operation(*operands):
        rtype_ = operands[0].__class__ if rtype is None else rtype
        values = lambda: [operand.value for operand in operands]
        result = rtype_(get(*values()))
        update = lambda *args: result.set_value(get(*values()))
        for operand in operands:
            operand.changed.connect(update)
        return result
    return operation


class Bool(Object):

    """A bool-like value that can be observed for changes."""

    changed = Signal(bool)

    def __init__(self, value):
        super().__init__()
        self._value = bool(value)

    def get_value(self):
        return self._value

    def set_value(self, value):
        value = bool(value)
        if value != self._value:
            self._value = value
            self.changed.emit(value)

    value = property(get_value, set_value)

    __eq__  = _operator(operator.__eq__)
    __ne__  = _operator(operator.__ne__)
    __and__ = _operator(operator.__and__)
    __or__  = _operator(operator.__or__)
    __xor__ = _operator(operator.__xor__)
    __invert__ = _operator(operator.__not__)


class List(Object):

    """A list-like class that can be observed for changes."""

    # parameters: (slice, old_values, new_values)
    update_before = Signal([object, object, object])
    update_after = Signal([object, object, object])

    insert_notify = Signal([int, object])
    delete_notify = Signal([int])
    remove_notify = Signal([int, object])
    modify_notify = Signal([int, object])

    def __init__(self, items=None):
        """Use the items object by reference."""
        super().__init__()
        self._items = list() if items is None else items
        self.lock = Lock()

    def mirror(self, other):
        """Connect another list to be mirror of oneself."""
        self.insert_notify.connect(other.insert)
        self.delete_notify.connect(other.__delitem__)
        self.modify_notify.connect(other.__setitem__)

    @contextmanager
    def update_notify(self, slice, new_values):
        """Emit update signals, only when ."""
        with self.lock:
            old_values = self[slice]
            num_del, num_ins = len(old_values), len(new_values)
            if slice.step not in (None, 1) and num_del != num_ins:
                # This scenario is forbidden by `list` as well (even step=-1).
                # Catch it before emitting the event.
                raise ValueError(
                    "attempt to assign sequence of size {} to extended slice of size {}"
                    .format(num_ins, num_del))
            self.update_before.emit(slice, old_values, new_values)
            try:
                yield None
            finally:
                self._emit_single_notify(slice, old_values, new_values)
                self.update_after.emit(slice, old_values, new_values)

    def _emit_single_notify(self, slice, old_values, new_values):
        num_old = len(old_values)
        num_new = len(new_values)
        num_ins = num_new - num_old
        old_len = len(self) - num_ins
        indices = list(range(old_len))[slice]
        # TODO: verify correctness...:
        for idx, old, new in zip(indices, old_values, new_values):
            self.modify_notify.emit(idx, new)
        if num_old > num_new:
            for val in old_values[num_new:]:
                self.delete_notify.emit(indices[0])
                self.remove_notify.emit(indices[0], val)
        elif num_new > num_old:
            start = (slice.start or 0) + num_old
            for idx, val in enumerate(new_values[num_old:]):
                self.insert_notify.emit(start+idx, val)

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
        # Don't notify user for NOPs:
        if isinstance(index, slice) and len(self._items[index]) == 0:
            return
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


MutableSequence.register(List)

class Selection:

    """
    List of elements with the additional notion of an *active* element
    (determined by insertion order).

    For simplicity, the track-record of insertion order is implemented as a
    reordering of a list of elements - even though a selection of elements may
    be represented somewhat more appropriately by an `OrderedSet`
    (=`Set`+`List`).
    """

    def __init__(self, elements=None):
        self.elements = List() if elements is None else elements
        self.ordering = list(range(len(self.elements)))
        maintain_selection(self.ordering, self.elements)

    def get_top(self):
        """Get index of top element."""
        return self.ordering[-1]

    def set_top(self, index):
        """Move element with specified index to top of the list."""
        self.ordering.remove(index)
        self.ordering.append(index)

    top = property(get_top, set_top)


def maintain_selection(sel, avail):
    def insert(index, value):
        for i, v in enumerate(sel):
            if v >= index:
                sel[i] += 1
        sel.append(index)
    def delete(index):
        if index in sel:
            sel.remove(index)
        for i, v in enumerate(sel):
            if v >= index:
                sel[i] -= 1
    avail.insert_notify.connect(insert)
    avail.delete_notify.connect(delete)
