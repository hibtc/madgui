# encoding: utf-8
"""
Misc programming toolbox.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import functools


__all__ = [
    'attribute_alias',
    'cachedproperty',
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


def cachedproperty(func):
    """A memoize decorator for class properties."""
    key = '_' + func.__name__
    @functools.wraps(func)
    def get(self):
        try:
            return getattr(self, key)
        except AttributeError:
            val = func(self)
            setattr(self, key, val)
            return val
    return property(get)


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
