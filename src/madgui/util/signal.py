"""
This module provides a very lightweight alternative for Qt's signals that is
easier to use in a non-GUI environment since it doesn't require creating and
initializing ``QApplication`` first, nor deriving from ``QObject``.
"""

__all__ = [
    'Signal',
]


class Signal:

    """
    Decorator for lightweight signals to be used in a class context.

    Use as follows:

        >>> class Car:
        ...     gear_changed = Signal()

        >>> car = Car()
        >>> car.gear_changed.connect(lambda gear: print("New gear:", gear))
        >>> car.gear_changed.emit(12)
        New gear: 12

    This works similar to pyqtSignal, but always uses the same connection mode
    for all connected handlers. This can be either:

    - *direct mode*: immediately calls all handlers
    - *queued mode*: schedules handlers for another main loop iteration

    Default is *direct mode*.

    Note that direct mode is similar to ``Qt.DirectConnection`` and queued
    mode similar to ``Qt.QueuedConnection``, but differs in that it merges
    multiple subsequent signal emissions into one (as long as the event has
    not been processed).
    """

    def __init__(self, doc=''):
        self.__doc__ = 'Signal<{}>'.format(doc)
        self._attr = '__signal_' + str(id(self))

    def __repr__(self):
        return self.__doc__

    def __get__(self, instance, owner):
        if instance is None:    # access via class
            return self
        try:
            return getattr(instance, self._attr)
        except AttributeError:
            signal = BoundSignal()
            setattr(instance, self._attr, signal)
            return signal


class BoundSignal:

    """Manages a list of callback handlers."""

    def __init__(self):
        self.handlers = []
        self._invoke = invoke_handlers.__get__(self.handlers)
        self._trigger = self._invoke

    def emit(self, *args):
        """
        Emit signal.

        In *direct mode*: immediately calls all handlers.
        In *queued mode*: schedules handlers for another main loop iteration
        """
        self._trigger(*args)

    def connect(self, handler):
        """Connect a signal handler."""
        self.handlers.append(handler)

    def disconnect(self, handler):
        """Disconnect a previously connected handler."""
        self.handlers.remove(handler)

    def set_queued(self, queued=True):
        """
        Set the signal to *queued mode*, i.e. signal will be emitted in
        another mainloop iteration.

        Note that queued mode requires at least a ``QCoreApplication``.
        """
        is_queued = self.is_queued()
        if queued and not is_queued:
            from madgui.util.qt import Queued
            self._trigger = Queued(self._invoke)
        elif not queued and is_queued:
            self._trigger = self._invoke

    def is_queued(self):
        """Return whether the signal operates in *queued mode*."""
        return self._trigger is self._invoke


def invoke_handlers(handlers, *args):
    """Call each function in a list with the given arguments."""
    for handler in handlers:
        handler(*args)
