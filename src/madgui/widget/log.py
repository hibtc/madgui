"""
This module defines the parts involved in redirecting all logging events to a
window.
"""

__all__ = [
    'LogRecord',
    'RecordInfoBar',
    'LogWindow',
    'RecordHandler',
]

import sys
import traceback
import logging
import time
from collections import namedtuple, deque

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor, QTextFormat
from PyQt5.QtWidgets import QFrame, QPlainTextEdit, QTextEdit

from madgui.util.qt import monospace
from madgui.util.layout import HBoxLayout
from madgui.widget.edit import LineNumberBar


LOGLEVELS = [None, 'CRITICAL', 'ERROR', 'WARNING',  'INFO', 'DEBUG']

LogRecord = namedtuple('LogRecord', ['time', 'domain', 'text'])


class RecordInfoBar(LineNumberBar):

    """
    Widget that shows log domain and time next to the log widget text.

    This class is taylored toward the behaviour of :class:`LogWindow` and
    should not be instanciated from elsewhere.
    """

    def __init__(self, edit, time_format='%H:%M:%S', show_time=True):
        self.records = {}
        self.domains = set()
        self.show_time = show_time
        self.time_format = time_format
        super().__init__(edit)
        font = self.font()
        font.setBold(True)
        self.setFont(font)
        self.adjustWidth(1)
        # Keeps track of the total line number of all appended records. This
        # is needed for looking up previously inserted blocks by line number,
        # even if line numbers have changed, due to the maxlen feature:
        self._curlen = 0

    def enable_timestamps(self, enable: bool):
        """Turn on display of times, recalculate geometry, and redraw."""
        self.show_time = enable
        self.adjustWidth(1)

    def set_timeformat(self, format: str):
        """Set a time display format for use with :func:`time.strftime`,
        recalculate geometry, and redraw."""
        self.time_format = format
        self.adjustWidth(1)

    def draw_block(self, painter, rect, block, first):
        """Draw the info corresponding to a given block (text line) of the text
        document.

        This overrides :class:`LineNumberBar.draw_block`.

        :param QPainter painter: painter for the current widget
        :param QRect rect: clipping rect for the text to be drawn
        :param QTextBlock block: associated text block in the text edit
        :param bool first: indicates the topmost visible block on screen
        """
        total = self.edit.document().blockCount()
        outed = self._curlen - (total-1)
        count = block.blockNumber() + outed
        if count in self.records:
            painter.setPen(QColor(Qt.black))
        elif first:
            painter.setPen(QColor(Qt.gray))
            count = max([c for c in self.records if c <= count], default=None)
        if count in self.records:
            record = self.records[count]
            parts = [record.domain]
            if self.show_time:
                record_time = time.localtime(record.time)
                parts.insert(0, time.strftime(self.time_format, record_time))
            if parts:
                text = ' '.join(parts) + ':' or ''
                painter.drawText(rect, Qt.AlignLeft, text)

    def calc_width(self, count: int = 0) -> int:
        """Calculate the required widget width in pixels.

        :param int count: ignored here

        This overrides :class:`LineNumberBar.calc_width`."""
        fm = self.fontMetrics()
        width_time = fm.width("23:59:59")
        width_kind = max(map(fm.width, self.domains), default=0)
        width_base = fm.width(": ")
        return width_time * bool(self.show_time) + width_kind + width_base

    def add_record(self, record: LogRecord):
        """Called by :class:`LogWindow` when it adds a visible record."""
        self.records[self._curlen] = record
        self.domains.add(record.domain)
        self._curlen += record.text.count('\n') + 1

    def clear(self):
        """Called by :class:`LogWindow` before rebuilding the list of
        displayed records."""
        self._curlen = 0
        self.records.clear()
        self.domains.clear()


