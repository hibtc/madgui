"""
Misc programming toolbox.
"""

__all__ = [
    'memoize',
    'invalidate',
    'cachedproperty',
    'ranges',
    'strip_suffix',
    'relpath',
    'userpath',
]

import os
import functools


# class utils

def memoize(func):
    """
    Decorator for cached method that remembers its result from the first
    execution and returns this in all subsequent calls rather than executing
    the function again.

    Example:

        >>> class Foo:
        ...     @memoize
        ...     def bar(self):
        ...         print("executing bar…")
        ...         return 'bar'

        >>> foo = Foo()
        >>> foo.bar()
        executing bar…
        'bar'
        >>> foo.bar()
        'bar'

    The cached result can be cleared using ``invalidate``:

        >>> invalidate(foo, 'bar')
        >>> foo.bar()
        executing bar…
        'bar'

    If arguments are passed, the result is always recomputed.
    """
    key = '_' + func.__name__

    @functools.wraps(func)
    def get(self, *args, **kwargs):
        if not (args or kwargs):
            try:
                return getattr(self, key)
            except AttributeError:
                pass
        val = func(self)
        setattr(self, key, val)
        return val
    return get


def invalidate(obj, func):
    """Invalidate cache for memoized function."""
    key = '_' + func
    try:
        delattr(obj, key)
    except AttributeError:
        pass


def cachedproperty(func):
    """
    Decorator for cached, writeable properties.

        >>> class Foo:
        ...     @cachedproperty
        ...     def bar(self):
        ...         return ['bar']

        >>> foo = Foo()
        >>> foo.bar
        ['bar']

        >>> foo.bar is foo.bar
        True

        >>> foo.bar = 'qux'
        >>> foo.bar
        'qux'

        >>> del foo.bar
        >>> foo.bar
        ['bar']
    """
    key = '_' + func.__name__
    get_ = memoize(func)

    def set_(self, val):
        setattr(self, key, val)

    def del_(self):
        delattr(self, key)
    return property(get_, set_, del_)


# dictionary utils

def ranges(nums):
    """Identify groups of consecutive numbers in a list. Returns a list of
    intervals ``[start, end)`` as tuples."""
    nums = sorted(set(nums))
    gaps = [[s, e] for s, e in zip(nums, nums[1:]) if s+1 < e]
    edges = iter(nums[:1] + sum(gaps, []) + nums[-1:])
    return [(s, e+1) for s, e in zip(edges, edges)]


def strip_suffix(s, suffix):
    """Strip a suffix from a string, if present."""
    return s[:-len(suffix)] if s.endswith(suffix) and suffix else s


def relpath(path, start):
    """Try to make ``path`` relative to ``start`` using ``os.path.relpath``,
    but returns ``path`` itself if this fails (e.g. if they are on different
    drives on windows)."""
    try:
        return os.path.relpath(path, start)
    except ValueError:  # e.g. different drive on windows
        return path


def userpath(path):
    """Expand '~' and environment variables in a user-given path string."""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
