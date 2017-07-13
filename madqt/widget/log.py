# encoding: utf-8
"""
Logging utils.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import logging
import threading

from six import text_type as unicode

from madqt.qt import Qt, QtCore, QtGui
from madqt.core.base import Object, Signal
import madqt.util.font as font


class LogWindow(QtGui.QPlainTextEdit):

    def __init__(self, *args):
        super(LogWindow, self).__init__(*args)
        self.setFont(font.monospace())
        self.setReadOnly(True)

    def setup_logging(self, level=logging.INFO,
                      fmt='%(asctime)s %(levelname)s %(name)s: %(message)s',
                      datefmt='%H:%M:%S'):
        # TODO: MAD-X log should be separate from basic logging
        stream = TextCtrlStream(self)
        root = logging.getLogger('')
        manager = logging.Manager(root)
        formatter = logging.Formatter(fmt, datefmt)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root.level = level
        # store member variables:
        self._log_stream = stream
        self._log_manager = manager

    def async_reader(self, stream):
        reader = AsyncRead(stream)
        reader.dataReceived.connect(self._log_stream.write)


class AsyncRead(Object):

    """
    Write to a text control.
    """

    dataReceived = Signal(unicode)
    closed = Signal()

    def __init__(self, stream):
        super(AsyncRead, self).__init__()
        self.stream = stream
        self.thread = threading.Thread(target=self._readLoop)
        self.thread.start()

    def _readLoop(self):
        # The file iterator seems to be buffered:
        for line in iter(self.stream.readline, b''):
            try:
                self.dataReceived.emit(line.decode('utf-8'))
            except BaseException:
                break


class TextCtrlStream(object):

    """
    Write to a text control.
    """

    def __init__(self, ctrl):
        """Set text control."""
        self._ctrl = ctrl

    def write(self, text):
        """Append text."""
        self._ctrl.appendPlainText(text.rstrip())
