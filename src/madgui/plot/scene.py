"""
Plot base classes.
"""

__all__ = [
    'SceneNode',
    'SimpleArtist',
    'SceneGraph',
]


class SceneNode:

    """An element of a figure."""

    parent = None
    shown = False       # if this element is currently drawn
    enabled = True      # whether this element (+children) should be drawn
    figure = None

    # public API:

    def enable(self, enabled=True):
        """Enable/disable the element individually."""
        self.enabled = enabled
        self.render()

    # private, should be called via the scene tree only:

    def render(self, show=True):
        show = self.enabled and show
        shown = self.shown
        if show and not shown:
            self.draw()
            self.invalidate()
        elif not show and shown:
            self.remove()
            self.invalidate()
        self.shown = show

    # overrides, private, must only be called from `render`:

    def draw(self):
        """Plot the element in a newly created scene."""

    def remove(self):
        """Remove the element from the scene."""

    def update(self):
        """Update existing plot."""

    def redraw(self):
        self.render(False)
        self.render()

    def on_remove(self):
        """Notification when the entire graph was hidden."""
        self.shown = False

    def destroy(self):
        """Cleanup existing resources."""

    def invalidate(self):
        """Mark the canvas to be stale."""
        # Must override in root node!
        self.parent.invalidate()


class SimpleArtist(SceneNode):

    """Delegates to draw function that returns a list of matplotlib artists."""

    def __init__(self, artist, *args, **kwargs):
        super().__init__()
        self.lines = ()
        self.artist = artist
        self.args = args
        self.kwargs = kwargs

    def draw(self):
        self.lines = [
            line
            for ax in self.figure.axes
            for line in self.artist(ax, *self.args, **self.kwargs)
        ]

    def remove(self):
        for line in self.lines:
            line.remove()
        self.lines = ()

    def on_remove(self):
        self.lines = ()
        super().on_remove()

    destroy = on_remove


class SceneGraph(SceneNode):

    """A scene element that is composed of multiple elements."""

    def __init__(self, items=(), figure=None):
        super().__init__()
        self.items = list(items)
        self.figure = figure
        self._adopt(items)

    def _adopt(self, items):
        for item in items:
            item.parent = self
            item.figure = self.figure

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
        self._adopt(items)
        for item in items:
            item.render(self.shown)

    def insert(self, index, item):
        self.items.insert(index, item)
        self._adopt((item,))
        item.render(self.shown)

    def pop(self, item):
        """Remove and hide one item (by value)."""
        item.render(False)
        item.destroy()
        self.items.remove(item)

    def clear(self, items=()):
        """Remove and hide all items, and replace with new items."""
        self.remove()
        self.items.clear()
        self.extend(items)

    def on_remove(self):
        for item in self.items:
            item.on_remove()
        super().on_remove()

    def destroy(self):
        self.remove()
        for item in self.items:
            item.destroy()
        self.items.clear()
