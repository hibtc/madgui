# encoding: utf-8
"""
Table widget specified by column behaviour.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import MutableSequence
from contextlib import contextmanager
from inspect import getmro

from six import (python_2_unicode_compatible,
                 text_type,
                 string_types as basestring)

from madqt.qt import QtCore, QtGui, Qt
from madqt.core.base import Object, Signal
from madqt.util.layout import HBoxLayout

import madqt.core.unit as unit


__all__ = [
    'ColumnInfo',
    'ItemsList',
    'TableModel'
    'TableView',
]


defaultTypes = {}       # default {type: value proxy} mapping


class ColumnInfo(object):

    """Column specification for a table widget."""

    types = defaultTypes

    def __init__(self, title, getter, types=None, **kwargs):
        """
        :param str title: column title
        :param callable getter: item -> :class:`ValueProxy`
        :param dict kwargs: arguments for ``getter``, e.g. ``editable``
        """
        self.title = title
        self.getter = getter
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


class ItemsList(MutableSequence):

    """A list-like interface adapter for a :class:`QtCore.QAbstractTableModel`."""

    def __init__(self, model, items):
        """Use the items object by reference."""
        self._model = model
        self._items = items

    # Sized

    def __len__(self):
        return len(self._items)

    # Iterable

    def __iter__(self):
        return iter(self._items)

    # Container

    def __contains__(self, value):
        return value in self._items

    # Sequence

    def __getitem__(self, index):
        return self._items[index]

    def __reversed__(self):
        return reversed(self._items)

    def index(self, value):
        return self._items.index(value)

    def count(self, value):
        return self._items.count(value)

    # MutableSequence

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            start = 0 if index.start is None else index.start
            stop = -1 if index.stop is None else index.stop
        else:
            start, stop = index, index+1
        with self._refresh(start, stop):
            self._items[index] = value

    def __delitem__(self, index):
        with self._refresh(index, -1):
            del self._items[index]

    def insert(self, index, value):
        with self._refresh(index, -1):
            self._items.insert(index, value)

    append = MutableSequence.append

    def reverse(self):
        with self._refresh(0, -1):
            self._items.reverse()

    def extend(self, values):
        old_len = len(self._items)
        with self._refresh(old_len, -1):
            self._items.extend(values)

    pop = MutableSequence.pop
    remove = MutableSequence.remove
    __iadd__ = MutableSequence.__iadd__

    @contextmanager
    def _refresh(self, begin, end):
        self._model.layoutAboutToBeChanged.emit()
        try:
            yield None
        finally:
            self._model.layoutChanged.emit()


class TableModel(QtCore.QAbstractTableModel):

    try:
        baseFlags = Qt.ItemNeverHasChildren
    except AttributeError:
        baseFlags = 0

    """
    Table data model.

    Column specifications are provided as :class:`ColumnInfo` instances. The
    data can be accessed and changed via the list-like :attribute:`rows`.
    """

    def __init__(self, columns):
        super(TableModel, self).__init__()
        self.columns = columns
        self._rows = ItemsList(self, [])

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

    def __init__(self, columns, *args, **kwargs):
        """Initialize with list of :class:`ColumnInfo`."""
        super(TableView, self).__init__(*args, **kwargs)
        self.setModel(TableModel(columns))
        self.setShowGrid(False)
        self.verticalHeader().hide()
        self.setItemDelegate(TableViewDelegate())

    @property
    def rows(self):
        """List-like access to the data."""
        return self.model().rows

    @rows.setter
    def rows(self, rows):
        """List-like access to the data."""
        self.model().rows = rows

    def sizeHint(self):
        return QtCore.QSize(
            self.horizontalHeader().length(),
            super(TableView, self).sizeHint().height())


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


@python_2_unicode_compatible
class ValueProxy(Object):

    """Wrap a value of a specific type for string rendering and editting."""

    default = ""
    fmtspec = ''
    editable = True
    dataChanged = Signal(object)
    types = defaultTypes

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
        Qt.TextColorRole:               'textColor',
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
                 types=None):
        """Store the value."""
        super(ValueProxy, self).__init__()
        self.value = value
        if default is not None: self.default = default
        if editable is not None: self.editable = editable
        if fmtspec is not None: self.fmtspec = fmtspec
        if types is not None: self.types = types

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
        return self.value if self.editable else None

    def checkState(self):
        checked = self.checked()
        if checked is None:
            return None
        return Qt.Checked if checked else Qt.Unchecked

    def checked(self):
        return None

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
    fmtspec = '.3f'


class IntValue(ValueProxy):

    """Integer value."""

    default = 0


class BoolValue(ValueProxy):

    """Boolean value."""

    default = False

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


class QuantityValue(FloatValue):

    fmtspec = '.3f'

    def display(self):
        return unit.format_quantity(self.value, self.fmtspec)

    def delegate(self):
        try:
            delegate = self._delegate
        except AttributeError:
            delegate = self._delegate = QuantityDelegate()
        return delegate


class ListValue(ValueProxy):

    """List value."""

    def display(self):
        return '[{}]'.format(
            ", ".join(map(self.formatValue, self.value)))

    def formatValue(self, value):
        return makeValue(value, self.types).display()

    def delegate(self):
        return ListDelegate()


defaultTypes.update({
    float: FloatValue,
    int: IntValue,
    bool: BoolValue,
    text_type: StringValue,
    bytes: StringValue,
    list: ListValue,
    unit.units.Quantity: QuantityValue,
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
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.DisplayRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        pass


class QuantityDelegate(QtGui.QStyledItemDelegate):

    unit = None

    # TODO: *infer* number of decimals from the value in a sensible manner
    # TODO: use same inference for ordinary FloatValue's as well

    def createEditor(self, parent, option, index):
        editor = QtGui.QDoubleSpinBox(parent)
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor, index):
        quantity = index.data(Qt.EditRole)
        unit_label = unit.get_raw_label(quantity)
        suffix = ' ' + unit_label if unit_label else ''
        editor.setSuffix(suffix)
        decimals = 3
        editor.setDecimals(decimals)
        editor.setSingleStep(10**-decimals)
        editor.setValue(quantity.magnitude)
        self.units = quantity.units

    def setModelData(self, editor, model, index):
        value = editor.value()
        quantity = unit.units.Quantity(value, self.units)
        model.setData(index, quantity)


class InfixLineEdit(QtGui.QWidget):

    """Single-line edit control with prefix/suffix text."""

    def __init__(self, *args, **kwargs):
        super(InfixLineEdit, self).__init__(*args, **kwargs)
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
        editor = InfixLineEdit(parent)
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
