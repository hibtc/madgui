"""
Qt utilities.
"""

from importlib_resources import path as resource_filename

from madgui.qt import QtGui


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


def present(window, raise_=False):
    """Activate window."""
    window.show()
    window.activateWindow()
    if raise_:
        window.raise_()


def monospace():
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)


def bold():
    font = QtGui.QFont()
    font.setBold(True)
    return font


def load_icon_resource(module, name, format='XPM'):
    with resource_filename(module, name) as filename:
        return QtGui.QIcon(QtGui.QPixmap(str(filename), format))
