"""
Table widget specified by column behaviour.
"""

from inspect import getmro

from madgui.qt import QtCore, QtGui, Qt
from madgui.core.base import Signal
from madgui.core.unit import to_ui, from_ui, ui_units
from madgui.util.layout import HBoxLayout
from madgui.util.misc import rw_property
from madgui.util.collections import List
from madgui.util.enum import Enum
from madgui.widget.spinbox import QuantitySpinBox
from madgui.widget.quantity import DoubleValidator as _DoubleValidator

import madgui.core.unit as unit
import madgui.core.config as config


__all__ = [
    'ColumnInfo',
    'TableModel',
    'TableView',
]


# TODO: more consistent behaviour/feel of controls: Quantity vs Bare


# data role, see: http://doc.qt.io/qt-5/qt.html#ItemDataRole-enum
ROLES = {
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


def lift(value):
    return value if callable(value) else lambda cell: value


class ColumnInfo:

    """Column specification for a table widget."""

    def __init__(self, title, getter, setter=None, resize=None,
                 *, convert=False, padding=0, **kwargs):
        """
        :param str title: column title
        :param callable getter: item -> value
        :param callable setter: (rows,idx,value) -> ()
        :param QtGui.QHeaderView.ResizeMode resize: column resize mode
        :param bool convert: automatic unit conversion, can be string to base
                             quanitity name on an attribute of the item
        :param int padding: column padding for size hint
        :param kwargs: any parameter in ``ROLES`` or a method override, in
                       particular ``mutable``, ``delegate``, ``checkable``,
                       ``checked``, ``setChecked``. Can be given as static
                       value or as function: cell->value
        """
        # column globals:
        self.title = title
        self.resize = resize
        self.padding = padding
        # value accessors
        self.getter = getter or (lambda c: c.item)
        self.setter = setter
        self.convert = convert
        kwargs.setdefault('mutable', setter is not None)
        if convert is True: self.title += '/' + ui_units.label(getter)
        # method/property overrides
        for k, v in kwargs.items():
            setattr(self, k, lift(v))

    # QAbstractItemModel queries

    def flags(self, cell):
        # Always editable with ReadOnlyDelegate:
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        if cell.checkable:
            flags |= Qt.ItemIsUserCheckable
        return flags

    # role queries

    def display(self, cell):
        """Render the value as string."""
        return cell.delegate.display(cell.value)

    def edit(self, cell):
        """Obtain value for the editor."""
        return cell.delegate.edit(cell)

    def checkState(self, cell):
        checked = cell.checked
        if checked is None:
            return None
        return Qt.Checked if checked else Qt.Unchecked

    def textAlignment(self, cell):
        return cell.delegate.textAlignment

    # value type

    def editable(self, cell):
        return cell.mutable and not isinstance(cell.delegate, BoolDelegate)

    def checkable(self, cell):
        return cell.mutable and isinstance(cell.delegate, BoolDelegate)

    def delegate(self, cell):
        return lookupDelegate(cell.value)

    # value queries

    def value(self, cell):
        if isinstance(self.getter, str):
            value = getattr(cell.item, self.getter)
        else:
            value = self.getter(cell)
        return to_ui(cell.name, value)

    def checked(self, cell):
        if isinstance(cell.delegate, BoolDelegate):
            return bool(cell.value)

    def name(self, cell):
        convert = self.convert
        if convert:
            if isinstance(convert, str):
                return getattr(cell.item, convert)
            elif callable(convert):
                return convert(cell.item)
            else:
                # NOTE: incompatible with custom getters/setters
                return self.getter

    # edit requests:

    def setValue(self, cell, value):
        self.setter(cell, from_ui(cell.name, value))

    def setChecked(self, cell, value):
        """Implement setting BoolDelegate via checkbox."""
        self.setter(cell, value)


class TableCell:

    """
    Proxy class for accessing contents/properties of a table cell. Queries
    properties from the associated :class`ColumnInfo` and caches the result
    as attribute.
    """

    def __init__(self, model, index):
        self.model = model
        self.row = row = index.row()
        self.col = col = index.column()
        self.info = model.columns[col]
        self.item = model.rows[row]

    # Fetch properties by invoking associated ColumnInfo methods, cache
    # results automatically as attributes, e.g.: value/delegate/name
    def __getattr__(self, key):
        fn = getattr(self.info, key, None)
        try:
            val = fn and fn(self)
        except AttributeError as e:     # unshadow AttributeError!
            raise Exception() from e
        setattr(self, key, val)
        return val

    def setData(self, value, role):
        if role == Qt.EditRole and self.editable:
            self.info.setValue(self, value)
            return True
        if role == Qt.CheckStateRole and self.checkable:
            self.info.setChecked(self, value == Qt.Checked)
            return True
        return False


class TableModel(QtGui.QStandardItemModel):

    """
    Table data model.

    Column specifications are provided as :class:`ColumnInfo` instances. The
    data can be accessed and changed via the list-like :attribute:`rows`.
    """

    baseFlags = Qt.ItemNeverHasChildren

    def __init__(self, columns, data=None, context=None):
        self._rows = List() if data is None else data
        self._rows.update_after.connect(self._update_finalize)
        super().__init__(len(self._rows), len(columns))
        self.columns = columns
        self.context = context if context is not None else self
        for col, info in enumerate(columns):
            self.setHeaderData(col, Qt.Horizontal, info.title, Qt.DisplayRole)
        for row, item in enumerate(self._rows):
            for col in range(self.columnCount()):
                self.setItem(row, col, self._create_item(row, col, item))

    def _create_item(self, row, col, data):
        cell = self.cell(self.index(row, col))
        item = QtGui.QStandardItem()
        item.setFlags(cell.flags)
        for role, name in ROLES.items():
            if role != Qt.EditRole:
                value = getattr(cell, name, None)
                if value is not None:
                    item.setData(value, role)
        return item

    def _update_finalize(self, slice, old_values, new_values):
        simple = slice.step is None or slice.step == 1
        if not simple:
            raise NotImplementedError()
        num_old = len(old_values)
        num_new = len(new_values)
        start = (slice.start or 0) % len(self.rows)
        if num_new > num_old:
            self.insertRows(start+num_old, num_new-num_old)
        elif num_old > num_new:
            self.removeRows(start+num_new, num_old-num_new)
        for row, item in enumerate(new_values):
            for col in range(self.columnCount()):
                self.setItem(row, col, self._create_item(row, col, item))

    # data accessors

    @property
    def rows(self):
        return self._rows

    @rows.setter
    def rows(self, rows):
        self._rows[:] = rows

    def cell(self, index):
        return TableCell(self, index)

    # QAbstractItemModel overrides

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        return self.cell(index).setData(value, role)


class TableView(QtGui.QTreeView):

    """A table widget using a :class:`TableModel` to handle the data."""

    _default_resize_modes = [QtGui.QHeaderView.ResizeToContents,
                             QtGui.QHeaderView.Stretch]

    selectionChangedSignal = Signal()

    allow_delete = False

    def __init__(self, parent=None, columns=None, data=None, context=None, **kwargs):
        """Initialize with list of :class:`ColumnInfo`."""
        super().__init__(parent, **kwargs)
        self.setItemDelegate(TableViewDelegate())
        self.setAlternatingRowColors(True)
        self.setRootIsDecorated(False)
        if columns is not None:
            self.set_columns(columns, data, context)
        config.number.changed.connect(self.format_changed)

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
            self.header().setSectionResizeMode(index, resize)

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

    def resizeColumnsToContents(self):
        for i in range(self.model().columnCount()):
            self.resizeColumnToContents(i)

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
                   self.header().sectionSizeHint(column))

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


