"""
Core classes for MadQt.

Every object that emits signals has to derive from :class:`Object`.
"""

from functools import partial

from madqt.qt import QtCore


__all__ = [
    'Signal',
    'Cache',
]


Object = QtCore.QObject
try:
    Signal = QtCore.pyqtSignal
except AttributeError:
    Signal = QtCore.Signal


class Cache(Object):

    updated = Signal()

    def __init__(self, callback):
        super().__init__()
        self.data = None
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(partial(self.update, force=True))
        self.callback = callback

    def invalidate(self):
        self.timer.start()

    def update(self, force=False):
        if force or self.timer.isActive():
            self.timer.stop()
            self.data = self.callback()
            self.updated.emit()
        return self.data
