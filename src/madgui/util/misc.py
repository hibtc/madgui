"""
Misc programming toolbox.
"""

__all__ = [
    'memoize',
    'cachedproperty',
]

import os
import functools


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
    """A property decorator for cached, writeable properties."""
    key = '_' + func.__name__
    get_ = memoize(func)

    def set_(self, val):
        setattr(self, key, val)

    def del_(self):
        delattr(self, key)
    return property(get_, set_, del_)


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
