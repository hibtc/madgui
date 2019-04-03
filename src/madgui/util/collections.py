"""
Observable collection classes.
"""

__all__ = [
    'Boxed',
    'Bool',
    'List',
    'Selection'
]

from collections.abc import MutableSequence
from contextlib import contextmanager
from functools import wraps
import operator

from madgui.util.signal import Signal


def _operator(get):
    @wraps(get)
    def operation(*operands):
        rtype = operands[0].__class__
        dtype = operands[0]._dtype
        values = lambda: [dtype(operand()) for operand in operands]
        result = rtype(get(*values()))
        update = lambda *args: result.set(get(*values()))
        for operand in operands:
            operand.changed.connect(update)
        return result
    return operation


class Boxed:

    """
    A box that holds a single object and can be observed for changes
    (assigning a different object).

    Storing an object inside another one is the only way to pass around
    variable references in python (which doesn't have native pointer or
    references variables otherwise and therefore only supports passing the
    objects themselves).

    This class also provides a signal that notifies about changes in value.

    This has some similarities to what is called a BehaviourSubject in RX.
    """

    changed = Signal([object])
    changed2 = Signal([object, object])

    def __init__(self, value):
        self._value = self._dtype(value)

    def __call__(self, *value):
        return self._value

    def set(self, value, force=False):
        new = self._dtype(value)
        old = self._value
        if force or new != old:
            self._value = new
            self.changed.emit(new)
            self.changed2.emit(old, new)

    def _dtype(self, value):
        return value

    def changed_singleshot(self, callback):
        def on_change(value):
            self.changed.disconnect(on_change)
            callback()
        self.changed.connect(on_change)

    __eq__ = _operator(operator.__eq__)
    __ne__ = _operator(operator.__ne__)


class Bool(Boxed):

    _dtype = bool
    __and__ = _operator(operator.__and__)
    __or__ = _operator(operator.__or__)
    __xor_ = _operator(operator.__xor__)
    __invert__ = _operator(operator.__not__)


class List:

    """A list-like class that can be observed for changes."""

    # parameters: (slice, old_values, new_values)
    update_started = Signal([object, object, object])
    update_finished = Signal([object, object, object])

    inserted = Signal([int, object])
    removed = Signal([int])
    changed = Signal([int, object])

    def __init__(self, items=None):
        """Use the items object by reference."""
        self._items = list() if items is None else items

    def mirror(self, other):
        """Connect another list to be mirror of oneself."""
        self.inserted.connect(other.insert)
        self.removed.connect(other.__delitem__)
        self.changed.connect(other.__setitem__)

    def map(self, fn):
        l = List([fn(x) for x in self])
        self.inserted.connect(lambda i, x: l.insert(i, fn(x)))
        self.changed.connect(lambda i, x: l.__setitem__(i, fn(x)))
        self.removed.connect(l.__delitem__)
        return l

    def touch(self):
        self[:] = self

    @contextmanager
    def update_notify(self, slice, new_values):
        """Emit update signals, only when ."""
        old_values = self[slice]
        num_del, num_ins = len(old_values), len(new_values)
        if slice.step not in (None, 1) and num_del != num_ins:
            # This scenario is forbidden by `list` as well (even step=-1).
            # Catch it before emitting the event.
            raise ValueError(
                "attempt to assign sequence of size {} to slice of size {}"
                .format(num_ins, num_del))
        self.update_started.emit(slice, old_values, new_values)
        try:
            yield None
        finally:
            self._emit_single_notify(slice, old_values, new_values)
            self.update_finished.emit(slice, old_values, new_values)

    def _emit_single_notify(self, slice, old_values, new_values):
        num_old = len(old_values)
        num_new = len(new_values)
        num_ins = num_new - num_old
        old_len = len(self) - num_ins
        indices = list(range(old_len))[slice]
        # TODO: verify correctness...:
        for idx, old, new in zip(indices, old_values, new_values):
            self.changed.emit(idx, new)
        if num_old > num_new:
            for val in old_values[num_new:]:
                self.removed.emit(indices[0])
        elif num_new > num_old:
            start = (slice.start or 0) + num_old
            for idx, val in enumerate(new_values[num_old:]):
                self.inserted.emit(start+idx, val)

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


class Selection(List):

    """Set of items with the additional notion of a cursor to the least
    recently *active* element. Each item can occur only once in the set.

    Note that the inherited ``List`` methods and signals can be used to listen
    for selection changes, and to query or delete items. However, for
    *inserting* or *modifying* elements, only use the methods defined in the
    ``Selection`` class can be used to ensure that items stay unique.
    """

    def __init__(self):
        super().__init__()
        self.cursor = Boxed(0)
        # activity changes the "active" element:
        self.changed.connect(self._on_changed)
        self.removed.connect(self._on_removed)

    def add(self, item, replace=False):
        """Add the item to the set if not already present. If ``replace`` is
        true, the currently active item will be replaced by the new item. In
        each case, set the active element to ``item``."""
        if item in self:
            self[self.index(item)] = item
        elif replace and len(self) > 0:
            self[self.cursor()] = item
        else:
            self.append(item)
            # When inserting elements, we can't use the `self.inserted` signal
            # to adjust the cursor, because this triggers too early for other
            # viewers to have realized that a new element was inserted
            # already (which is I guess the downside of using DirectConnection
            # signals, i.e. depth-first evaluation):
            self.cursor.set(len(self) - 1)

    def cursor_item(self):
        """Return the currently active item."""
        return self[self.cursor()] if len(self) > 0 else None

    # internal methods

    def _on_changed(self, index, *_):
        self.cursor.set(index, force=True)

    def _on_removed(self, index):
        if self.cursor() > index or self.cursor() == index > 0:
            self.cursor.set(self.cursor() - 1)
