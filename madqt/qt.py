"""
Compatibility module for Qt. Historically used to achieve compatibility with
PyQt4. Now still to maintain a stable internal API for QtGui.
"""

import types

from PyQt5 import QtCore, QtWidgets, QtGui, QtPrintSupport, uic

__all__ = [
    'Qt',
    'QtCore',
    'QtGui',
    'uic',
]


QtGuiCompat = types.ModuleType('QtGui')
QtGuiCompat.__dict__.update(QtGui.__dict__)
QtGuiCompat.__dict__.update(QtWidgets.__dict__)
QtGuiCompat.__dict__.update(QtPrintSupport.__dict__)
QtGui = QtGuiCompat
Qt = QtCore.Qt
