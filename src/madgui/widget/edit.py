"""
Provides an editor control with line numbers.
"""

__all__ = [
    'LineNumberBar',
    'TextEditDialog',
]

from PyQt5.QtCore import QRect, Qt, QSize
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget, QDialog, QDialogButtonBox, QPlainTextEdit

from madgui.util.qt import monospace
from madgui.util.layout import VBoxLayout, HBoxLayout


class LineNumberBar(QWidget):

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
        painter = QPainter(self)
        painter.fillRect(event.rect(), edit.palette().base())
        first = True
        while block.isValid():
            count += 1
            block_top = edit.blockBoundingGeometry(block).translated(
                edit.contentOffset()).top()
            if not block.isVisible() or block_top > event.rect().bottom():
                break
            rect = QRect(0, block_top, self.width(), font_metrics.height())
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

    def draw_block(self, painter, rect, block, first):
        """Draw the info corresponding to a given block (text line) of the text
        document.

        This method can be overriden by subclasses (with care).

        :param QPainter painter: painter for the current widget
        :param QRect rect: clipping rect for the text to be drawn
        :param QTextBlock block: associated text block in the text edit
        :param bool first: indicates the topmost visible block on screen
        """
        count = block.blockNumber()+1
        if count != block.document().blockCount() or block.text():
            painter.drawText(rect, Qt.AlignRight, str(count))

    def calc_width(self, count):
        """Calculate the widget width in pixels required to hold line numbers
        up to the given ``count``."""
        return self.fontMetrics().width(str(count))


class TextEditDialog(QDialog):

    """Text edit dialog with line numbers."""

    def __init__(self, text, apply_callback):
        super().__init__()
        self.apply_callback = apply_callback
        self.textbox = QPlainTextEdit()
        self.textbox.setFont(monospace())
        self.linenos = LineNumberBar(self.textbox)
        buttons = QDialogButtonBox()
        buttons.addButton(buttons.Ok).clicked.connect(self.accept)
        self.setLayout(VBoxLayout([
            HBoxLayout([self.linenos, self.textbox], tight=True),
            buttons,
        ]))
        self.setSizeGripEnabled(True)
        self.resize(QSize(600, 400))
        self.textbox.appendPlainText(text)

    def accept(self):
        if self.apply():
            super().accept()

    def apply(self):
        text = self.textbox.toPlainText()
        return self.apply_callback(text)
