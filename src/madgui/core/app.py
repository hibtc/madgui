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
    'init_app',
]

import warnings
import traceback
import signal
import sys
from functools import partial

# Must import Qt *before* matplotlib!
from PyQt5.QtCore import QTimer, QCoreApplication

from madgui import __version__


def init_app(argv=None, gui=True):
    """
    Initialize qt runtime, deal with common issues (such as installing an
    exception handler), and return a ``QApplication`` object. If ``gui`` is
    false, return a ``QCoreApplication`` instead.
    """
    warnings.filterwarnings(
        "default", module='(madgui|cpymad|minrpc|pydicti).*')
    set_app_id('hit.madgui')
    init_stdio()
    # QApplication needs a valid argument list:
    if argv is None:
        argv = sys.argv
    if gui:
        from PyQt5.QtWidgets import QApplication
        from madgui.util.qt import load_icon_resource
        from importlib_resources import read_text
        app = QApplication(argv)
        app.setWindowIcon(load_icon_resource('madgui.data', 'icon.xpm'))
        app.setStyleSheet(read_text('madgui.data', 'style.css'))
        # matplotlib must be imported *after* Qt;
        # must be selected before importing matplotlib.backends:
        import matplotlib
        matplotlib.use('Qt5Agg')
    else:
        app = QCoreApplication(argv)
    app.setApplicationName('madgui')
    app.setApplicationVersion(__version__)
    app.setOrganizationName('HIT Betriebs GmbH')
    app.setOrganizationDomain('https://www.klinikum.uni-heidelberg.de/hit')
    # Print uncaught exceptions. This changes the default behaviour on PyQt5,
    # where an uncaught exception would usually cause the program to abort.
    sys.excepthook = traceback.print_exception
    setup_interrupt_handling(app)
    return app


def init_stdio():
    """Prepare sys.stdout according to requirements in madgui's dependencies."""
    # If started as GUI script, there is usually no stdout. Some packages
    # don't like this and raise exceptions, e.g. pyqtconsole. Let's keep them
    # satisfied:
    sys.stdout = sys.stdout or open('madgui.log', 'at', encoding='utf-8')
    sys.stderr = sys.stderr or sys.stdout
    # Fix issue with utf-8 output on STDOUT in non utf-8 terminal.
    if sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def main(argv=None):
    """Run madgui mainloop and exit process when finished."""
    import madgui.core.config as config
    from madgui.core.session import Session
    from madgui.widget.mainwindow import MainWindow
    from docopt import docopt
    app = init_app(argv)
    # Filter arguments understood by Qt before doing our own processing:
    args = app.arguments()[1:]
    opts = docopt(__doc__, args, version=__version__)
    conf = config.load(opts['--config'])
    config.number = conf.number
    session = Session(conf)
    try:
        window = MainWindow(session)
        session.window.set(window)
        window.show()
        # Defer `loadDefault` to avoid creation of a AsyncRead thread before
        # the main loop is entered: (Being in the mainloop simplifies
        # terminating the AsyncRead thread via the QApplication.aboutToQuit
        # signal. Without this, if the setup code excepts after creating the
        # thread the main loop will never be entered and thus aboutToQuit
        # never be emitted, even when pressing Ctrl+C.)
        QTimer.singleShot(0, partial(session.load_default, opts['FILE']))
        exit_code = app.exec_()
    finally:
        session.terminate()
    return sys.exit(exit_code)


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
    QCoreApplication.quit()


def safe_timer(timeout, func, *args, **kwargs):
    """
    Create a timer that is safe against garbage collection and overlapping
    calls. See: http://ralsina.me/weblog/posts/BB974.html
    """
    def timer_event():
        try:
            func(*args, **kwargs)
        finally:
            QTimer.singleShot(timeout, timer_event)
    QTimer.singleShot(timeout, timer_event)


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
