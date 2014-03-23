# encoding: utf-8
"""
Simple POD vector struct.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from collections import namedtuple

# exported symbols
__all__ = ['Vector']


Vector = namedtuple('Vector', ['x', 'y'])
