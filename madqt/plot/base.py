# encoding: utf-8
"""
Plot base classes.
"""

from __future__ import absolute_import
from __future__ import unicode_literals


__all__ = [
    'SceneElement',
    'SceneGraph',
]


class SceneElement(object):

    """
    A self-contained unit to be plotted.

    The member functions may only be invoked in this order:
        (plot -> update* -> remove)*
    """

    def plot(self):
        """Plot the element in a newly created scene."""
        raise NotImplementedError

    def update(self):
        """Update the element state in the current scene."""
        raise NotImplementedError

    def remove(self):
        """Remove the element from the scene."""
        raise NotImplementedError

    # TODO: show/hide


class SceneGraph(SceneElement):

    """A scene element that is composed of multiple elements."""

    def __init__(self, items=None):
        self.items = [] if items is None else items

    def plot(self):
        for item in self.items:
            item.plot()

    def update(self):
        for item in self.items:
            item.update()

    def remove(self):
        self.clear_items()
        del self.items[:]

    def clear_items(self):
        for item in self.items:
            item.remove()
