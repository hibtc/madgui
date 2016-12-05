# encoding: utf-8
"""
MadQt - interactive GUI application for MAD-X via cpymad.

Usage:
    madqt [--config <config>] [FILE]
    madqt [--help | --version]

Options:
    --config=<config>       Set config file
    -h, --help              Show this help
    -v, --version           Show version information

Arguments:
    FILE                    Load this file initially

Contact information:

    Thomas Gläßle <t_glaessle@gmx.de>

Website:

    https://github.com/coldfix/madqt
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import traceback
import signal
import sys

from pkg_resources import resource_string

from docopt import docopt

from madqt.qt import QtCore, QtGui

from madqt import __version__
from madqt.core.mainwindow import MainWindow


__all__ = [
    'main',
]


def main(argv=None):
    """Run MadQt mainloop and exit process when finished."""
    # QApplication needs a valid argument list:
    if argv is None:
        argv = sys.argv
    app = QtGui.QApplication(argv)
    setup_interrupt_handling(app)
    # Print uncaught exceptions. This changes the default behaviour on PyQt5,
    # where an uncaught exception would usually cause the program to abort.
    sys.excepthook = traceback.print_exception
    # Filter arguments understood by Qt before doing our own processing:
    args = app.arguments()[1:]
    # QApplication uses the "real" command line on windows. This means, when
    # invoking MadQt as `python -m madqt ...` we have to strip two more
    # arguments from the left:
    if args[:1] == ['-m']:
        args = args[2:]
    opts = docopt(__doc__, args, version=__version__)
    mainwindow = MainWindow(opts)
    mainwindow.show()
    app.setStyleSheet(resource_string('madqt.data', 'style.css').decode('utf-8'))
    return sys.exit(app.exec_())


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
