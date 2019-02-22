"""
This module was historically used as compatibility layer for PyQt4/5. It
contains import aliases for PyQt modules.

It was kept after dropping PyQt4 compatibility - in order to spare me
the necessity to replace most of the ``QtGui`` occurences inside the existing
code with ``QtWidgets``.

This module adds no actual functionality whatsoever. Please keep it that way
and add all functions in other modules, such as :mod:`madgui.util.qt`.
"""

__all__ = [
    'Qt',
    'QtCore',
    'QtGui',
    'uic',
]

import types

from PyQt5 import QtCore, QtWidgets, QtGui, QtPrintSupport, uic


QtGuiCompat = types.ModuleType('QtGui')
QtGuiCompat.__dict__.update(QtGui.__dict__)
QtGuiCompat.__dict__.update(QtWidgets.__dict__)
QtGuiCompat.__dict__.update(QtPrintSupport.__dict__)
QtGui = QtGuiCompat
Qt = QtCore.Qt

del types, QtGuiCompat
del QtWidgets, QtPrintSupport
