"""
Misc programming toolbox.
"""

import os
import functools
import collections
import tempfile
import importlib

from madgui.util.collections import Bool
from madgui.util.qt import notifyCloseEvent, present

__all__ = [
    'safe_hasattr',
    'suppress',
    'memoize',
    'cachedproperty',
    'update_property',
    'Property',
    'SingleWindow',
    'rename_key',
    'merged',
    'translate_default',
    'make_index',
]


def try_import(name):
    """Try to import module. Returns the module or ``None`` if it fails."""
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def safe_hasattr(obj, key):
    """
    Safe replacement for `hasattr()`. The py2 builtin `hasattr()` shadows all
    exceptions, see https://hynek.me/articles/hasattr/.
    """
    try:
        getattr(obj, key)
        return True
    except AttributeError:
        return False


def suppress(exc, fun, *args, **kwargs):
    try:
        return fun(*args, **kwargs)
    except exc:
        return None


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
    return property(memoize(func))


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


def update_property(update, name=None):
    key = '_' + update.__name__
    @functools.wraps(update)
    def wrapper(self, *args, **kwargs):
        old = getattr(self, key, None)
        new = update(self, old, *args, **kwargs)
        setattr(self, key, new)
        return new
    return wrapper


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
        return safe_hasattr(self, '_val')

    def _get(self):
        return self._val

    def _set(self, val):
        self._val = val
        self.holds_value.set_value(True)

    def _del(self):
        del self._val
        self.holds_value.set_value(False)

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
        notifyCloseEvent(window, self._closed)
        return window

    def _update(self):
        present(self.val.window())


class LazyList(collections.Sequence):

    def __init__(self, len, get):
        self._len = len
        self._get = get
        self._dat = {}

    def __getitem__(self, index):
        if index not in self._dat:
            self._dat[index] = self._get(index)
        return self._dat[index]

    def __len__(self):
        return self._len


# dictionary utils

def rename_key(d, name, new):
    if name in d:
        d[new] = d.pop(name)


def merged(d1, *others):
    r = d1.copy()
    for d in others:
        r.update(d)
    return r


def translate_default(d, name, old_default, new_default):
    if d[name] == old_default:
        d[name] = new_default


def make_index(values):
    return {k: i for i, k in enumerate(values)}


# Returns a filename rather than a `NamedTemporaryFile` to gain more
# control over the encoding on python2:
def logfile_name(path, base, ext):
    # TODO: should also print log path
    # TODO: how to avoid clutter? delete old files / use unique filename/dir?
    # NOTE: saves all logs to temp folder currently
    fd, name = tempfile.mkstemp(suffix=ext, prefix=base+'.', text=True)
    os.close(fd)
    return name


def strip_suffix(s, suffix):
    return s[:-len(suffix)] if s.endswith(suffix) else s
