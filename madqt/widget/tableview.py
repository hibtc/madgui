# encoding: utf-8
"""
Table widget specified by column behaviour.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from inspect import getmro

from six import (python_2_unicode_compatible,
                 text_type as unicode,
                 string_types as basestring)

from madqt.qt import QtCore, QtGui, Qt
from madqt.core.base import Object, Signal
from madqt.core.unit import Expression
from madqt.core.config import NumberFormat
from madqt.util.layout import HBoxLayout
from madqt.util.misc import rw_property
from madqt.util.collections import List
from madqt.util.enum import Enum
from madqt.widget.spinbox import QuantitySpinBox
from madqt.widget.quantity import DoubleValidator as _DoubleValidator

import madqt.core.unit as unit


__all__ = [
    'ColumnInfo',
    'TableModel',
    'TableView',
]


defaultTypes = {}       # default {type: value proxy} mapping


# TODO: more consistent behaviour/feel of controls: Quantity vs Bare


class ColumnInfo(object):

    """Column specification for a table widget."""

    types = defaultTypes

    def __init__(self, title, getter, resize=None, types=None, padding=0,
                 **kwargs):
        """
        :param str title: column title
        :param callable getter: item -> :class:`ValueProxy`
        :param QtGui.QHeaderView.ResizeMode resize:
        :param int padding:
        :param dict kwargs: arguments for ``getter``, e.g. ``editable``
        """
        self.title = title
        self.getter = getter
        self.resize = resize
        self.padding = padding
        self.kwargs = kwargs
        if types is not None:
            self.types = types

    def valueProxy(self, item):
        if isinstance(self.getter, basestring):
            value = getattr(item, self.getter)
        else:
            value = self.getter(item)
        if isinstance(value, ValueProxy):
            return value
        return makeValue(value, self.types, **self.kwargs)


class TableModel(QtCore.QAbstractTableModel):

    """
    Table data model.

    Column specifications are provided as :class:`ColumnInfo` instances. The
    data can be accessed and changed via the list-like :attribute:`rows`.
    """

    try:
        baseFlags = Qt.ItemNeverHasChildren
    except AttributeError:
        baseFlags = 0           # Qt4

    def __init__(self, columns, data=None):
        super(TableModel, self).__init__()
        self.columns = columns
        self._rows = List() if data is None else data
        self._rows.update_before.connect(self._update_prepare)
        self._rows.update_after.connect(self._update_finalize)

    def _update_prepare(self, slice, old_values, new_values):
        self.layoutAboutToBeChanged.emit()

    def _update_finalize(self, slice, old_values, new_values):
        self.layoutChanged.emit()

    # data accessors

    @property
    def rows(self):
        return self._rows

    @rows.setter
    def rows(self, rows):
        self._rows[:] = rows

    def value(self, index):
        column = self.columns[index.column()]
        item = self.rows[index.row()]
        return column.valueProxy(item)

    # QAbstractTableModel overrides

    def columnCount(self, parent):
        return len(self.columns)

    def rowCount(self, parent):
        return len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        return self.value(index).data(role)

    def flags(self, index):
        if not index.isValid():
            return super(TableModel, self).flags(index)
        return self.value(index).flags() | self.baseFlags

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section].title
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        proxy = self.value(index)
        changed = proxy.setData(value, role)
        if changed:
            self.dataChanged.emit(index, index)
        return changed


class TableView(QtGui.QTableView):

    """A table widget using a :class:`TableModel` to handle the data."""

    _default_resize_modes = [QtGui.QHeaderView.ResizeToContents,
                             QtGui.QHeaderView.Stretch]

    selectionChangedSignal = Signal()

    def __init__(self, parent=None, columns=None, **kwargs):
        """Initialize with list of :class:`ColumnInfo`."""
        super(TableView, self).__init__(parent, **kwargs)
        self.verticalHeader().hide()
        self.setItemDelegate(TableViewDelegate())
        self.setAlternatingRowColors(True)
        if columns is not None:
            self.set_columns(columns)
        NumberFormat.changed.connect(self.format_changed)

    def format_changed(self):
        # NOTE: this is only okay as long as there is only a single view for
        # each model (otherwise the signals will be emitted multiple times!):
        self.model().layoutAboutToBeChanged.emit()
        self.model().layoutChanged.emit()

    def set_columns(self, columns, data=None):
        self.setModel(TableModel(columns, data))
        for index, column in enumerate(columns):
            resize = (self._default_resize_modes[index > 0]
                      if column.resize is None
                      else column.resize)
            self._setColumnResizeMode(index, resize)

    def selectionChanged(self, selected, deselected):
        super(TableView, self).selectionChanged(selected, deselected)
        self.selectionChangedSignal.emit()

    @property
    def rows(self):
        """List-like access to the data."""
        return self.model().rows

    @rows.setter
    def rows(self, rows):
        """List-like access to the data."""
        self.model().rows = rows

    def removeSelectedRows(self):
        # TODO: delete all in one operation
        for idx in sorted(self.selectedIndexes(), reverse=True, key=lambda idx: idx.row()):
            # TODO: these should be called from the model…
            row = idx.row()
            self.model().beginRemoveRows(idx.parent(), row, row)
            del self.rows[row]
            self.model().endRemoveRows()

    def _columnContentWidth(self, column):
        return max(self.sizeHintForColumn(column),
                   self.horizontalHeader().sectionSizeHint(column))

    def sizeHint(self):
        # FIXME: (low priority) This works accurately (as expected) on PyQt5,
        # but somehow gives slightly too much space on PyQt4:
        content_width = sum(map(self._columnContentWidth,
                                range(len(self.model().columns))))
        margins_width = (self.contentsMargins().left() +
                         self.contentsMargins().right())
        scrollbar_width = self.verticalScrollBar().width()
        total_width = (margins_width +
                       content_width +
                       scrollbar_width)
        height = super(TableView, self).sizeHint().height()
        return QtCore.QSize(total_width, height)

    def sizeHintForColumn(self, column):
        return (super(TableView, self).sizeHintForColumn(column)
                + self.model().columns[column].padding)

    @property
    def _setColumnResizeMode(self):
        header = self.horizontalHeader()
        try:
            return header.setResizeMode
        except AttributeError:  # PyQt5
            return header.setSectionResizeMode


class TableViewDelegate(QtGui.QStyledItemDelegate):

    # NOTE: The QItemEditorFactory/QItemEditorCreatorBase has some problems
    # regarding registration and creation of QVariant types for custom python
    # types, so we use QItemDelegate as a simpler replacement.

    def delegate(self, index):
        valueProxy = index.model().value(index)
        return (not valueProxy.editable and ReadOnlyDelegate() or
                valueProxy.delegate() or
                super(TableViewDelegate, self))

    def createEditor(self, parent, option, index):
        return self.delegate(index).createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        return self.delegate(index).setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        return self.delegate(index).setModelData(editor, model, index)

    def updateEditorGeometry(self, editor, option, index):
        return self.delegate(index).updateEditorGeometry(editor, option, index)


# Value types


# TODO: rename to ItemProxy (or ItemDelegate if that were available).
@python_2_unicode_compatible
class ValueProxy(Object):

    """Wrap a value of a specific type for string rendering and editting."""

    default = ""
    fmtspec = ''
    editable = False
    dataChanged = Signal(object)
    types = defaultTypes
    textbrush = None

    # data role, see: http://doc.qt.io/qt-5/qt.html#ItemDataRole-enum
    roles = {
        # general purpose roles
        Qt.DisplayRole:                 'display',
        Qt.DecorationRole:              'decoration',
        Qt.EditRole:                    'edit',
        Qt.ToolTipRole:                 'toolTip',
        Qt.StatusTipRole:               'statusTip',
        Qt.WhatsThisRole:               'whatsThis',
        Qt.SizeHintRole:                'sizeHint',
        # appearance and meta data
        Qt.FontRole:                    'font',
        Qt.TextAlignmentRole:           'textAlignment',
        Qt.BackgroundRole:              'background',
        Qt.BackgroundColorRole:         'backgroundColor',
        Qt.ForegroundRole:              'foreground',
        #Qt.TextColorRole:               'textColor',   # = ForegroundRole
        Qt.CheckStateRole:              'checkState',
        Qt.InitialSortOrderRole:        'initialSortOrder',
        # Accessibility roles
        Qt.AccessibleTextRole:          'accessibleText',
        Qt.AccessibleDescriptionRole:   'accessibleDescription',
    }

    def __init__(self, value,
                 # keyword-only arguments:
                 default=None,
                 editable=None,
                 fmtspec=None,
                 types=None,
                 textcolor=None):
        """Store the value."""
        super(ValueProxy, self).__init__()
        if default is not None: self.default = default
        if editable is not None: self.editable = editable
        if fmtspec is not None: self.fmtspec = fmtspec
        if types is not None: self.types = types
        if textcolor is not None: self.textbrush = QtGui.QBrush(textcolor)
        self.value = value

    def __str__(self):
        """Render the value."""
        return self.display()

    def __repr__(self):
        return "{}({})".format(
            self.__class__.__name__,
            self.display())

    def data(self, role):
        getter_name = self.roles.get(role, '')
        getter_func = getattr(self, getter_name, lambda: None)
        return getter_func()

    def setData(self, value, role=Qt.EditRole):
        if self.editable and role == Qt.EditRole:
            self.value = value
            self.dataChanged.emit(self.value)
            return True
        return False

    def flags(self):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        # Always editable with ReadOnlyDelegate
        flags |= Qt.ItemIsEditable
        return flags

    def delegate(self):
        return None

    # role query functions

    def display(self):
        """Render the value as string."""
        if self.value is None:
            return ""
        return format(self.value, self.fmtspec)

    def edit(self):
        return self.default if self.value is None else self.value

    def checkState(self):
        checked = self.checked()
        if checked is None:
            return None
        return Qt.Checked if checked else Qt.Unchecked

    def checked(self):
        return None

    def textAlignment(self):
        return Qt.AlignLeft | Qt.AlignVCenter

    def foreground(self):
        return self.textbrush

    # TODO: delegate functions (initiateEdit / createEditor)


class StringValue(ValueProxy):

    """Bare string value."""

    pass


class QuotedStringValue(StringValue):

    """String value, but format with enclosing quotes."""

    def display(self):
        """Quote string."""
        if self.value is None:
            return ""
        return repr(self.value).lstrip('u')


class FloatValue(ValueProxy):

    """Float value."""

    default = 0.0

    def textAlignment(self):
        return NumberFormat.align | Qt.AlignVCenter

    def delegate(self):
        return FloatDelegate()

    @rw_property
    def fmtspec(self):
        return NumberFormat.fmtspec


class IntValue(ValueProxy):

    """Integer value."""

    default = 0

    def textAlignment(self):
        return NumberFormat.align | Qt.AlignVCenter


class BoolValue(ValueProxy):

    """Boolean value."""

    default = False

    # FIXME: distinguish `None` values, gray out?
    def get_value(self):
        return self._value
    def set_value(self, value):
        self._value = self.default if value is None else value
    value = property(get_value, set_value)

    def checked(self):
        return self.value

    def flags(self):
        base_flags = super(BoolValue, self).flags()
        return base_flags & ~Qt.ItemIsEditable | Qt.ItemIsUserCheckable

    def setData(self, value, role):
        if role == Qt.CheckStateRole:
            role = Qt.EditRole
            value = value == Qt.Checked
        return super(BoolValue, self).setData(value, role)


# TODO: use UI units
class QuantityValue(FloatValue):

    def __init__(self, value, **kwargs):
        if value is not None:
            self.unit = unit.get_unit(value)
        else:
            self.unit = unit.get_unit(kwargs.get('default'))
        super(QuantityValue, self).__init__(value, **kwargs)

    @property
    def value(self):
        if self.magnitude is None or self.unit is None:
            return self.magnitude
        return self.magnitude * self.unit

    @value.setter
    def value(self, value):
        self.magnitude = unit.strip_unit(value, self.unit)

    def display(self):
        value = self.value
        units = self.unit
        if value is None:
            return "" if units is None else unit.get_raw_label(units)
        if isinstance(self.value, (float, unit.units.Quantity)):
            return unit.format_quantity(self.value, self.fmtspec)
        return format(self.value)

    def delegate(self):
        return QuantityDelegate(self.unit)


class ListValue(ValueProxy):

    """List value."""

    def display(self):
        return '[{}]'.format(
            ", ".join(map(self.formatValue, self.value)))

    def formatValue(self, value):
        return makeValue(value, self.types).display()

    def textAlignment(self):
        return NumberFormat.align | Qt.AlignVCenter

    def delegate(self):
        return ListDelegate()


class EnumValue(StringValue):

    def __init__(self, value, **kwargs):
        self.enum = type(value)
        super(EnumValue, self).__init__(value, **kwargs)

    def delegate(self):
        return EnumDelegate(self.enum)


defaultTypes.update({
    float: FloatValue,
    int: IntValue,
    bool: BoolValue,
    unicode: StringValue,
    bytes: StringValue,
    list: ListValue,                        # TODO: VECTOR vs MATRIX…
    unit.units.Quantity: QuantityValue,
    Expression: QuantityValue,
    Enum: EnumValue,
})


# makeValue

def makeValue(value, types=defaultTypes, **kwargs):
    types = _setdefault(types, defaultTypes)
    try:
        match = _get_best_base(value.__class__, types)
    except ValueError:
        factory = ValueProxy
    else:
        factory = types[match]
    return factory(value, types=types, **kwargs)


def _get_best_base(cls, bases):
    bases = tuple(base for base in bases if issubclass(cls, base))
    mro = getmro(cls)
    return min(bases, key=(mro + bases).index)


def _setdefault(dict_, default):
    result = default.copy()
    result.update(dict_)
    return result


# Editors

class ReadOnlyDelegate(QtGui.QStyledItemDelegate):

    def createEditor(self, parent, option, index):
        editor = QtGui.QLineEdit(parent)
        #editor.setFrame(False)
        editor.setReadOnly(True)
        editor.setAlignment(Qt.Alignment(index.data(Qt.TextAlignmentRole)))
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.DisplayRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        pass


class DoubleValidator(_DoubleValidator):

    def validate(self, text, pos):
        # Allow to delete values
        if not text:
            return (QtGui.QValidator.Acceptable, text, pos)
        return super(DoubleValidator, self).validate(text, pos)


class FloatDelegate(QtGui.QStyledItemDelegate):

    unit = None

    # TODO: *infer* number of decimals from the value in a sensible manner
    # TODO: use same inference for ordinary FloatValue's as well

    def createEditor(self, parent, option, index):
        editor = QtGui.QLineEdit(parent)
        editor.setFrame(False)
        editor.setValidator(DoubleValidator())
        editor.setAlignment(Qt.Alignment(index.data(Qt.TextAlignmentRole)))
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.DisplayRole)
        editor.setText(value)

    def setModelData(self, editor, model, index):
        value = editor.text()
        try:
            parsed = float(value)
        except ValueError:
            parsed = None
        model.setData(index, parsed)


class QuantityDelegate(QtGui.QStyledItemDelegate):

    def __init__(self, unit):
        super(QuantityDelegate, self).__init__()
        self.unit = unit

    def createEditor(self, parent, option, index):
        return QuantitySpinBox(parent, unit=self.unit)

    def setEditorData(self, editor, index):
        editor.set_quantity_checked(index.data(Qt.EditRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.quantity)


class AffixLineEdit(QtGui.QWidget):

    """Single-line edit control with prefix/suffix text."""

    def __init__(self, *args, **kwargs):
        super(AffixLineEdit, self).__init__(*args, **kwargs)
        self.prefix = QtGui.QLabel()
        self.suffix = QtGui.QLabel()
        self.edit = QtGui.QLineEdit()
        self.edit.setFrame(False)
        layout = HBoxLayout([
            self.prefix,
            self.edit,
            self.suffix,
        ])
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        self.setAutoFillBackground(True)

    def focusInEvent(self, event):
        self.edit.setFocus()
        event.accept()


class ListDelegate(QtGui.QStyledItemDelegate):

    # TODO: select sections individually, cycle through with <Tab>
    # TODO: adjust increase editor size while typing? (so prefix/suffix will
    # always be directly after the edit text)
    # TODO: use QDoubleSpinBox for current section? Show other parts as
    # prefix/suffix
    # TODO: intercept and handle <Enter>

    def createEditor(self, parent, option, index):
        editor = AffixLineEdit(parent)
        editor.prefix.setText('[')
        editor.suffix.setText(']')
        return editor

    def setEditorData(self, editor, index):
        text = index.data().lstrip('[').rstrip(']')
        editor.edit.setText(text)
        editor.edit.selectAll()

    def setModelData(self, editor, model, index):
        value = editor.edit.text()
        items = [unit.from_config(item) for item in value.split(',')]
        model.setData(index, items)


class EnumDelegate(QtGui.QStyledItemDelegate):

    def __init__(self, enum):
        super(EnumDelegate, self).__init__()
        self.enum = enum

    def createEditor(self, parent, option, index):
        editor = QtGui.QComboBox(parent)
        return editor

    def setEditorData(self, editor, index):
        editor.clear()
        editor.addItems(self.enum._values)
        editor.setCurrentIndex(editor.findText(str(index.data())))

    def setModelData(self, editor, model, index):
        value = editor.currentText()
        model.setData(index, self.enum(value))
