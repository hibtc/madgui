"""
Logging utils.
"""

# TODO:
# - filter log according to log message type
# - right click context menu: copy
# ? single line ListView overview over all log events ("quick jump")
# ? deselect on single click

import sys
import traceback
import logging
import time
from collections import namedtuple

from madgui.qt import Qt, QtGui
from madgui.util.collections import List
from madgui.util.qt import monospace
from madgui.util.layout import HBoxLayout
from madgui.widget.edit import LineNumberBar


LOGLEVELS = [None, 'CRITICAL', 'ERROR', 'WARNING',  'INFO', 'DEBUG']

LogRecord = namedtuple('LogRecord', ['time', 'domain', 'text'])


class RecordInfoBar(LineNumberBar):

    def __init__(self, edit, records, domains):
        self.records = records
        self.domains = domains
        super().__init__(edit)
        font = self.font()
        font.setBold(True)
        self.setFont(font)
        self.adjustWidth(1)

    def draw_block(self, painter, rect, block, first):
        count = block.blockNumber()+1
        if count in self.records:
            painter.setPen(QtGui.QColor(Qt.black))
        elif first:
            painter.setPen(QtGui.QColor(Qt.gray))
            count = max([c for c in self.records if c <= count], default=None)
        if count in self.records:
            record = self.records[count]
            text = "{} {}:".format(
                time.strftime('%H:%M:%S', time.localtime(record.time)),
                record.domain)
            painter.drawText(rect, Qt.AlignLeft, text)

    def calc_width(self, count):
        width_time = self.fontMetrics().width("23:59:59: ")
        width_kind = max(map(self.fontMetrics().width, self.domains), default=0)
        return width_time + width_kind


class LogWindow(QtGui.QFrame):

    """
    Simple log window based on QPlainTextEdit using ExtraSelection to
    highlight input/output sections with different backgrounds, see:
    http://doc.qt.io/qt-5/qtwidgets-widgets-codeeditor-example.html
    """

    # TODO:
    # - add toggle buttons to show/hide specific domains, and titles+timestamps
    # - A more advanced version could use QTextEdit with QSyntaxHighlighter:
    #   http://doc.qt.io/qt-5/qtwidgets-richtext-syntaxhighlighter-example.html

    def __init__(self, *args):
        super().__init__(*args)
        self.setFont(monospace())
        self.textctrl = QtGui.QPlainTextEdit()
        self.textctrl.setReadOnly(True)
        self.infobar = RecordInfoBar(self.textctrl, {}, set())
        self.linumbar = LineNumberBar(self.textctrl)
        self.setLayout(HBoxLayout([
            self.infobar, self.linumbar, self.textctrl], tight=True))
        self.records = List()
        self.records.insert_notify.connect(self._insert_record)
        self.formats = {}
        self._enabled = {}
        self._domains = set()
        self.loglevel = 'INFO'

    def highlight(self, domain, color):
        format = QtGui.QTextCharFormat()
        format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
        format.setBackground(color)
        self.formats[domain] = format

    def setup_logging(self, level=logging.INFO, fmt='%(message)s'):
        # TODO: MAD-X log should be separate from basic logging
        self.loglevel = logging.getLevelName(level)
        self.logging_enabled = True
        root = logging.getLogger('')
        manager = logging.Manager(root)
        formatter = logging.Formatter(fmt)
        handler = RecordHandler(self.records)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root.level = level
        # store member variables:
        self._log_manager = manager
        sys.excepthook = self.excepthook

    def enable_logging(self, enable):
        self.logging_enabled = enable
        self.set_loglevel(self.loglevel)

    def set_loglevel(self, loglevel):
        self.loglevel = loglevel = loglevel.upper()
        index = LOGLEVELS.index(loglevel)
        if any([self._enable(level, i <= index and self.logging_enabled)
                for i, level in enumerate(LOGLEVELS)]):
            self.rebuild_log()

    def enable(self, domain, enable):
        if self._enable(domain, enable):
            self.rebuild_log()

    def _enable(self, domain, enable):
        if self.enabled(domain) != enable:
            self._enabled[domain] = enable
            return self.has_entries(domain)
        return False

    def enabled(self, domain):
        return self._enabled.get(domain, True)

    def has_entries(self, domain):
        return domain in self._domains

    def recv_log(self, domain, text):
        if text:
            self.records.append(LogRecord(
                time.time(), domain, text))

    def excepthook(self, *args, **kwargs):
        traceback.print_exception(*args, **kwargs)
        logging.error("".join(traceback.format_exception(*args, **kwargs)))

    def rebuild_log(self):
        self.textctrl.clear()
        self.infobar.records.clear()
        self.infobar.domains.clear()
        for record in self.records:
            self._append_log(record)

    def _insert_record(self, index, record):
        self._domains.add(record.domain)
        self._append_log(record)

    def _append_log(self, record):
        if not self.enabled(record.domain):
            return

        self.infobar.records[self.textctrl.document().blockCount()] = record
        self.infobar.domains.add(record.domain)
        if record.domain not in self.formats:
            self.textctrl.appendPlainText(record.text)
            return

        QTextCursor = QtGui.QTextCursor

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

        selection = QtGui.QTextEdit.ExtraSelection()
        selection.format = self.formats[record.domain]
        selection.cursor = cursor

        selections = self.textctrl.extraSelections()
        selections.append(selection)
        self.textctrl.setExtraSelections(selections)
        self.textctrl.ensureCursorVisible()


class RecordHandler(logging.Handler):

    """Handle incoming logging events by adding them to a list."""

    def __init__(self, records):
        super().__init__()
        self.records = records

    def emit(self, record):
        self.records.append(LogRecord(
            record.created,
            record.levelname,
            self.format(record),
        ))

