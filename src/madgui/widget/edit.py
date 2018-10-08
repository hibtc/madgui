from madgui.qt import Qt, QtCore, QtGui


class LineNumberBar(QtGui.QWidget):

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

    def draw_block(self, painter, rect, block, first):
        count = block.blockNumber()+1
        if count != block.document().blockCount() or block.text():
            painter.drawText(rect, Qt.AlignRight, str(count))

    def calc_width(self, count):
        return self.fontMetrics().width(str(count))
