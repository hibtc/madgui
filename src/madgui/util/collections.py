"""
Observable collection classes.
"""

__all__ = [
    'List',
    'Selection'
]

from collections.abc import MutableSequence, Sequence
from contextlib import contextmanager
from functools import wraps, partial
import operator

from madgui.qt import QtCore
from madgui.core.signal import Object, Signal


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


class Boxed(Object):

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

    changed = Signal([object], [object, object])

    def __init__(self, value):
        super().__init__()
        self._value = self._dtype(value)

    def __call__(self, *value):
        return self._value

    def set(self, value):
        new = self._dtype(value)
        old = self._value
        if new != old:
            self._value = new
            self.changed.emit(new)
            self.changed[object, object].emit(old, new)

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

    def mirror(self, other):
        """Connect another list to be mirror of oneself."""
        self.insert_notify.connect(other.insert)
        self.delete_notify.connect(other.__delitem__)
        self.modify_notify.connect(other.__setitem__)

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
    sel[:] = range(len(avail))


class Cache(Object):

    """
    Cached state that can be invalidated. Invalidation triggers recomputation
    in the main loop at the next idle time.
    """

    invalidated = Signal()
    updated = Signal()      # emitted after update
    invalid = False         # prevents invalidation during callback()

    def __init__(self, callback):
        super().__init__()
        self.data = None
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self)
        self.callback = callback

    def invalidate(self):
        if not self.invalid:
            self.invalid = True
            if self.receivers(self.updated) > 0:
                self.timer.start()
            self.invalidated.emit()

    def __call__(self, force=False):
        if force or self.invalid:
            self.timer.stop()
            self.invalid = True     # prevent repeated invalidation in callback
            self.data = self.callback()
            self.invalid = False    # clear AFTER update
            self.updated.emit()
        return self.data

    @classmethod
    def decorate(cls, fn):
        # TODO: resolve cyclic dependency!
        from madgui.util.misc import memoize
        return property(memoize(wraps(fn)(
            lambda self: cls(fn.__get__(self)))))


class CachedList(Sequence):

    """Immutable collection of named cached items."""

    def __init__(self, cls, keys, transform=None):
        keys = [self._transform(k) for k in keys]
        self._indices = {k: i for i, k in enumerate(keys)}
        self._items = [Cache(partial(cls, i, k)) for i, k in enumerate(keys)]
        self.invalidate()

    def invalidate(self, item=None):
        if item is None:
            for item in self._items:
                item.invalidate()
        else:
            index = self.index(item)
            self._items[index].invalidate()

    def __contains__(self, item):
        """
        Check if sequence contains item with specified name.

        Can be invoked with the item index or name or the item itself.
        """
        try:
            self.index(item)
            return True
        except (KeyError, ValueError):
            return False

    def __getitem__(self, item):
        """Return item with specified index."""
        idx = self.index(item)
        return self._items[idx]()

    def __len__(self):
        """Get number of item."""
        return len(self._items)

    def index(self, item):
        """
        Find index of item with specified name.

        :raises ValueError: if the item is not found
        """
        if isinstance(item, int):
            if item < 0:
                return item + len(self)
            return item
        try:
            return self._indices[self._transform(item)]
        except KeyError:
            raise ValueError(
                "Unknown item: {!r} ({})".format(item, type(item)))

    def as_list(self, l=None):
        if l is None:
            l = List()
        l[:] = list(self)

        def update(idx):
            l[idx] = self[idx]
        for idx, item in enumerate(self._items):
            item.updated.connect(partial(update, idx))
        return l

    def sublist(self, keys):
        l = self.__class__(None, [])
        l._items = [self._items[self.index(k)] for k in keys]
        return l

    def _transform(self, key):
        if isinstance(key, str):
            return key.lower()
