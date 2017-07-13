# encoding: utf-8
"""
Logging utils.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import logging
import threading
import time
from collections import namedtuple

from six import text_type as unicode

from madqt.qt import Qt, QtCore, QtGui
from madqt.core.base import Object, Signal
from madqt.util.collections import List
from madqt.widget.tableview import ColumnInfo, TableView
import madqt.util.font as font


LogRecord = namedtuple('LogRecord', ['time', 'domain', 'text', 'extra'])


class LogWindow(TableView):

    columns = [
        ColumnInfo('Time', lambda record: time.strftime(
            '%H:%M:%S', time.localtime(record.time))),
        ColumnInfo('Domain', 'domain', resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo('Text', 'text'),
    ]

    def __init__(self, parent):
        self.records = List()
        super(LogWindow, self).__init__(parent, self.columns, self.records)
        self.horizontalHeader().hide()
        self._setRowResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.setFont(font.monospace())

    def setup_logging(self, level=logging.INFO,
                      fmt='%(name)s: %(message)s'):
        # TODO: MAD-X log should be separate from basic logging
        stream = TextCtrlStream(self.records, 'Log')
        root = logging.getLogger('')
        manager = logging.Manager(root)
        formatter = logging.Formatter(fmt)
        handler = RecordHandler(self.records)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root.level = level
        # store member variables:
        self._log_stream = stream
        self._log_manager = manager

    def async_reader(self, stream):
        reader = AsyncRead(stream)
        reader.dataReceived.connect(self._log_stream.write)


class RecordHandler(logging.Handler):

    """Handle incoming logging events by adding them to a list."""

    def __init__(self, records):
        super(RecordHandler, self).__init__()
        self.records = records

    def emit(self, record):
        self.records.append(LogRecord(
            record.created,
            record.levelname,
            self.format(record),
            record,
        ))


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
                self.dataReceived.emit(line.decode('utf-8')[:-1])
            except BaseException:
                break


class TextCtrlStream(object):

    """
    Write to a text control.
    """

    def __init__(self, records, domain):
        """Set text control."""
        self._records = records
        self._domain = domain

    def write(self, text):
        """Append text."""
        self._records.append(LogRecord(time.time(), self._domain, text, None))
