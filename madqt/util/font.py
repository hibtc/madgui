# encoding: utf-8
"""
Font utilities.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import QtGui


__all__ = [
    'monospace',
]


def monospace(size=None):
    font = QtGui.QFont("Monospace")
    font.setStyleHint(QtGui.QFont.TypeWriter)
    if size:
        font.setPointSize(size)
    return font
