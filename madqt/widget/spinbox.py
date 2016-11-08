# encoding: utf-8
"""
Custom spin box widgets.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

import math

from madqt.qt import Qt, QtCore, QtGui

from madqt.core.unit import units, get_raw_label, get_unit, tounit
from madqt.core.base import Signal


def asb_property(name):
    key = '_' + name
    def get(self):
        return getattr(self, key)
    def set(self, value):
        if value != get(self):
            setattr(self, key, value)
            self.updateEdit()
    get.__name__ = str('get_' + name)
    set.__name__ = str('set_' + name)
    return property(get, set)


class AbstractSpinBox(QtGui.QAbstractSpinBox):

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

    valueChanged = Signal(object)

    validator = None

    # imitate QAbstractSpinBox/QSpinBox/QDoubleSpinBox API

    def get_value(self):
        return self._value

    def set_value(self, value, update=True):
        value = self.bound_value(value)
        if value == self._value:
            return
        self._value = value
        self.valueChanged.emit(value)
        if update:
            self.updateEdit()

    def get_range(self):
        return (self.minimum, self.maximum)

    def set_range(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    prefix = asb_property('prefix')
    suffix = asb_property('suffix')
    minimum = asb_property('minimum')
    maximum = asb_property('maximum')
    value = property(get_value, set_value)
    range = property(get_range, set_range)
    step = None

    _prefix = ""
    _suffix = ""
    _minimum = None
    _maximum = None
    _value = None

    #

    def __init__(self):
        super(AbstractSpinBox, self).__init__()
        self.setAlignment(Qt.AlignRight)
        self.editingFinished.connect(self.updateEdit)
        self.lineEdit().textChanged.connect(self.interpretText)

    def stripped(self, text):
        if text.startswith(self.prefix):
            text = text[len(self.prefix):]
        if text.endswith(self.suffix) and self.suffix:
            text = text[:-len(self.suffix)]
        return text.strip()

    def bound_value(self, value):
        if value is None:
            return None
        minimum, maximum = self.minimum, self.maximum
        if minimum is not None and value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return self.round_value(value)

    def round_value(self, value):
        return self.valueFromText(self.textFromValue(value))

    # QAbstractSpinBox replacements (non-virtual methods)

    def interpretText(self):
        edit = self.lineEdit()
        state, text, pos = self.validate(edit.text(), edit.cursorPosition())
        if state == QtGui.QValidator.Acceptable:
            self.set_value(self.valueFromText(text), update=False)

    def updateEdit(self):
        # taken from QAbstractSpinBoxPrivate::updateEdit
        old = self.text()
        new = self.textFromValue(self.value)
        if new == old:
            return
        edit = self.lineEdit()
        pos = edit.cursorPosition()
        sel = len(edit.selectedText())
        sb = edit.blockSignals(True)
        edit.setText(new)
        pos = max(pos, len(self.prefix))
        pos = min(pos, len(new) - len(self.suffix))
        if sel > 0:
            edit.setSelection(pos, sel)
        else:
            edit.setCursorPosition(pos)
        edit.blockSignals(sb)
        self.updateGeometry()

    def selectAll(self):
        if self.value is None:
            self.lineEdit().selectAll()
        else:
            beg = len(self.prefix)
            end = len(self.text()) - len(self.suffix)
            self.lineEdit().setSelection(beg, end-beg)

    def valueFromText(self, text):
        if text == self.specialValueText():
            return None
        return self.parse(self.stripped(text))

    def textFromValue(self, value):
        if value is None:
            return self.specialValueText()
        return self.prefix + self.format(value) + self.suffix

    # QWidget overrides

    def sizeHint(self):
        # copied from the Qt4 C implementation
        QStyle = QtGui.QStyle

        self.ensurePolished()
        fm = self.fontMetrics()
        edit = self.lineEdit()
        height = edit.sizeHint().height()
        width = max(map(fm.width, (
            self.textFromValue(self.typical) + ' ',
            self.textFromValue(self.minimum) + ' ',
            self.textFromValue(self.maximum) + ' ',
            self.textFromValue(self.value) + ' ',
            self.specialValueText() + ' ',
        )))

        width += 2  # cursor blinking space

        hint = QtCore.QSize(width, height)
        extra = QtCore.QSize(35, 6)

        opt = QtGui.QStyleOptionSpinBox()
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
            .expandedTo(QtGui.QApplication.globalStrut()))

    def focusInEvent(self, event):
        self.lineEdit().event(event)
        if event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason):
            self.selectAll()
        # skip QAbstractSpinBox::focusInEvent (which would call the
        # non-virtual selectAll)
        QtGui.QWidget.focusInEvent(self, event)

    def keyPressEvent(self, event):

        if event.key() == Qt.Key_Tab:
            self.editingFinished.emit()
            return

        if event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.editingFinished.emit()
            self.selectAll()
            return

        if event.key() in (Qt.Key_End, Qt.Key_Home):
            edit = self.lineEdit()
            pos = edit.cursorPosition()
            beg = len(self.prefix)
            end = len(self.text()) - len(self.suffix)
            if pos < beg or pos > end:
                # let lineedit handle this
                edit.event(event)
                return
            if event.key() == Qt.Key_End:
                dest = end
            if event.key() == Qt.Key_Home:
                dest = beg
            if event.modifiers() & Qt.ShiftModifier:
                edit.setSelection(pos, dest-pos)
            else:
                edit.setCursorPosition(dest)
            event.accept()
            return

        if event == QtGui.QKeySequence.SelectAll:
            self.selectAll()
            event.accept()
            return

        super(AbstractSpinBox, self).keyPressEvent(event)


    # QAbstractSpinBox overrides

    def fixup(self, text):
        # TODO: fix invalid values
        if not text:
            return self.specialValueText()
        return text

    def validate(self, text, pos):
        # strip prefix
        if not text.startswith(self.prefix):
            return QtGui.QValidator.Invalid, text, pos
        text = text[len(self.prefix):]
        pos -= len(self.prefix)
        if pos < 0:
            pos = 0
        # strip suffix
        if not text.endswith(self.suffix):
            return QtGui.QValidator.Invalid, text, pos
        if self.suffix:
            text = text[:-len(self.suffix)]
        if pos >= len(text):
            pos = len(text)
        # allow empty value
        text = text.strip()
        if text and self.validator is not None:
            state, text, pos = self.validator.validate(text, pos)
        else:
            state = QtGui.QValidator.Acceptable
        # fix prefix/suffix
        text = self.prefix + text + self.suffix
        pos += len(self.prefix)
        return state, text, pos

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
            return QtGui.QAbstractSpinBox.StepNone
        minimum, maximum, value = self.minimum, self.maximum, self.value
        enabled = QtGui.QAbstractSpinBox.StepNone
        if value is None:
            if minimum is not None:
                enabled |= QtGui.QAbstractSpinBox.StepUpEnabled
            if maximum is not None:
                enabled |= QtGui.QAbstractSpinBox.StepDownEnabled
        else:
            wrapping = self.wrapping()
            if wrapping or minimum is None or value > minimum:
                enabled |= QtGui.QAbstractSpinBox.StepDownEnabled
            if wrapping or maximum is None or value > maximum:
                enabled |= QtGui.QAbstractSpinBox.StepUpEnabled
        return enabled


class QuantitySpinBox(AbstractSpinBox):

    _decimals = 4
    _unit = None
    step = 1.0
    typical = 33333333333333333e-33

    decimals = asb_property('decimals')

    def __init__(self, value=None, unit=None):
        super(QuantitySpinBox, self).__init__()
        self.valueChanged.connect(self.update_step)
        self.validator = QtGui.QDoubleValidator()
        self.unit = unit
        if isinstance(value, units.Quantity):
            if self.unit is None:
                self.set_quantity(value)
            else:
                self.set_quantity_checked(value)
        else:
            self.set_magnitude(value)

    # implement AbstractSpinBox specific methods

    def parse(self, text):
        return float(text)

    def format(self, value):
        num_fmt = '{:' + self.fmtspec + '}'
        return num_fmt.format(value)

    @property
    def fmtspec(self):
        return '.{}g'.format(self.decimals)

    def update_step(self, value):
        if value is None or value == 0:
            return
        log = int(math.floor(math.log10(abs(value))))
        self.step = 10.0 ** (log-1)

    # own methods

    def get_magnitude(self):
        return self.value

    def set_magnitude(self, magnitude):
        self.value = magnitude

    def get_unit(self):
        return self._unit

    def set_unit(self, unit):
        self._unit = unit
        self.suffix = "" if unit is None else " " + get_raw_label(unit)
        self.setSpecialValueText(self.suffix)

    def get_quantity(self):
        magnitude = self.magnitude
        unit = self.unit
        if magnitude is None or unit is None:
            return magnitude
        return magnitude * unit

    def set_quantity(self, value):
        self.set_unit(get_unit(value))
        self.set_magnitude(value.magnitude)

    magnitude = property(get_magnitude, set_magnitude)
    quantity = property(get_quantity, set_quantity)
    unit = property(get_unit, set_unit)

    # set magnitude/unit/quantity and check units

    def set_quantity_checked(self, value):
        scaled = tounit(value, self.unit)
        self.set_magnitude(scaled.magnitude)

