"""
Table widget specified by column behaviour.
"""

from inspect import getmro

from madgui.qt import QtCore, QtGui, Qt
from madgui.core.base import Object, Signal
from madgui.core.unit import Expression
from madgui.core.config import NumberFormat
from madgui.util.layout import HBoxLayout
from madgui.util.misc import rw_property
from madgui.util.collections import List
from madgui.util.enum import Enum
from madgui.util.symbol import SymbolicValue
from madgui.widget.spinbox import QuantitySpinBox
from madgui.widget.quantity import DoubleValidator as _DoubleValidator

import madgui.core.unit as unit


__all__ = [
    'ColumnInfo',
    'TableModel',
    'TableView',
]


defaultTypes = {}       # default {type: value proxy} mapping


# TODO: more consistent behaviour/feel of controls: Quantity vs Bare


class ColumnInfo:

    """Column specification for a table widget."""

    types = defaultTypes

    def __init__(self, title, getter, setter=None,
                 resize=None, types=None, padding=0,
                 **kwargs):
        """
        :param str title: column title
        :param callable getter: item -> :class:`ValueProxy`
        :param QtGui.QHeaderView.ResizeMode resize:
        :param int padding:
        :param dict kwargs: arguments for ``getter``, e.g. ``editable``
        """
        self.title = title
        self.getter = getter or (lambda x: x)
        self.setter = setter
        self.resize = resize
        self.padding = padding
        self.kwargs = kwargs
        if types is not None:
            self.types = types
        if setter is not None:
            self.kwargs.setdefault('editable', True)

    def valueProxy(self, model, index):
        item = model.rows[index]
        if isinstance(self.getter, str):
            value = getattr(item, self.getter)
        else:
            value = self.getter(*self.getter_args(model, index))
        if isinstance(value, ValueProxy):
            proxy = value
        else:
            proxy = makeValue(value, self.types, **self.kwargs)
        if self.setter is not None:
            proxy.dataChanged.connect(
                lambda value: self.setter(*self.setter_args(model, index, value)))
        return proxy

    def getter_args(self, model, index):
        return (model.rows[index],)

    def setter_args(self, model, index, value):
        return (model.rows, index, value)


class ExtColumnInfo(ColumnInfo):

    def getter_args(self, model, index):
        return (model.context, model.rows[index], index)

    def setter_args(self, model, index, value):
        return (model.context, model.rows[index], index, value)



class TableModel(QtCore.QAbstractTableModel):

    """
    Table data model.

    Column specifications are provided as :class:`ColumnInfo` instances. The
    data can be accessed and changed via the list-like :attribute:`rows`.
    """

    baseFlags = Qt.ItemNeverHasChildren

    def __init__(self, columns, data=None, context=None):
        super().__init__()
        self.columns = columns
        self.context = context if context is not None else self
        self._rows = List() if data is None else data
        self._rows.update_before.connect(self._update_prepare)
        self._rows.update_after.connect(self._update_finalize)

    def _update_prepare(self, slice, old_values, new_values):
        simple = slice.step is None or slice.step == 1
        parent = QtCore.QModelIndex()
        num_old = len(old_values)
        num_new = len(new_values)
        start = slice.start or 0
        if simple and num_old == 0 and num_new > 0:
            stop = start+num_new-1
            self.beginInsertRows(parent, start, stop)
        elif simple and num_old > 0 and num_new == 0:
            stop = start+num_old-1
            self.beginRemoveRows(parent, start, stop)
        elif simple and num_old == num_new:
            pass
        else:
            self.beginResetModel()

    def _update_finalize(self, slice, old_values, new_values):
        simple = slice.step is None or slice.step == 1
        num_old = len(old_values)
        num_new = len(new_values)
        if simple and num_old == 0 and num_new > 0:
            self.endInsertRows()
        elif simple and num_old > 0 and num_new == 0:
            self.endRemoveRows()
        elif simple and num_old == num_new:
            start = slice.start or 0
            stop = start + num_old
            self.dataChanged.emit(
                self.createIndex(start, 0),
                self.createIndex(stop, self.columnCount()-1))
        else:
            self.endResetModel()

    # data accessors

    @property
    def rows(self):
        return self._rows

    @rows.setter
    def rows(self, rows):
        self._rows[:] = rows

    def value(self, index):
        # TODO: cache the valueproxy? However, we have to recreate the proxy
        # at least whenever the value changes, because also the type may
        # change.
        column = self.columns[index.column()]
        return column.valueProxy(self, index.row())

    # QAbstractTableModel overrides

    def columnCount(self, parent=None):
        return len(self.columns)

    def rowCount(self, parent=None):
        return len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        return self.value(index).data(role)

    def flags(self, index):
        if not index.isValid():
            return super().flags(index)
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
            # NOTE: technically redundant due to self._update_finalize:
            self.dataChanged.emit(index, index)
        return changed


