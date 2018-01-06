"""
Qt utilities.
"""

from contextlib import contextmanager

from madqt.qt import QtGui, Qt


def notifyCloseEvent(widget, handler):
    """Connect a closeEvent observer."""
    # There are three basic ways to get notified when a window is closed:
    #   - set the WA_DeleteOnClose attribute and connect to the
    #     QWidget.destroyed signal
    #   - use installEventFilter / eventFilter
    #   - hook into the closeEvent method (see notifyEvent below)
    # We use the first option here since it is the simplest:
    notifyEvent(widget, 'closeEvent', lambda event: handler())


def notifyEvent(widget, name, handler):
    """Connect an event listener."""
    old_handler = getattr(widget, name)
    def new_handler(event):
        handler(event)
        old_handler(event)
    setattr(widget, name, new_handler)


@contextmanager
def waitCursor(cursor=None):
    if cursor is None:
        cursor = QtGui.QCursor(Qt.WaitCursor)
    QtGui.QApplication.setOverrideCursor(cursor)
    try:
        yield None
    finally:
        QtGui.QApplication.restoreOverrideCursor()


def present(window, raise_=False):
    """Activate window."""
    window.show()
    window.activateWindow()
    if raise_:
        window.raise_()