class TableViewDelegate(QtGui.QStyledItemDelegate):

    def delegate(self, index):
        cell = index.model().cell(index)
        return cell.delegate if cell.editable else ReadOnlyDelegate()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(hint.height() + 10)
        return hint

    def createEditor(self, parent, option, index):
        return self.delegate(index).createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        return self.delegate(index).setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        return self.delegate(index).setModelData(editor, model, index)

    def updateEditorGeometry(self, editor, option, index):
        return self.delegate(index).updateEditorGeometry(editor, option, index)


# Value types

class ItemDelegate(QtGui.QStyledItemDelegate):

    """Wrap a value of a specific type for string rendering and editting."""

    default = ""
    fmtspec = ''
    textAlignment = Qt.AlignLeft | Qt.AlignVCenter

    def __init__(self, *,
                 default=None,
                 fmtspec=None
                 ):
        """Store the value."""
        super().__init__()
        if default is not None: self.default = default
        if fmtspec is not None: self.fmtspec = fmtspec

    def display(self, value):
        """Render the value as string."""
        if value is None:
            return ""
        return format(value, self.fmtspec)

    def edit(self, cell):
        return self.default if cell.value is None else cell.value


class StringDelegate(ItemDelegate):

    """Bare string value."""

    pass


class FloatValue(ItemDelegate):

    """Float value."""

    default = 0.0
    textAlignment = Qt.AlignRight | Qt.AlignVCenter

    @rw_property
    def fmtspec(self):
        return config.number.fmtspec

    # QStyledItemDelegate

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


