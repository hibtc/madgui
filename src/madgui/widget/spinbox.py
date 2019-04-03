"""
Custom spin box widgets.
"""

__all__ = [
    'AbstractSpinBox',
    'QuantitySpinBox',
    'ExpressionSpinBox',
]

import math

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (
    QAbstractSpinBox, QApplication, QSizePolicy, QStyle, QStyleOptionSpinBox)

from madgui.widget.quantity import (
    ValueControlBase, QuantityControlBase, ExpressionValidator)
from madgui.util.signal import Signal
import madgui.core.config as config


class AbstractSpinBox(ValueControlBase, QAbstractSpinBox):

    """
    Base class for custom spinbox controls.

    Subclassing :class:`QAbstractSpinBox` or :class:`QDoubleSpinBox` directly
    with PyQt is hard, because they do not expose access to several crucial
    APIs:

        - ``prefix`` and ``suffix`` (QAbstractSpinBox)
        - no null values,
        - can't control `round()`
        - NaN is reset to maximum in `bound()`
        - no unit editing
        - rounding is 'f'-based
    """

    step = None
    typical = None

    #

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.editingFinished.connect(self.updateEdit)
        self.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Preferred)

    # QWidget overrides

    def sizeHint(self):
        # copied from the Qt4 C implementation
        self.ensurePolished()
        fm = self.fontMetrics()
        edit = self.lineEdit()
        height = edit.sizeHint().height()
        width = max(map(fm.width, (
            self.textFromValue(self.typical) + ' ',
            self.textFromValue(self.minimum) + ' ',
            self.textFromValue(self.maximum) + ' ',
            self.textFromValue(self.value) + ' ',
            self.placeholder_text + ' ',
        )))

        width += 2  # cursor blinking space

        hint = QSize(width, height)
        extra = QSize(35, 6)

        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)

        opt.rect.setSize(hint + extra)
        extra += hint - self.style().subControlRect(
            QStyle.CC_SpinBox, opt,
            QStyle.SC_SpinBoxEditField, self).size()

        # get closer to final result by repeating the calculation
        opt.rect.setSize(hint + extra)
        extra += hint - self.style().subControlRect(
            QStyle.CC_SpinBox, opt,
            QStyle.SC_SpinBoxEditField, self).size()
        hint += extra

        opt.rect = self.rect()
        return (
            self.style().sizeFromContents(QStyle.CT_SpinBox, opt, hint, self)
            .expandedTo(QApplication.globalStrut()))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab:
            self.editingFinished.emit()
            return
        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.editingFinished.emit()
            self.selectAll()
            return
        super().keyPressEvent(event)

    # QAbstractSpinBox overrides

    def fixup(self, text):
        # TODO: fix invalid values
        if not text:
            return self.placeholder_text
        return text

    def stepBy(self, steps):
        value = self.value
        if value is None:
            if steps > 0:
                value = self.minimum
                steps -= 1
            elif steps < 0:
                value = self.maximum
                steps += 1
        if steps != 0:
            value += steps * self.step
        self.value = value
        self.selectAll()

    def clear(self):
        self.value = None

    def stepEnabled(self):
        if self.isReadOnly():
            return QAbstractSpinBox.StepNone
        minimum, maximum, value = self.minimum, self.maximum, self.value
        enabled = QAbstractSpinBox.StepNone
        if value is None:
            if minimum is not None:
                enabled |= QAbstractSpinBox.StepUpEnabled
            if maximum is not None:
                enabled |= QAbstractSpinBox.StepDownEnabled
        else:
            wrapping = self.wrapping()
            if wrapping or minimum is None or value > minimum:
                enabled |= QAbstractSpinBox.StepDownEnabled
            if wrapping or maximum is None or value > maximum:
                enabled |= QAbstractSpinBox.StepUpEnabled
        return enabled


class QuantitySpinBox(QuantityControlBase, AbstractSpinBox):

    valueChanged = Signal(object)

    step = 1.0
    typical = 33333333333333333e-33

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.valueChanged.connect(self.update_step)
        self.updateEdit()

    def update_step(self, value):
        if not isinstance(value, float) or value == 0:
            return
        log = int(math.floor(math.log10(abs(value))))
        self.step = 10.0 ** (log-1)

    def line_edit(self):
        return self.lineEdit()

    def updateEdit(self):
        buttons = [QAbstractSpinBox.NoButtons,
                   QAbstractSpinBox.UpDownArrows]
        self.setButtonSymbols(buttons[
            isinstance(self.value, float) and bool(config.number.spinbox)])
        super().updateEdit()


class ExpressionSpinBox(QuantitySpinBox):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validator = ExpressionValidator()

    def stepEnabled(self):
        if isinstance(self.value, float):
            return super().stepEnabled()
        return QAbstractSpinBox.StepNone

    def parse(self, text):
        try:
            return float(text)
        except ValueError:
            return text.strip().lower()

    def format(self, value):
        try:
            return super().format(value)
        except ValueError:
            return str(value)
