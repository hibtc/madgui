# encoding: utf-8
"""
Compatibility module for Qt.

Use this module to get consistent Qt imports.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

# this is required for qtconsole (interactive shell) to work:
from qtconsole.qt_loaders import load_qt

import os

api_pref = os.environ.get('PYQT_API') or 'pyqt,pyqt5'
api_opts = api_pref.lower().split(',')

QtCore, QtGui, QtSvg, QT_API = load_qt(api_opts)

Qt = QtCore.Qt