class IntDelegate(ItemDelegate):

    """Integer value."""

    default = 0
    textAlignment = Qt.AlignRight | Qt.AlignVCenter

    # NOTE: This class is needed to create a spinbox without
    # `editor.setFrame(False)` which causes a display bug: display value is
    # still shown, partially covered by the spin buttons.

    def createEditor(self, parent, option, index):
        editor = QtGui.QSpinBox(parent)
        editor.setRange(-(1<<30), +(1<<30))
        editor.setAlignment(Qt.Alignment(index.data(Qt.TextAlignmentRole)))
        return editor

    def setEditorData(self, editor, index):
        value = index.model().cell(index).edit
        editor.setValue(value)

    def setModelData(self, editor, model, index):
        value = editor.text()
        try:
            parsed = int(value)
        except ValueError:
            parsed = None
        model.setData(index, parsed)


class BoolDelegate(ItemDelegate):

    """Boolean value."""

    # FIXME: distinguish `None` values, gray out?
    default = False


# TODO: use UI units
class QuantityDelegate(FloatValue):

    def __init__(self, unit=None):
        super().__init__()
        self.unit = unit

    def display(self, value):
        if value is None:
            return "" if self.unit is None else unit.get_raw_label(self.unit)
        if isinstance(value, (float, unit.units.Quantity)):
            return unit.format_quantity(value, self.fmtspec)
        return format(value)

    # QStyledItemDelegate

    def createEditor(self, parent, option, index):
        return QuantitySpinBox(parent, unit=self.unit)

    def setEditorData(self, editor, index):
        editor.set_quantity_checked(index.model().cell(index).edit)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.quantity)


class ListDelegate(ItemDelegate):

    """List value."""

    textAlignment = Qt.AlignRight | Qt.AlignVCenter

    def display(self, value):
        return '[{}]'.format(
            ", ".join(map(self.formatValue, value)))

    def formatValue(self, value):
        return lookupDelegate(value).display(value)

    # QStyledItemDelegate

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


class EnumDelegate(StringDelegate):

    # QStyledItemDelegate

    def createEditor(self, parent, option, index):
        enum = type(index.model().cell(index).edit)
        editor = QtGui.QComboBox(parent)
        editor.setEditable(not enum._strict)
        return editor

    def setEditorData(self, editor, index):
        enum = type(index.model().cell(index).edit)
        editor.clear()
        editor.addItems(enum._values)
        editor.setCurrentIndex(editor.findText(str(index.data())))

    def setModelData(self, editor, model, index):
        enum = type(index.model().cell(index).edit)
        value = editor.currentText()
        model.setData(index, enum(value))


TYPES = {                   # default {type: value proxy} mapping
    object: ItemDelegate(),
    float: QuantityDelegate(),
    int: IntDelegate(),
    bool: BoolDelegate(),
    str: StringDelegate(),
    bytes: StringDelegate(),
    list: ListDelegate(),                       # TODO: VECTOR vs MATRIX…
    unit.units.Quantity: QuantityDelegate(),
    Enum: EnumDelegate(),
}


# lookupDelegate

def lookupDelegate(value):
    return TYPES[_get_best_base(value.__class__, TYPES)]


def _get_best_base(cls, bases):
    bases = tuple(base for base in bases if issubclass(cls, base))
    mro = getmro(cls)
    return min(bases, key=(mro + bases).index)


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
        return super().validate(text, pos)


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
