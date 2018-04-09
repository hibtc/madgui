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

from madgui.qt import Qt, QtCore, QtGui
from madgui.util.collections import List
from madgui.util.qt import monospace
from madgui.util.layout import HBoxLayout


LogRecord = namedtuple('LogRecord', ['time', 'domain', 'text'])


class TextEditSideBar(QtGui.QWidget):

    """Widget that displays line numbers for a QPlainTextEdit."""

    # Thanks to:
    # https://nachtimwald.com/2009/08/19/better-qplaintextedit-with-line-numbers/

    def __init__(self, edit):
        super().__init__(edit)
        self.edit = edit
        self.adjustWidth(1)
        edit.blockCountChanged.connect(self.adjustWidth)
        edit.updateRequest.connect(self.updateContents)

    def paintEvent(self, event):
        edit = self.edit
        font_metrics = edit.fontMetrics()
        block = edit.firstVisibleBlock()
        count = block.blockNumber()
        painter = QtGui.QPainter(self)
        painter.fillRect(event.rect(), edit.palette().base())
        first = True
        while block.isValid():
            count += 1
            block_top = edit.blockBoundingGeometry(block).translated(
                edit.contentOffset()).top()
            if not block.isVisible() or block_top > event.rect().bottom():
                break
            rect = QtCore.QRect(
                0, block_top, self.width(), font_metrics.height())
            self.draw_block(painter, rect, block, first)
            first = False
            block = block.next()
        painter.end()
        super().paintEvent(event)

    def adjustWidth(self, count):
        width = self.calc_width(count)
        if self.width() != width:
            self.setFixedWidth(width)

    def updateContents(self, rect, scroll):
        if scroll:
            self.scroll(0, scroll)
        else:
            self.update()


class LineNumberBar(TextEditSideBar):

    def draw_block(self, painter, rect, block, first):
        count = block.blockNumber()+1
        if count != block.document().blockCount() or block.text():
            painter.drawText(rect, Qt.AlignRight, str(count))

    def calc_width(self, count):
        return self.fontMetrics().width(str(count))


class RecordInfoBar(TextEditSideBar):

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
            count = max([c for c in self.records if c <= count])
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

    def highlight(self, domain, color):
        format = QtGui.QTextCharFormat()
        format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
        format.setBackground(color)
        self.formats[domain] = format

    def setup_logging(self, level=logging.INFO, fmt='%(message)s'):
        # TODO: MAD-X log should be separate from basic logging
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

    def recv_log(self, domain, reader):
        lines = list(reader.read_all())
        if lines:
            text = "\n".join(lines)
            self.records.append(LogRecord(
                time.time(), domain, text))

    def excepthook(self, *args, **kwargs):
        logging.error("".join(traceback.format_exception(*args, **kwargs)))

    def _insert_record(self, index, record):
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

