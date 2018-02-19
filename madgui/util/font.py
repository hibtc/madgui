"""
Font utilities.
"""

from madgui.qt import QtGui


__all__ = [
    'monospace',
]


def monospace(size=None):
    font = QtGui.QFont("Monospace")
    font.setStyleHint(QtGui.QFont.TypeWriter)
    if size:
        font.setPointSize(size)
    return font
