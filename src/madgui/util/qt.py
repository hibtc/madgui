"""
Qt utilities.
"""

import functools
from importlib_resources import path as resource_filename

from madgui.qt import QtGui
from madgui.util.collections import Bool
from madgui.util.misc import cachedproperty


def notifyCloseEvent(widget, handler):
    """Connect a closeEvent observer."""
    # There are three basic ways to get notified when a window is closed:
    #   - set the WA_DeleteOnClose attribute and connect to the
    #     QWidget.destroyed signal
    #   - use installEventFilter / eventFilter
    #   - hook into the closeEvent method (see notifyEvent below)
    # We use the first option here since it is the simplest:
    notifyEvent(widget, 'closeEvent', lambda event: handler())


def notifyEvent(widget, name, handler):
    """Connect an event listener."""
    old_handler = getattr(widget, name)

    def new_handler(event):
        handler(event)
        old_handler(event)
    setattr(widget, name, new_handler)


def present(window, raise_=False):
    """Activate window."""
    window.show()
    window.activateWindow()
    if raise_:
        window.raise_()


def monospace():
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)


def bold():
    font = QtGui.QFont()
    font.setBold(True)
    return font


def load_icon_resource(module, name, format='XPM'):
    with resource_filename(module, name) as filename:
        return QtGui.QIcon(QtGui.QPixmap(str(filename), format))


class Property:

    def __init__(self, obj, construct):
        self.obj = obj
        self.construct = construct
        self.holds_value = Bool(False)

    # porcelain

    @classmethod
    def factory(cls, func):
        @functools.wraps(func)
        def getter(self):
            return cls(self, func)
        return cachedproperty(getter)

    def create(self):
        if self._has:
            self._update()
        else:
            self._new()
        return self.val

    def destroy(self):
        if self._has:
            self._del()

    def toggle(self):
        if self._has:
            self._del()
        else:
            self._new()

    def _new(self):
        val = self.construct(self.obj)
        self._set(val)
        return val

    def _update(self):
        pass

    @property
    def _has(self):
        return hasattr(self, '_val')

    def _get(self):
        return self._val

    def _set(self, val):
        self._val = val
        self.holds_value.set(True)

    def _del(self):
        del self._val
        self.holds_value.set(False)

    # use lambdas to enable overriding the _get/_set/_del methods
    # without having to redefine the 'val' property
    val = property(lambda self:      self._get(),
                   lambda self, val: self._set(val),
                   lambda self:      self._del())


class SingleWindow(Property):

    def _del(self):
        self.val.window().close()

    def _closed(self):
        super()._del()

    def _new(self):
        window = super()._new()
        present(window.window())
        notifyCloseEvent(window, self._closed)
        return window

    def _update(self):
        present(self.val.window())
