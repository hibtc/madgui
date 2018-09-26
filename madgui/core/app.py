"""
madgui - interactive GUI application for MAD-X via cpymad.

Usage:
    madgui [-c CONFIG] [FILE]
    madgui [--help | --version]

Options:
    -c FILE, --config FILE  Set config file
    -h, --help              Show this help
    -v, --version           Show version information

Arguments:
    FILE                    Load this file initially

Contact information:

    Thomas Gläßle <t_glaessle@gmx.de>

Website:

    https://github.com/hibtc/madgui
"""

__all__ = [
    'main',
]

import warnings
import traceback
import signal
import sys
from functools import partial

from importlib_resources import read_binary

from docopt import docopt

from madgui.qt import QtCore, QtGui

from madgui import __version__
from madgui.core.session import Session
from madgui.widget.mainwindow import MainWindow
from madgui.util.qt import load_icon_resource
import madgui.core.config as config


def main(argv=None):
    """Run madgui mainloop and exit process when finished."""
    warnings.filterwarnings(
        "default", module='(madgui|cpymad|minrpc|pydicti).*')
    set_app_id('hit.madgui')
    # Fix issue with utf-8 output on STDOUT in non utf-8 terminal.
    # Note that sys.stdout can be ``None`` if starting as console_script:
    if sys.stdout and sys.stdout.encoding != 'UTF-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    # QApplication needs a valid argument list:
    if argv is None:
        argv = sys.argv
    app = QtGui.qApp = QtGui.QApplication(argv)
    app.setWindowIcon(load_icon_resource('madgui.data', 'icon.xpm'))
    init_app(app)
    # Filter arguments understood by Qt before doing our own processing:
    args = app.arguments()[1:]
    opts = docopt(__doc__, args, version=__version__)
    conf = config.load(opts['--config'])
    config.number = conf.number
    with Session(conf) as session:
        window = MainWindow(session)
        session.window.set(window)
        window.show()
        app.setStyleSheet(read_binary('madgui.data', 'style.css').decode('utf-8'))
        # Defer `loadDefault` to avoid creation of a AsyncRead thread before
        # the main loop is entered: (Being in the mainloop simplifies
        # terminating the AsyncRead thread via the QApplication.aboutToQuit
        # signal. Without this, if the setup code excepts after creating the
        # thread the main loop will never be entered and thus aboutToQuit
        # never be emitted, even when pressing Ctrl+C.)
        QtCore.QTimer.singleShot(
            0, partial(session.load_default, opts['FILE']))
        return sys.exit(app.exec_())


def init_app(app):
    setup_interrupt_handling(app)
    # Print uncaught exceptions. This changes the default behaviour on PyQt5,
    # where an uncaught exception would usually cause the program to abort.
    sys.excepthook = traceback.print_exception


def setup_interrupt_handling(app):
    """
    Setup handling of KeyboardInterrupt (Ctrl-C) for PyQt.

    By default Ctrl-C has no effect in PyQt. For more information, see:

    https://riverbankcomputing.com/pipermail/pyqt/2008-May/019242.html
    https://docs.python.org/3/library/signal.html#execution-of-python-signal-handlers
    http://stackoverflow.com/questions/4938723/what-is-the-correct-way-to-make-my-pyqt-application-quit-when-killed-from-the-console
    """
    signal.signal(signal.SIGINT, interrupt_handler)
    safe_timer(50, lambda: None)


def interrupt_handler(signum, frame):
    """Handle KeyboardInterrupt: quit application."""
    QtGui.QApplication.quit()


def safe_timer(timeout, func, *args, **kwargs):
    """
    Create a timer that is safe against garbage collection and overlapping
    calls. See: http://ralsina.me/weblog/posts/BB974.html
    """
    def timer_event():
        try:
            func(*args, **kwargs)
        finally:
            QtCore.QTimer.singleShot(timeout, timer_event)
    QtCore.QTimer.singleShot(timeout, timer_event)


def set_app_id(appid):
    """
    Set application ID on windows.

    This is needed so that madgui windows will have their own taskbar group
    and not be counted as generic "python" applications.

    See: https://stackoverflow.com/a/1552105/650222
    """
    try:
        from ctypes import windll
    except ImportError:
        return
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
