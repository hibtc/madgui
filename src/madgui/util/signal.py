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

    This works similar to pyqtSignal, but always calls handlers immediately
    (equivalent to ``Qt.DirectConnection``), and does not allow overrides.
    """

    def __init__(self, doc=''):
        self._doc = 'Signal<{}>'.format(doc)
        self._attr = '__signal_' + str(id(self))

    def __repr__(self):
        return self._doc

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

    """
    Manages a list of callback handlers.

    Usually you won't need to create instances of this class manually.
    """

    def __init__(self):
        self.handlers = []

    def emit(self, *args):
        """Emit signal. Directly calls all handlers."""
        for handler in self.handlers:
            handler(*args)

    def connect(self, handler):
        """Connect a signal handler."""
        self.handlers.append(handler)

    def disconnect(self, handler):
        """Disconnect a previously connected handler."""
        self.handlers.remove(handler)
