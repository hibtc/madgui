"""
Qt utilities.
"""

import functools
from importlib_resources import path as resource_filename

from madgui.qt import QtGui, QtCore
from madgui.util.collections import Bool
from madgui.util.misc import cachedproperty, memoize


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
        return old_handler(event)
    setattr(widget, name, new_handler)


def eventFilter(object, events):
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

    See ``QtCore.QEvent`` for possible events.
    """
    filter = EventFilter(events)
    object.installEventFilter(filter)
    return filter


class EventFilter(QtCore.QObject):

    """Implements an event filter from a lookup table. It is preferred to use
    the :func:`eventFilter` function rather than instanciating this class
    directly."""

    def __init__(self, events):
        super().__init__()
        self.event_table = {
            getattr(QtCore.QEvent, k): v
            for k, v in events.items()
        }

    def eventFilter(self, object, event):
        dispatch = self.event_table.get(event.type())
        return bool(dispatch and dispatch(object, event))


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
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(func)

    def __call__(self):
        """Schedule the handler invocation for another mainloop iteration."""
        self.timer.start()

    @classmethod
    def method(cls, func):
        """Decorator for a queued method."""
        return property(memoize(functools.wraps(func)(
            lambda self: cls(func.__get__(self)))))