class LogWindow(QFrame):

    """
    Simple log window based on QPlainTextEdit using ExtraSelection to
    highlight input/output sections with different backgrounds, see:
    http://doc.qt.io/qt-5/qtwidgets-widgets-codeeditor-example.html
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.setFont(monospace())
        self.textctrl = QPlainTextEdit()
        self.textctrl.setFont(monospace())      # not inherited on windows
        self.textctrl.setReadOnly(True)
        self.textctrl.setUndoRedoEnabled(False)
        self.infobar = RecordInfoBar(self.textctrl)
        self.linumbar = LineNumberBar(self.textctrl)
        self.setLayout(HBoxLayout([
            self.infobar, self.linumbar, self.textctrl], tight=True))
        self.records = []
        self.formats = {}
        self._enabled = {}
        self._domains = set()
        self.loglevel = 'INFO'
        self._maxlen = 0
        self._rec_lines = deque()
        self.default_format = QTextCharFormat()

    @property
    def maxlen(self) -> int:
        """Maximum number of displayed log records. Default is ``0`` which
        means infinite."""
        return self._maxlen

    @maxlen.setter
    def maxlen(self, maxlen: int):
        maxlen = maxlen or 0
        if self._maxlen != maxlen:
            self._maxlen = maxlen
            self._rec_lines = deque(maxlen=maxlen)
            self.rebuild_log()

    def highlight(self, domain: str, color: QColor):
        """Configure log records with the given *domain* to be colorized in
        the given color."""
        format = QTextCharFormat()
        format.setProperty(QTextFormat.FullWidthSelection, True)
        format.setBackground(color)
        self.formats[domain] = format

    def setup_logging(self, level: str = 'INFO', fmt: str = '%(message)s'):
        """Redirect exceptions and :mod:`logging` to this widget."""
        level = (logging.getLevelName(level)
                 if isinstance(level, int) else level.upper())
        self.loglevel = level
        self.logging_enabled = True
        root = logging.getLogger('')
        formatter = logging.Formatter(fmt)
        handler = RecordHandler(self)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root.setLevel(level)
        sys.excepthook = self.excepthook

    def enable_logging(self, enable: bool):
        """Turn on/off display of :mod:`logging` log events."""
        self.logging_enabled = enable
        self.set_loglevel(self.loglevel)

    def set_loglevel(self, loglevel: str):
        """Set minimum log level of displayed log events."""
        self.loglevel = loglevel = loglevel.upper()
        index = LOGLEVELS.index(loglevel)
        if any([self._enable(level, i <= index and self.logging_enabled)
                for i, level in enumerate(LOGLEVELS)]):
            self.rebuild_log()

    def enable(self, domain: str, enable: bool):
        """Turn on/off log records with the given domain."""
        if self._enable(domain, enable):
            self.rebuild_log()

    def _enable(self, domain: str, enable: bool) -> bool:
        """Internal method to turn on/off display of log records with the
        given domain.

        Returns whether calling :meth:`rebuild_log` is necessary."""
        if self.enabled(domain) != enable:
            self._enabled[domain] = enable
            return self.has_entries(domain)
        return False

    def enabled(self, domain: str) -> bool:
        """Return if the given domain is configured to be displayed."""
        return self._enabled.get(domain, True)

    def has_entries(self, domain: str) -> bool:
        """Return if any log records with the given domain have been
        emitted."""
        return domain in self._domains

    def append_from_binary_stream(self, domain, text, encoding='utf-8'):
        """Append a log record from a binary utf-8 text stream."""
        text = text.strip().decode(encoding, 'replace')
        if text:
            self.append(LogRecord(time.time(), domain, text))

    def excepthook(self, *args, **kwargs):
        """Exception handler that prints exceptions and appends a log record
        instead of exiting."""
        traceback.print_exception(*args, **kwargs)
        logging.error("".join(traceback.format_exception(*args, **kwargs)))

    def rebuild_log(self):
        """Clear and reinsert all configured log records into the text
        control.

        This is used internally if the configuration has changed such that
        previously invisible log entries become visible or vice versa."""
        self.textctrl.clear()
        self.infobar.clear()
        shown_records = [r for r in self.records if self.enabled(r.domain)]
        for record in shown_records[-self.maxlen:]:
            self._append_log(record)

    def append(self, record):
        """Add a :class:`LogRecord`. This can be called by users!"""
        self.records.append(record)
        self._domains.add(record.domain)
        if self.enabled(record.domain):
            self._append_log(record)

    def _append_log(self, record):
        """Internal method to insert a displayed record into the underlying
        :class:`QPlainTextEdit`."""
        self.infobar.add_record(record)
        self._rec_lines.append(record.text.count('\n') + 1)

        # NOTE: For some reason, we must use `setPosition` in order to
        # guarantee a absolute, fixed selection (at least on linux). It seems
        # almost if `movePosition(End)` will be re-evaluated at any time the
        # cursor/selection is used and therefore always point to the end of
        # the document.

        cursor = QTextCursor(self.textctrl.document())
        cursor.movePosition(QTextCursor.End)
        pos0 = cursor.position()
        cursor.insertText(record.text + '\n')
        pos1 = cursor.position()

        cursor = QTextCursor(self.textctrl.document())
        cursor.setPosition(pos0)
        cursor.setPosition(pos1, QTextCursor.KeepAnchor)

        selection = QTextEdit.ExtraSelection()
        selection.format = self.formats.get(record.domain, self.default_format)
        selection.cursor = cursor

        selections = self.textctrl.extraSelections()
        if selections:
            # Force the previous selection to end at the current block.
            # Without this, all previous selections are be updated to span
            # over the rest of the document, which dramatically impacts
            # performance because it means that all selections need to be
            # considered even if showing only the end of the document.
            selections[-1].cursor.setPosition(pos0, QTextCursor.KeepAnchor)
        selections.append(selection)
        self.textctrl.setExtraSelections(selections[-self.maxlen:])
        self.textctrl.ensureCursorVisible()

        if self.maxlen:
            # setMaximumBlockCount() must *not* be in effect while inserting
            # the text, because it will mess with the cursor positions and
            # make it nearly impossible to create a proper ExtraSelection!
            num_lines = sum(self._rec_lines)
            self.textctrl.setMaximumBlockCount(num_lines + 1)
            self.textctrl.setMaximumBlockCount(0)


class RecordHandler(logging.Handler):

    """Handler class that is needed for forwarding :mod:`logging` log events
    to :class:`LogWindow`.

    This class is instanciated by :meth:`LogWindow.setup_logging` and there
    should be no need to instanciate it anywhere else."""

    def __init__(self, log_window: LogWindow):
        super().__init__()
        self.log_window = log_window

    def emit(self, record):
        """Override :meth:`logging.Handler.emit` to append to
        :class:`LogWindow`."""
        self.log_window.append(LogRecord(
            record.created,
            record.levelname,
            self.format(record),
        ))
