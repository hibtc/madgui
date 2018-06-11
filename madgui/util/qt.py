"""
Qt utilities.
"""

from importlib_resources import path as resource_filename

from madgui.qt import Qt, QtGui


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


def fit_button(button):
    text = ' ' + button.text() + ' '
    text_size = button.fontMetrics().size(Qt.TextShowMnemonic, text)
    opt = QtGui.QStyleOptionButton()
    opt.initFrom(button)
    opt.rect.setSize(text_size)
    full_size = button.style().sizeFromContents(
        QtGui.QStyle.CT_PushButton, opt, text_size, button)
    button.setMinimumWidth(full_size.width())
    button.setMaximumWidth(full_size.width())


def monospace():
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)


def load_icon_resource(module, name, format='XPM'):
    with resource_filename(module, name) as filename:
        return QtGui.QIcon(QtGui.QPixmap(str(filename), format))
