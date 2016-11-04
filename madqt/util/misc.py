# encoding: utf-8
"""
Misc programming toolbox.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import functools


__all__ = [
    'attribute_alias',
    'memoize',
    'cachedproperty',
    'update_property',
    'rename_key',
    'merged',
    'translate_default',
]


# class utils

def attribute_alias(alias):
    """Declare alias for an instance variable / attribute."""
    return property(
        lambda self:        getattr(self, alias),
        lambda self, value: setattr(self, alias, value),
        lambda self:        delattr(self, alias),
        "Alias for '{}'".format(alias))


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


def update_property(update, name=None):
    key = '_' + update.__name__
    @functools.wraps(update)
    def wrapper(self, *args, **kwargs):
        old = getattr(self, key, None)
        new = update(self, old, *args, **kwargs)
        setattr(self, key, new)
        return new
    return wrapper


def update_decorator(update):
    def decorator(func):
        def updater(self, saved, *args):
            return update(self, func, saved, *args)
        updater.__name__ = func.__name__
        return update_property(updater)
    return decorator


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