class TableView(QtGui.QTableView):

    """A table widget using a :class:`TableModel` to handle the data."""

    _default_resize_modes = [QtGui.QHeaderView.ResizeToContents,
                             QtGui.QHeaderView.Stretch]

    selectionChangedSignal = Signal()

    allow_delete = False

    def __init__(self, parent=None, columns=None, data=None, context=None, **kwargs):
        """Initialize with list of :class:`ColumnInfo`."""
        super().__init__(parent, **kwargs)
        self.verticalHeader().hide()
        self.setItemDelegate(TableViewDelegate())
        self.setAlternatingRowColors(True)
        if columns is not None:
            self.set_columns(columns, data, context)
        NumberFormat.changed.connect(self.format_changed)

    def format_changed(self):
        # NOTE: this is only okay as long as there is only a single view for
        # each model (otherwise the signals will be emitted multiple times!):
        self.model().layoutAboutToBeChanged.emit()
        self.model().layoutChanged.emit()

    def set_columns(self, columns, data=None, context=None):
        self.setModel(TableModel(columns, data, context))
        for index, column in enumerate(columns):
            resize = (self._default_resize_modes[index > 0]
                      if column.resize is None
                      else column.resize)
            self._setColumnResizeMode(index, resize)

    def selectionChanged(self, selected, deselected):
        super().selectionChanged(selected, deselected)
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
        rows = {idx.row() for idx in self.selectedIndexes()}
        # TODO: delete all in one operation
        for row in sorted(rows, reverse=True):
            # TODO: these should be called from the model…
            del self.model().rows[row]
            #self.model().beginRemoveRows(self.rootIndex(), row, row)
            #self.model().endRemoveRows()

    def keyPressEvent(self, event):
        if self.state() == QtGui.QAbstractItemView.NoState:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) \
                    and self.allow_delete:
                self.removeSelectedRows()
                event.accept()
                return
        super().keyPressEvent(event)

    def connectButtons(self, remove, clear=None):
        if remove:
            self.allow_delete = True
            update = lambda: remove.setEnabled(bool(self.selectedIndexes()))
            remove.clicked.connect(self.removeSelectedRows)
            self.selectionChangedSignal.connect(update)
            update()
        if clear:
            self.allow_delete = True
            update = lambda: clear.setEnabled(bool(self.rows))
            clear.clicked.connect(self.rows.clear)
            self.selectionChangedSignal.connect(update)
            self.rows.update_after.connect(update)
            update()

    def _columnContentWidth(self, column):
        return max(self.sizeHintForColumn(column),
                   self.horizontalHeader().sectionSizeHint(column))

    def sizeHint(self):
        content_width = sum(map(self._columnContentWidth,
                                range(len(self.model().columns))))
        margins_width = (self.contentsMargins().left() +
                         self.contentsMargins().right())
        scrollbar_width = self.verticalScrollBar().width()
        total_width = (margins_width +
                       content_width +
                       scrollbar_width)
        height = super().sizeHint().height()
        return QtCore.QSize(total_width, height)

    def sizeHintForColumn(self, column):
        return (super().sizeHintForColumn(column)
                + self.model().columns[column].padding)

    @property
    def _setColumnResizeMode(self):
        return self.horizontalHeader().setSectionResizeMode

    @property
    def _setRowResizeMode(self):
        return self.verticalHeader().setSectionResizeMode


class TableViewDelegate(QtGui.QStyledItemDelegate):

    # NOTE: The QItemEditorFactory/QItemEditorCreatorBase has some problems
    # regarding registration and creation of QVariant types for custom python
    # types, so we use QItemDelegate as a simpler replacement.

    def delegate(self, index):
        valueProxy = index.model().value(index)
        return (not valueProxy.editable and ReadOnlyDelegate() or
                valueProxy.delegate() or
                super())

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
                 textcolor=None,
                 sizeHint=None,
                 ):
        """Store the value."""
        super().__init__()
        if default is not None: self.default = default
        if editable is not None: self.editable = editable
        if fmtspec is not None: self.fmtspec = fmtspec
        if types is not None: self.types = types
        if textcolor is not None: self.textbrush = QtGui.QBrush(textcolor)
        if sizeHint is not None: self.sizeHint = sizeHint
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
        return repr(self.value)


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
        base_flags = super().flags()
        return base_flags & ~Qt.ItemIsEditable | Qt.ItemIsUserCheckable

    def setData(self, value, role):
        if role == Qt.CheckStateRole:
            role = Qt.EditRole
            value = value == Qt.Checked
        return super().setData(value, role)


# TODO: use UI units
class QuantityValue(FloatValue):

    def __init__(self, value, **kwargs):
        if value is not None:
            self.unit = unit.get_unit(value)
        else:
            self.unit = unit.get_unit(kwargs.get('default'))
        super().__init__(value, **kwargs)

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
        super().__init__(value, **kwargs)

    def delegate(self):
        return EnumDelegate(self.enum)


defaultTypes.update({
    float: FloatValue,
    int: IntValue,
    bool: BoolValue,
    str: StringValue,
    bytes: StringValue,
    list: ListValue,                        # TODO: VECTOR vs MATRIX…
    unit.units.Quantity: QuantityValue,
    SymbolicValue: QuantityValue,
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


class MultiLineDelegate(QtGui.QStyledItemDelegate):

    def createEditor(self, parent, option, index):
        editor = QtGui.QPlainTextEdit(parent)
        editor.setReadOnly(True)
        return editor

    def setEditorData(self, editor, index):
        editor.setPlainText(index.data(Qt.DisplayRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        pass


class DoubleValidator(_DoubleValidator):

    def validate(self, text, pos):
        # Allow to delete values
        if not text:
            return (QtGui.QValidator.Acceptable, text, pos)
        return super().validate(text, pos)


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
        super().__init__()
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
        super().__init__(*args, **kwargs)
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
        super().__init__()
        self.enum = enum

    def createEditor(self, parent, option, index):
        editor = QtGui.QComboBox(parent)
        editor.setEditable(not self.enum._strict)
        return editor

    def setEditorData(self, editor, index):
        editor.clear()
        editor.addItems(self.enum._values)
        editor.setCurrentIndex(editor.findText(str(index.data())))

    def setModelData(self, editor, model, index):
        value = editor.currentText()
        model.setData(index, self.enum(value))
