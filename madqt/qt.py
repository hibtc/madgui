"""
Compatibility module for Qt.

Use this module to get consistent Qt imports.
"""

# this is required for qtconsole (interactive shell) to work:
from qtconsole.qt_loaders import (load_qt, QT_API_PYSIDE,
                                  QT_API_PYQT, QT_API_PYQT5)

api_opts = [QT_API_PYQT, QT_API_PYQT5, QT_API_PYSIDE]

QtCore, QtGui, QtSvg, QT_API = load_qt(api_opts)

Qt = QtCore.Qt
