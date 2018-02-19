"""
This module was historically used as compatibility layer for PyQt4/5.

It was kept after the removal of PyQt4 compatibility - in order to spare me
the necessity to replace most of the ``QtGui`` occurences inside the existing
code with ``QtWidgets``.
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

del types, QtGuiCompat
del QtWidgets, QtPrintSupport
