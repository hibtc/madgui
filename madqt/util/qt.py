# encoding: utf-8
"""
Qt utilities.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from contextlib import contextmanager

from madqt.qt import QtCore, QtGui, Qt


def notifyCloseEvent(widget, handler):
    """Connect a closeEvent observer."""
    # There are three basic ways to get notified when a window is closed:
    #   - set the WA_DeleteOnClose attribute and connect to the
    #     QWidget.destroyed signal
    #   - use installEventFilter / eventFilter
    #   - hook into the closeEvent method (see notifyEvent below)
    # We use the first option here since it is the simplest:
    widget.setAttribute(Qt.WA_DeleteOnClose)
    widget.destroyed.connect(handler)


def notifyEvent(widget, name, handler):
    """Connect an event listener."""
    old_handler = getattr(widget, name)
    def new_handler(event):
        handler(event)
        old_handler(event)
    setattr(widget, name, new_handler)


@contextmanager
def waitCursor(cursor=QtGui.QCursor(Qt.WaitCursor)):
    QtGui.QApplication.setOverrideCursor(cursor)
    try:
        yield None
    finally:
        QtGui.QApplication.restoreOverrideCursor()
