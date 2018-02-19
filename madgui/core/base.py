"""
Core classes for madgui.

Every object that emits signals has to derive from :class:`Object`.
"""

from madgui.qt import QtCore


__all__ = [
    'Signal',
    'Cache',
]


Object = QtCore.QObject
Signal = QtCore.pyqtSignal


class Cache(Object):

    """
    Cached state that can be invalidated. Invalidation triggers recomputation
    in the main loop at the next idle time.
    """

    updated = Signal()      # emitted after update
    invalid = False         # prevents invalidation during callback()

    def __init__(self, callback):
        super().__init__()
        self.data = None
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.update)
        self.callback = callback

    def invalidate(self):
        if not self.invalid:
            self.invalid = True
            self.timer.start()

    def update(self, force=False):
        if force or self.invalid:
            self.timer.stop()
            self.invalid = True     # prevent repeated invalidation in callback
            self.data = self.callback()
            self.invalid = False    # clear AFTER update
            self.updated.emit()
        return self.data
