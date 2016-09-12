"""
Core classes for MadQt.

Every object that emits signals has to derive from :class:`Object`.
"""

from madqt.qt import QtCore


__all__ = [
    'Signal',
]


Object = QtCore.QObject
try:
    Signal = QtCore.pyqtSignal
except AttributeError:
    Signal = QtCore.Signal
