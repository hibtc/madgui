"""
Misc programming toolbox.
"""

__all__ = [
    'memoize',
    'cachedproperty',
    'Property',
    'SingleWindow',
]

import os
import functools

from madgui.util.collections import Bool
from madgui.util.qt import notifyCloseEvent, present


# class utils

def memoize(func):
    key = '_' + func.__name__

    @functools.wraps(func)
    def get(self):
        try:
            return getattr(self, key)
        except AttributeError:
            val = func(self)
            setattr(self, key, val)
            return val
    return get


def cachedproperty(func):
    """A memoize decorator for class properties."""
    key = '_' + func.__name__
    get_ = memoize(func)

    def set_(self, val):
        setattr(self, key, val)

    def del_(self):
        delattr(self, key)
    return property(get_, set_, del_)


def rw_property(func, name=None):
    """A property that allows overwriting the value."""
    key = '_' + (name or func.__name__)

    def get_(self):
        return getattr(self, key, None) or func(self)

    def set_(self, val):
        setattr(self, key, val)

    def del_(self):
        setattr(self, key, None)
    return property(get_, set_, del_)


class Property:

    def __init__(self, obj, construct):
        self.obj = obj
        self.construct = construct
        self.holds_value = Bool(False)

    # porcelain

    @classmethod
    def factory(cls, func):
        @functools.wraps(func)
        def getter(self):
            return cls(self, func)
        return cachedproperty(getter)

    def create(self):
        if self._has:
            self._update()
        else:
            self._new()
        return self.val

    def destroy(self):
        if self._has:
            self._del()

    def toggle(self):
        if self._has:
            self._del()
        else:
            self._new()

    def _new(self):
        val = self.construct(self.obj)
        self._set(val)
        return val

    def _update(self):
        pass

    @property
    def _has(self):
        return hasattr(self, '_val')

    def _get(self):
        return self._val

    def _set(self, val):
        self._val = val
        self.holds_value.set(True)

    def _del(self):
        del self._val
        self.holds_value.set(False)

    # use lambdas to enable overriding the _get/_set/_del methods
    # without having to redefine the 'val' property
    val = property(lambda self:      self._get(),
                   lambda self, val: self._set(val),
                   lambda self:      self._del())


class SingleWindow(Property):

    def _del(self):
        self.val.window().close()

    def _closed(self):
        super()._del()

    def _new(self):
        window = super()._new()
        window.show()
        notifyCloseEvent(window, self._closed)
        return window

    def _update(self):
        present(self.val.window())


# dictionary utils

def ranges(nums):
    """Identify groups of consecutive numbers in a list."""
    nums = sorted(set(nums))
    gaps = [[s, e] for s, e in zip(nums, nums[1:]) if s+1 < e]
    edges = iter(nums[:1] + sum(gaps, []) + nums[-1:])
    return [(s, e+1) for s, e in zip(edges, edges)]


def strip_suffix(s, suffix):
    return s[:-len(suffix)] if s.endswith(suffix) else s


def relpath(path, start):
    try:
        return os.path.relpath(path, start)
    except ValueError:  # e.g. different drive on windows
        return path
