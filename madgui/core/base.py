"""
Core classes for madgui.

Every object that emits signals has to derive from :class:`Object`.
"""

__all__ = [
    'Signal',
    'Object',
]

from madgui.qt import QtCore


Object = QtCore.QObject
Signal = QtCore.pyqtSignal
