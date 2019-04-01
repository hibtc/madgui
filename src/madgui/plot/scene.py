"""
Plot base classes.
"""

__all__ = [
    'SceneNode',
    'SimpleArtist',
    'SceneGraph',
    'ListView',
    'LineBundle',
    'plot_line',
]


class SceneNode:

    """An element of a figure."""

    # member variables (will be overriden per instance if deviating):

    name = None
    parent = None
    shown = False       # if this element is currently drawn
    _enabled = True     # whether this element (+children) should be drawn
    _figure = None      # the matplotlib figure we should draw on
    items = ()          # child nodes
    lines = None        # drawn matplotlib figure elements

    # public API:

    def enable(self, enabled=True):
        """Enable/disable the element individually."""
        if self._enabled != enabled:
            self._enabled = enabled
            self.render()
            self.draw_idle()

    def enabled(self):
        """Check whether this element should be drawn."""
        return self._enabled and (
            self.parent is None or self.parent.enabled())

    def node(self, name):
        """Find and return child node by name."""
        for item in self.items:
            if item.name == name:
                return item

    def invalidate(self):
        """Mark drawn state as stale and redraw if needed."""
        if self.enabled() and self.shown:
            self._update()

    @property
    def figure(self):
        return self._figure or self.parent.figure

    # private, should be called via the scene tree only:

    def render(self, show=True):
        """Draw or remove this node (and all children) from the figure."""
        show = self.enabled() and show
        shown = self.shown
        if show and not shown:
            self._draw()
        elif not show and shown:
            self._erase()
        self.shown = show

    def on_clear_figure(self):
        """
        cleanup references to drawn state. Called when the figure was cleared,
        but the SceneNode is still part of the SceneGraph for next redraw.
        """
        self.shown = False
        self.lines = None

    def destroy(self):
        """
        Cleanup all allocated ressources and disconnect signals. Called when
        the SceneNode is removed from the graph and not needed anymore.
        """
        self.on_clear_figure()

    # overrides, private, must only be called from `render`:

    def _draw(self):
        """Plot the element in a newly created scene."""

    def _erase(self):
        """Remove the element from the scene."""

    def _update(self):
        """Update existing plot."""

    # Used internally, must override in root node!
    def draw_idle(self):
        """Let the canvas know that it has to redraw."""
        self.parent.draw_idle()


class SimpleArtist(SceneNode):

    """Delegates to draw function that returns a list of matplotlib artists."""

    def __init__(self, name, artist, *args, **kwargs):
        self.name = name
        self.artist = artist
        self.args = args
        self.kwargs = kwargs

    def _draw(self):
        self.lines = LineBundle([
            self.artist(ax, *self.args, **self.kwargs)
            for ax in self.figure.axes
        ])

    def _erase(self):
        self.lines.remove()

    def _update(self):
        self.lines = self.lines.redraw()


class SceneGraph(SceneNode):

    """A scene element that is composed of multiple elements."""

    def __init__(self, name, items=(), figure=None):
        self.name = name
        self.items = list(items)
        self._figure = figure
        self._adopt(items)

    def _adopt(self, items):
        for item in items:
            item.parent = self

    # overrides

    def _draw(self):
        for item in self.items:
            item.render(True)

    def _erase(self):
        for item in self.items:
            item.render(False)

    def _update(self):
        for item in self.items:
            item.invalidate()

    # manage items:

    def add(self, *items):
        """Extend by several children."""
        self.extend(items)

    def extend(self, items):
        """Extend by several children."""
        self.items.extend(items)
        self._adopt(items)
        if self.shown:
            for item in items:
                item.render(True)
            self.draw_idle()

    def insert(self, index, item):
        self.items.insert(index, item)
        self._adopt((item,))
        if self.shown:
            item.render(True)
            self.draw_idle()

    def pop(self, item):
        """Remove and hide one item (by value)."""
        item.render(False)
        item.destroy()
        self.items.remove(item)
        self.draw_idle()

    def on_clear_figure(self):
        for item in self.items:
            item.on_clear_figure()
        self.shown = False

    def destroy(self):
        for item in self.items:
            item.destroy()
        self.items = None
        self.shown = False


class ListView(SceneGraph):

    def __init__(self, name, model, fn, *args, **kwargs):
        super().__init__(name)
        self.model = model
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        for idx, item in enumerate(model):
            self._add(idx, item)
        model.inserted.connect(self._add)
        model.removed.connect(self._rm)
        model.changed.connect(self._chg)

    def _add(self, idx, item):
        # This handles items with `name` or `elem` attributes and allows
        # `item.elem` to be either a name string or `Element` object:
        elem = getattr(item, 'elem', item)
        name = getattr(elem, 'name', elem)
        args = self.args + (item,)
        node = SimpleArtist(str(name), self.fn, *args, **self.kwargs)
        self.insert(idx, node)

    def _rm(self, idx):
        self.pop(self.items[idx])

    def _chg(self, idx, val):
        self._rm(idx)
        self._add(idx, val)

    def destroy(self):
        self.model.inserted.disconnect(self._add)
        self.model.removed.disconnect(self._rm)
        self.model.changed.disconnect(self._chg)
        super().destroy()


class LineBundle(list):

    __slots__ = ()

    def remove(self):
        for line in self:
            line.remove()
        self.clear()

    def redraw(self):
        self[:] = [
            line.redraw() if hasattr(line, 'redraw') else line
            for line in self
        ]
        return self


class plot_line:

    """Plot a single line using an fetch function."""

    def __init__(self, ax, get_xydata, **style):
        self._get_xydata = get_xydata
        self.line, = ax.plot(*get_xydata(), **style)

    def redraw(self):
        self.line.set_data(*self._get_xydata())
        return self

    def remove(self):
        self.line.remove()
