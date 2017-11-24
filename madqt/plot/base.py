"""
Plot base classes.
"""

from functools import wraps


__all__ = [
    'Artist',
    'SimpleArtist',
    'SceneGraph',
]


class Artist:

    """An element of a figure."""

    shown = False       # if this element is currently drawn
    enabled = True      # whether this element (+children) should be drawn

    # public API:

    def enable(self, enabled=True):
        """Enable/disable the element individually."""
        self.enabled = enabled
        self.render()

    # private, should be called via the scene tree only:

    def render(self, show=None):
        show = self.enabled if show is None else show
        shown = self.shown
        if show and not shown:
            self.draw()
        elif not show and shown:
            self.remove()
        self.shown = show

    # overrides, private, must only be called from `render`:

    def draw(self):
        """Plot the element in a newly created scene."""

    def remove(self):
        """Remove the element from the scene."""

    def update(self):
        """Update existing plot."""
        self.render(False)
        self.render()

    def hidden(self):
        """Notification when the entire graph was hidden."""
        self.shown = False

    def destroy(self):
        """Cleanup existing resources."""


class SimpleArtist(Artist):

    """Delegates to draw function that returns a list of matplotlib artists."""

    def __init__(self, artist, *args, **kwargs):
        super().__init__()
        self.lines = ()
        self.artist = artist
        self.args = args
        self.kwargs = kwargs

    def draw(self):
        self.lines = self.artist(*self.args, **self.kwargs)

    def remove(self):
        for line in self.lines:
            line.remove()
        self.lines = ()

    def hidden(self):
        self.lines = ()
        super().hidden()

    destroy = hidden


class SceneGraph(Artist):

    """A scene element that is composed of multiple elements."""

    def __init__(self, items=()):
        super().__init__()
        self.items = list(items)

    # overrides

    def draw(self):
        for item in self.items:
            item.render(True)

    def remove(self):
        for item in self.items:
            item.render(False)

    def update(self):
        for item in self.items:
            item.update()

    # manage items:

    def add(self, *items):
        """Extend by several children."""
        self.extend(items)

    def extend(self, items):
        """Extend by several children."""
        self.items.extend(items)
        for item in items:
            item.render(self.shown)

    def insert(self, index, item):
        self.items.insert(index, item)
        item.render(self.shown)

    def pop(self, item):
        """Remove and hide one item (by value)."""
        item.render(False)
        self.items.remove(item)

    def clear(self, items=()):
        """Remove and hide all items, and replace with new items."""
        self.remove()
        self.items.clear()
        self.extend(items)

    def hidden(self):
        for item in self.items:
            item.hidden()
        super().hidden()

    def destroy(self):
        for item in self.items:
            item.destroy()
        self.items.clear()
