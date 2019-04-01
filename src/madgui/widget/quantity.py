"""
Utility classes for creating widgets holding physical quantities.
"""

__all__ = [
    'AffixControlBase',
    'DoubleValidator',
    'ExpressionValidator',
    'ValueControlBase',
    'QuantityControlBase',
    'QuantityDisplay',
]

from abc import abstractmethod
import string
import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence, QValidator
from PyQt5.QtWidgets import QLineEdit, QWidget

from cpymad.util import check_expression

from madgui.util.unit import units, get_raw_label, get_unit, tounit
from madgui.util.signal import Signal
from madgui.util.misc import cachedproperty

import madgui.core.config as config


Acceptable = QValidator.Acceptable
Intermediate = QValidator.Intermediate
Invalid = QValidator.Invalid


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


class AffixControlBase:

    """
    Base class for controls showing a prefix/suffix surrounding an editable
    value in a QLineEdit.
    """

    validator = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.line_edit().textChanged.connect(self.interpretText)

    # imitate QAbstractSpinBox/QSpinBox/QDoubleSpinBox API

    def get_value(self):
        return self._value

    def set_value(self, value, update=True):
        value = self.sanitize(value)
        if value == self._value:
            return
        self._value = value
        self.valueChanged.emit(value)
        if update:
            self.updateEdit()

    prefix = asb_property('prefix')
    suffix = asb_property('suffix')
    value = property(get_value, set_value)
    placeholder_text = ""

    _prefix = ""
    _suffix = ""
    _value = None

    # abstract methods

    @abstractmethod
    def sanitize(self, value):
        return value

    @abstractmethod
    def line_edit(self):
        raise NotImplementedError

    @abstractmethod
    def parse(self, value):
        return value

    @abstractmethod
    def format(self, value):
        return format(value)

    # utility methods

    def stripped(self, text):
        if text.startswith(self.prefix):
            text = text[len(self.prefix):]
        if text.endswith(self.suffix) and self.suffix:
            text = text[:-len(self.suffix)]
        return text

    # def text(self):
    #     return self.line_edit().text()

    # QAbstractSpinBox replacements (non-virtual methods)

    def interpretText(self):
        edit = self.line_edit()
        state, text, pos = self.validate(edit.text(), edit.cursorPosition())
        if state == Acceptable:
            self.set_value(self.valueFromText(text), update=False)

    def updateEdit(self):
        # taken from QAbstractSpinBoxPrivate::updateEdit
        old = self.text()
        new = self.textFromValue(self.value)
        if new == old:
            return
        edit = self.line_edit()
        pos = edit.cursorPosition()     # TODO: must use selectionStart()?
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
            beg = 0
            end = len(self.text())
        else:
            beg = len(self.prefix)
            end = len(self.text()) - len(self.suffix)
        self.line_edit().setSelection(beg, end-beg)

    def valueFromText(self, text):
        if text == self.placeholder_text:
            return None
        return self.parse(self.stripped(text))

    def textFromValue(self, value):
        if value is None:
            return self.placeholder_text
        return self.prefix + self.format(value) + self.suffix

    def validate(self, text, pos):
        # strip prefix
        if not text.startswith(self.prefix):
            return Invalid, text, pos
        text = text[len(self.prefix):]
        pos -= len(self.prefix)
        if pos < 0:
            pos = 0
        # strip suffix
        if not text.endswith(self.suffix):
            return Invalid, text, pos
        if self.suffix:
            text = text[:-len(self.suffix)]
        if pos >= len(text):
            pos = len(text)
        # allow empty value
        state, text, pos = self._validate_value(text, pos)
        # fix prefix/suffix
        text = self.prefix + text + self.suffix
        pos += len(self.prefix)
        return state, text, pos

    def _validate_value(self, text, pos):
        if not text or self.validator is None:
            return Acceptable, text, pos
        return self.validator.validate(text, pos)

    # QWidget overrides

    def focusInEvent(self, event):
        edit = self.line_edit()
        if edit is self:
            # avoid infinite recursion
            super().focusInEvent(event)
        else:
            self.line_edit().event(event)
            # skip QAbstractSpinBox::focusInEvent (which would call the
            # non-virtual selectAll)
            QWidget.focusInEvent(self, event)

        if event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason):
            self.selectAll()

    def keyPressEvent(self, event):

        if event.key() in (Qt.Key_End, Qt.Key_Home):
            edit = self.line_edit()
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

        if event == QKeySequence.SelectAll:
            self.selectAll()
            event.accept()
            return

        super().keyPressEvent(event)


