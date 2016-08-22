# encoding: utf-8
"""
Qt utilities.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import QtCore, QtGui, Qt


def notifyCloseEvent(widget, handler):
    widget.setAttribute(Qt.WA_DeleteOnClose)
    widget.destroyed.connect(handler)


def notifyEvent(widget, name, handler):
    old_handler = getattr(widget, name)
    def new_handler(event):
        handler(event)
        old_handler(event)
    setattr(widget, name, new_handler)
