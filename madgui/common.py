"""
Common utilities.
"""

# Force new style imports
from __future__ import absolute_import

# standard library
import os
import functools


def rchop(thestring, ending):
    """Remove substring at the end of a string."""
    if thestring.endswith(ending):
        return thestring[:-len(ending)]
    return thestring


def axis_name(axis_num):
    """Return readable name corresponding to axis number."""
    return "xyz"[axis_num]


def makedirs(path):
    """Make sure 'path' exists. Like 'os.makedirs(path, exist_ok=True)'."""
    try:
        os.makedirs(path)
    except OSError:
        # directory already exists. 'exist_ok' cannot be used until python3.2
        pass


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
