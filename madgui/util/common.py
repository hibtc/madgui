"""
Common utilities.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import functools
import inspect
import os
import tempfile
from contextlib import contextmanager

# exported symbols
__all__ = [
    'cachedproperty',
    'instancevars',
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


def instancevars(func):
    """
    Store arguments as member variables.

    Example:

    >>> class Foo(object):
    ...     @instancevars
    ...     def __init__(self, bar):
    ...         pass
    >>> Foo(42).bar
    42
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        callargs = inspect.getcallargs(func, *args, **kwargs)
        self = args[0]
        for key, val in callargs.items():
            setattr(self, key, val)
        return func(*args, **kwargs)
    return wrapper


@contextmanager
def temp_filename():
    """Get filename for use within 'with' block and delete file afterwards."""
    fd, filename = tempfile.mkstemp()
    os.close(fd)
    yield filename
    try:
        os.remove(filename)
    except OSError:
        pass
