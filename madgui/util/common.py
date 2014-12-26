"""
Common utilities.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import functools

# exported symbols
__all__ = [
    'cachedproperty',
]


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
