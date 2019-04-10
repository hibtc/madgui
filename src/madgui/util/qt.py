"""
Miscellaneous utilities for programming with the Qt framework.
"""

__all__ = [
    'notifyEvent',
    'eventFilter',
    'EventFilter',
    'present',
    'monospace',
    'bold',
    'load_ui',
    'load_icon_resource',
    'SingleWindow',
    'Queued',
]

import functools
from importlib_resources import path as resource_filename, open_binary

from PyQt5.QtCore import QEvent, QObject, QTimer
from PyQt5.QtGui import QFont, QFontDatabase, QIcon, QPixmap
from PyQt5 import uic

from madgui.util.collections import Bool
from madgui.util.misc import cachedproperty, memoize


def notifyEvent(widget, name, handler):
    """Connect the handler function to be called when the widget receives an
    event specified by the given name."""
    # This is implemented using `EventFilter`. The alternative would be to
    #   - either overwrite the xxxEvent method on the object, or
    #   - for closeEvent specifically, set the WA_DeleteOnClose attribute and
    #     connect to the QWidget.destroyed signal.
    # However, either method should be avoided due to their disadvantages:
    #   - overwriting methods on the object makes it impossible to cleanly
    #     remove a handler, and may creates unneeded long-lasting reference
    #     cycles on the python side, deepens the call-stack for handlers,
    #     and only works with some events. For example the ``event()`` method
    #     seems to be unimpressed by attempts to change it on the object.
    #   - WA_DeleteOnClose alters the lifetime of the parent widget and can
    #     lead to unforseen side-effects, and is of course only available for
    #     a single event type (Close) anyway
    # Setting a parent is required to prevent the filter from being garbage
    # collected immediately:
    return eventFilter(widget, {
        name: lambda obj, evt: obj is widget and handler() and False,
    }, parent=widget)


def eventFilter(object, events, parent=None):
    """
    Subscribe to events from ``object`` and dispatch via ``events`` lookup
    table. Callbacks are invoked with two parameters ``(object, event)`` and
    should return a false-ish value. A true-ish value will stop the event from
    being processed further.

    Example usage:

    >>> self.event_filter = eventFilter(window, {
    ...     'WindowActivate': self._on_window_activate,
    ...     'Close': self._on_window_close))
    ... })

    (Note that it is important to store the reference to the event filter
    somewhere - otherwise it may be garbage collected.)

    See ``QEvent`` for possible events.
    """
    filter = EventFilter(events, parent)
    object.installEventFilter(filter)
    return filter


class EventFilter(QObject):

    """Implements an event filter from a lookup table. It is preferred to use
    the :func:`eventFilter` function rather than instanciating this class
    directly."""

    def __init__(self, events, parent=None):
        super().__init__(parent)
        self.event_table = {
            getattr(QEvent, k): v
            for k, v in events.items()
        }

    def eventFilter(self, object, event):
        dispatch = self.event_table.get(event.type())
        return bool(dispatch and dispatch(object, event))

    def uninstall(self):
        self.parent().removeEventFilter(self)


def present(window, raise_=False):
    """Activate window and bring to front."""
    window.show()
    window.activateWindow()
    if raise_:
        window.raise_()


def monospace():
    """Return a fixed-space ``QFont``."""
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)


def bold():
    """Return a bold ``QFont``."""
    font = QFont()
    font.setBold(True)
    return font


def load_ui(widget, package, filename):
    """
    Initialize widget from ``.uic`` file loaded from the given package.

    This function is for loading GUIs that were developed using the qt-designer
    rapid development tool which creates ``.uic`` description files. These can
    be saved in the same package alongside the corresponding python code. Now,
    in the class that implements the widget, use this function as follows::

        class MyWidget(QWidget):

            def __init__(self):
                super().__init__()
                load_ui(self, __package__, 'mywidget.uic')
    """
    with open_binary(package, filename) as f:
        uic.loadUi(f, widget)


def load_icon_resource(module, name, format='XPM'):
    """Load an icon distributed with the given python package. Returns a
     ``QPixmap``."""
    with resource_filename(module, name) as filename:
        return QIcon(QPixmap(str(filename), format))


class Property:

    """Internal class for cached properties. Should be simplified and
    rewritten. Currently only used as base class for ``SingleWindow``. Do not
    use for new code."""

    def __init__(self, construct):
        self.construct = construct
        self.holds_value = Bool(False)

    # porcelain

    @classmethod
    def factory(cls, func):
        return cachedproperty(functools.wraps(func)(
            lambda self: cls(func.__get__(self))))

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
        val = self.construct()
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

    """
    Decorator for widget constructor methods. It manages the lifetime of the
    widget to ensure that only one is active at the same time.
    """

    def _del(self):
        self.val.close()

    def _closed(self):
        if self.holds_value():
            super()._del()

    def _new(self):
        window = super()._new()
        present(window.window())
        notifyEvent(window, 'Close', self._closed)
        return window

    def _update(self):
        present(self.val.window())


class Queued:

    """
    A queued trigger. Calling the trigger will invoke the handler function
    in another mainloop iteration.

    Calling the trigger multiple times before the handler was invoked (e.g.
    within the same mainloop iteration) will result in only a *single* handler
    invocation!

    This can only be used with at least a ``QCoreApplication`` instanciated.
    """

    def __init__(self, func):
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(func)

    def __call__(self):
        """Schedule the handler invocation for another mainloop iteration."""
        self.timer.start()

    @classmethod
    def method(cls, func):
        """Decorator for a queued method, i.e. a method that when called,
        actually runs at a later time."""
        return property(memoize(functools.wraps(func)(
            lambda self: cls(func.__get__(self)))))