class DoubleValidator(QValidator):

    """
    Use this validator instead of QDoubleValidator to avoid allowing
    numbers in the current locale…
    """

    minimum = None
    maximum = None

    _ALLOWED_CHARS = set(string.digits + "eE+-.")
    _INTERMEDIATE = re.compile(r'^[+-]?\d*\.?\d*[eE]?[+-]?\d*$')

    def validate(self, text, pos):
        text = text.replace(",", ".")
        if not (set(text) <= self._ALLOWED_CHARS):
            return Invalid, text, pos
        try:
            value = float(text)
        except ValueError:
            return self._check_invalid(text, pos)
        return self._check_valid(value), text, pos

    def _check_valid(self, value):
        minimum, maximum = self.minimum, self.maximum
        if minimum is not None and value < minimum:
            return Intermediate
        if maximum is not None and value > maximum:
            return Intermediate
        return Acceptable

    def _check_invalid(self, text, pos):
        # TODO: get smarter, i.e. require
        #   - single edit
        #   - at current position
        # or similar? —I guess, that's not worth the effort…
        if self._INTERMEDIATE.match(text):
            return Intermediate, text, pos
        return Invalid, text, pos


class ExpressionValidator(QValidator):

    _ALLOWED_CHARS = set("+-/*^()->._ " + string.ascii_letters + string.digits)

    def validate(self, text, pos):
        return self._validate(text), text, pos

    def _validate(self, text):
        if not self._ALLOWED_CHARS.issuperset(text):
            return Invalid
        try:
            check_expression(text)
            return Acceptable
        except ValueError:
            return Intermediate

    def parse(self, text):
        return text


class ValueControlBase(AffixControlBase):

    """
    Base class for widgets displaying values from an ordered set.
    """

    def get_range(self):
        return (self.minimum, self.maximum)

    def set_range(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    minimum = asb_property('minimum')
    maximum = asb_property('maximum')
    range = property(get_range, set_range)

    _minimum = None
    _maximum = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignRight)

    def sanitize(self, value):
        if not isinstance(value, (float, int)):
            return value
        minimum, maximum = self.minimum, self.maximum
        if minimum is not None and value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return self.round_value(value)

    def round_value(self, value):
        return self.valueFromText(self.textFromValue(value))


class QuantityControlBase(ValueControlBase):

    """
    Base class for widgets displaying physical quantities.
    """

    _unit = None

    def __init__(self, parent=None, value=None, unit=None):
        super().__init__(parent)
        self.validator = DoubleValidator()
        self.unit = unit
        if isinstance(value, units.Quantity):
            if self.unit is None:
                self.set_quantity(value)
            else:
                self.set_quantity_checked(value)
        else:
            self.set_magnitude(value)
        config.number.changed.connect(self.updateEdit)

    def _validate_value(self, text, pos):
        if not text or self.validator is None:
            return Acceptable, text, pos
        self.validator.minimum = self.minimum
        self.validator.maximum = self.minimum
        return self.validator.validate(text, pos)

    def parse(self, text):
        return float(text)

    def format(self, value):
        num_fmt = '{:' + self.fmtspec + '}'
        return num_fmt.format(value)

    @cachedproperty
    def fmtspec(self):
        return config.number.fmtspec

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
        self.placeholder_text = self.suffix
        self.updateEdit()

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


class QuantityDisplay(QuantityControlBase, QLineEdit):

    """
    Readonly line-edit showing a quantity.
    """

    valueChanged = Signal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignRight)
        self.setReadOnly(True)
        self.selectionChanged.connect(self.clear_selectall_pending)

    def line_edit(self):
        return self

    # TODO: make this work for SpinBox as well

    _selectall_pending = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._selectall_pending = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._selectall_pending:
                self._selectall_pending = False
                self.selectAll()
        super().mouseReleaseEvent(event)

    def clear_selectall_pending(self):
        self._selectall_pending = False
