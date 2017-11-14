"""
Compatibility module for Qt.

Use this module to get consistent Qt imports.
"""

# this is required for qtconsole (interactive shell) to work:
from qtconsole.qt_loaders import load_qt

__all__ = [
    'Qt',
    'QtCore',
    'QtGui',
    'QtSvg',
    'QT_API',
    'uic',
]

QtCore, QtGui, QtSvg, QT_API = load_qt(['pyqt5'])
Qt = QtCore.Qt

from PyQt5 import uic
