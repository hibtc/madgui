"""
Logging utils.
"""

# TODO:
# - filter log according to log message type
# - right click context menu: copy
# ? single line ListView overview over all log events ("quick jump")
# ? deselect on single click

import logging
import threading
import time
from collections import namedtuple
from functools import partial
try:
    from queue import Queue, Empty
except ImportError:     # py2
    from Queue import Queue, Empty

from madgui.qt import Qt, QtCore, QtGui
from madgui.core.base import Object, Signal
from madgui.util.collections import List
from madgui.widget.tableview import ColumnInfo, TableModel, MultiLineDelegate
import madgui.util.font as font


LogRecord = namedtuple('LogRecord', ['time', 'domain', 'title', 'text', 'extra'])

TextInfo = namedtuple('TextInfo', ['text', 'rect', 'font'])


def get_record_text(record):
    return "{} {}:\n{}".format(
        time.strftime('%H:%M:%S', time.localtime(record.time)),
        record.domain,
        record.text)

def get_record_head(record):
    return "{} {}:".format(
        time.strftime('%H:%M:%S', time.localtime(record.time)),
        record.domain)

def get_record_body(record):
    return record.text


class LogWindow(QtGui.QListView):

    columns = [
        ColumnInfo('', 'text')
    ]

    def __init__(self, *args):
        self.records = List()
        super().__init__(*args)
        self.setFont(font.monospace(10))
        self.setModel(TableModel(self.columns, self.records))
        self.setItemDelegate(LogDelegate(self.font()))
        self.setAlternatingRowColors(True)
        self.setUniformItemSizes(False)
        self.setVerticalScrollMode(QtGui.QAbstractItemView.ScrollPerPixel)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.model().layoutChanged.connect(self.scrollToBottom)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clearSelection()

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

    def async_reader(self, domain, stream):
        reader = AsyncRead(stream)
        reader.dataReceived.connect(partial(self.recv_log, reader.queue, domain))

    def recv_log(self, queue, domain):
        lines = list(pop_all(queue))
        if lines:
            text = "\n".join(lines)
            self.records.append(LogRecord(
                time.time(), domain, '<stdout>', text, None))


class LogDelegate(MultiLineDelegate):

    # Basic mechanism from:
    # https://3adly.blogspot.fr/2013/09/qt-custom-qlistview-delegate-with-word.html

    padding = 8
    margin = 4
    corner_radius = 10
    pen_width = 1
    text_flags = Qt.AlignLeft|Qt.AlignTop|Qt.TextWordWrap

    def __init__(self, font):
        self.font = font
        super().__init__()

    def _get_text_info(self, option, index):
        record = index.model().rows[index.row()]
        head_text = get_record_head(record)
        info_text = record.title
        body_text = record.text

        head_font = QtGui.QFont(self.font)
        head_font.setBold(True)
        info_font = QtGui.QFont(self.font)
        body_font = QtGui.QFont(self.font)
        head_fm = QtGui.QFontMetrics(head_font)
        info_fm = QtGui.QFontMetrics(info_font)
        body_fm = QtGui.QFontMetrics(body_font)

        # Note that the given height is 0. That is because boundingRect() will return
        # the suitable height if the given geometry does not fit. And this is exactly
        # what we want.
        width = option.rect.width()-2*self.padding-2*self.margin

        head_rect = head_fm.boundingRect(
            option.rect.left() + self.padding + self.margin,
            option.rect.top() + self.padding + self.margin,
            width, 0,
            self.text_flags, head_text)

        info_rect = info_fm.boundingRect(
            head_rect.right() + self.padding,
            head_rect.top(),
            width-head_rect.width()-self.padding, 0,
            self.text_flags, info_text)

        body_rect = body_fm.boundingRect(
            head_rect.left(),
            max(head_rect.bottom(), info_rect.bottom())  + self.padding,
            width, 0,
            self.text_flags, body_text)

        return (TextInfo(head_text, head_rect, head_font),
                TextInfo(info_text, info_rect, info_font),
                TextInfo(body_text, body_rect, body_font))

    def sizeHint(self, option, index):
        if not index.isValid():
            return QtCore.QSize()
        head, info, body = self._get_text_info(option, index)
        return QtCore.QSize(
            option.rect.width(),
            max(head.rect.height(), info.rect.height()) + body.rect.height()
            + 3*self.padding
            + 2*self.margin)

    def paint(self, painter, option, index):
        if not index.isValid():
            return

        if option.state & QtGui.QStyle.State_Selected:
            fill = option.palette.highlight()
        elif index.row() % 2 == 0:
            fill = option.palette.base()
        else:
            fill = option.palette.alternateBase()
            #fill = option.backgroundBrush

        painter.save()

        # paint background
        painter.fillRect(option.rect, option.palette.base())

        # Qt Drawing a filled rounded rectangle with border:
        # https://stackoverflow.com/a/29196812/650222/
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        path = QtGui.QPainterPath()
        rect = option.rect
        rect = QtCore.QRectF(
            rect.x() + self.margin - 0.5,
            rect.y() + self.margin - 0.5,
            rect.width() - 2*self.margin,
            rect.height() - 2*self.margin)
        path.addRoundedRect(rect, self.corner_radius, self.corner_radius)
        pen = QtGui.QPen(Qt.black, self.pen_width)
        painter.setPen(pen)
        painter.fillPath(path, fill)
        painter.drawPath(path)

        painter.setPen(Qt.black)
        for block in self._get_text_info(option, index):
            painter.setFont(block.font)
            painter.drawText(block.rect, self.text_flags, block.text)

        painter.restore()


def pop_all(queue):
    while True:
        try:
            x = queue.get_nowait()
        except Empty:
            return
        yield x


class RecordHandler(logging.Handler):

    """Handle incoming logging events by adding them to a list."""

    def __init__(self, records):
        super().__init__()
        self.records = records

    def emit(self, record):
        self.records.append(LogRecord(
            record.created,
            record.levelname,
            '{0.name}:{0.lineno} in {0.funcName}()'.format(record),
            self.format(record),
            record,
        ))


class AsyncRead(Object):

    """
    Write to a text control.
    """

    dataReceived = Signal()

    def __init__(self, stream):
        super().__init__()
        self.queue = Queue()
        self.stream = stream
        self.thread = threading.Thread(target=self._readLoop)
        self.thread.daemon = True   # don't block program exit
        self.thread.start()

    def _readLoop(self):
        # The file iterator seems to be buffered:
        for line in iter(self.stream.readline, b''):
            self.queue.put(line.decode('utf-8', 'replace')[:-1])
            self.dataReceived.emit()
