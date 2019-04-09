"""
Table widget specified by column behaviour.
"""

__all__ = [
    'TableItem',
    'TableModel',
    'TableView',
    'TreeView',
    'lookupDelegate',
    'NodeItem',
    'TreeNode',
    'ItemView',
    'ItemViewDelegate',
    'ItemDelegate',
    'StringDelegate',
    'IntDelegate',
    'BoolDelegate',
    'QuantityDelegate',
    'ExpressionDelegate',
    'ListDelegate',
    'EnumDelegate',
    'ReadOnlyDelegate',
    'AffixLineEdit',
]

from inspect import getmro
from functools import partial

from PyQt5.QtCore import QAbstractItemModel, QModelIndex, QSize, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QLabel, QLineEdit, QSpinBox,
    QStyledItemDelegate, QTableView, QTreeView, QWidget)

from madgui.util.signal import Signal
from madgui.util.unit import to_ui, from_ui, ui_units
from madgui.util.layout import HBoxLayout
from madgui.util.misc import ranges, cachedproperty
from madgui.util.collections import List
from madgui.util.qt import monospace
from madgui.util.enum import Enum
from madgui.widget.spinbox import QuantitySpinBox, ExpressionSpinBox

import madgui.util.unit as unit
import madgui.core.config as config

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
    # NOTE: Background colors don't seem to work with css styling. For this
    # reason they show only in our TableView, not in our TreeView (for which
    # we need styling to make it look acceptable, see `madgui/data/style.css`).
    Qt.BackgroundRole:              'background',
    # NOTE: BackgroundColorRole is obsolete in favor of BackgroundRole:
    Qt.BackgroundColorRole:         'backgroundColor',
    Qt.ForegroundRole:              'foreground',
    # Qt.TextColorRole:               'textColor',   # = ForegroundRole
    Qt.CheckStateRole:              'checkState',
    Qt.InitialSortOrderRole:        'initialSortOrder',
    # Accessibility roles
    Qt.AccessibleTextRole:          'accessibleText',
    Qt.AccessibleDescriptionRole:   'accessibleDescription',
}


class NodeItem:

    """Descriptor/type information for a TreeNode."""

    def __init__(self, data=None, **kwargs):
        """
        :param value: item -> value
        :param kwargs: any parameter in ``ROLES`` or a method override, in
                       particular ``mutable``, ``delegate``, ``checkable``,
                       ``checked``, ``set_checked``. Can be given as static
                       value or as function: cell->value
        """
        self.data = data
        for k, v in kwargs.items():
            if k[:4] in ('get_', 'set_'):
                v = partial(self._call, v)
            setattr(self, k, v)

    def _call(self, fn, *args):
        return fn(self.row.node.index(), self.row.data, *args)

    # Resolve missing properties by invoking associated methods, cache
    # results automatically as attributes, e.g.: value/delegate/name
    def __getattr__(self, key):
        try:
            fn = object.__getattribute__(self, 'get_' + key)
        except AttributeError:
            fn = None
        try:
            val = fn and fn()
        except AttributeError as e:     # unshadow AttributeError!
            raise Exception() from e
        setattr(self, key, val)
        return val

    def rowitems(self, idx, data):
        return [cls(data) for cls in self.columns]

    def get_children(self):
        """List of child rows (for expandable data)."""
        return [
            NodeItem(row, get_children=self.rowitems)
            for row in self.rows
        ]

    def get_parent(self):
        return self.node.parent.item

    def get_row(self):
        return self


# TODO: add `deleter`
class TableItem(NodeItem):

    """Cell item data for a tree widget."""

    # QAbstractItemModel queries

    def get_flags(self):
        # Always editable with ReadOnlyDelegate:
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
        if self.checkable:
            flags |= Qt.ItemIsUserCheckable
        return flags

    # role queries (ROLES)

    def get_display(self):
        """Render the value as string."""
        return self.delegate.display(self.ui_value)

    def get_edit(self):
        """Obtain value for the editor."""
        return self.delegate.edit(self)

    def get_checkState(self):
        checked = self.checked
        if checked is None:
            return None
        return Qt.Checked if checked else Qt.Unchecked

    def get_textAlignment(self):
        return self.delegate.textAlignment

    # intermediate/helper properties

    def get_editable(self):
        return self.mutable and not isinstance(self.delegate, BoolDelegate)

    def get_checkable(self):
        return self.mutable and isinstance(self.delegate, BoolDelegate)

    def get_delegate(self):
        return lookupDelegate(self.ui_value)

    def get_mutable(self):
        return bool(self.set_value)

    def get_value(self):
        return self.data

    def get_ui_value(self):
        return to_ui(self.name, self.value)

    def get_checked(self):
        if isinstance(self.delegate, BoolDelegate):
            return bool(self.value)

    def set_ui_value(self, value):
        self.set_value(from_ui(self.name, value))

    def set_checked(self, value):
        """Implement setting BoolDelegate via checkbox."""
        self.set_value(value)

    # misc

    def get_row(self):
        return self.parent

    def get_rows(self):     # no children by default
        return ()

    def get_columns(self):
        return ()


class TreeNode:

    """
    Proxy class for accessing contents/properties of a table cell. Delegates
    data queries to attributes of the associated :class`NodeItem`.
    """

    def __init__(self, item, parent=None):
        self.item = item
        self.item.node = self
        self.parent = parent
        self.granny = parent and parent.parent
        self.root = parent.root if parent else self

    index = lambda self: self.parent.children.index(self)

    # row/col should only be used for "cells", i.e. those nodes that describe
    # the visible contents of the treeview:
    row = property(lambda self: self.parent.index())
    col = property(index)

    def invalidate(self):
        if hasattr(self, '_children'):
            nodes = self._children
            items = self.item.get_children()
            for node, item in zip(nodes, items):
                node.item = item
                item.node = node
                node.invalidate()
            del nodes[len(items):]
            nodes[len(nodes):] = [
                TreeNode(item, self)
                for item in items[len(nodes):]
            ]

    @cachedproperty
    def children(self):
        return [
            TreeNode(item, self)
            for item in self.item.get_children()
        ]

    def data(self, role):
        return getattr(self.item, ROLES[role])

    def setData(self, value, role):
        if role == Qt.EditRole and self.item.editable:
            self.item.set_ui_value(value)
            return True
        if role == Qt.CheckStateRole and self.item.checkable:
            self.item.set_checked(value == Qt.Checked)
            return True
        return False


class TableModel(QAbstractItemModel):

    """
    Table data model.

    Column specifications are provided as :class:`TableItem` instances. The
    data can be accessed and changed via the list-like :attr:`rows`.
    """

    def __init__(self, titles, rowitems, data=None):
        super().__init__()
        self.titles = titles
        self._rows = rows = List() if data is None else data
        self._rows.update_finished.connect(self._refresh)
        self.parent = None
        self.root = TreeNode(NodeItem(rows=rows, rowitems=rowitems))

    def _refresh(self, *_):
        self.beginResetModel()
        try:
            self.root.invalidate()
        finally:
            self.endResetModel()

    # data accessors

    @property
    def rows(self):
        return self._rows

    @rows.setter
    def rows(self, rows):
        self._rows[:] = rows

    def cell(self, index):
        return index.internalPointer() or self.root

    # QAbstractItemModel overrides

    # TODO: add/implement TreeNode.children
    def index(self, row, col, parent=QModelIndex()):
        return self.createIndex(
            row, col, self.cell(parent).children[row].children[col])

    def parent(self, index):
        # The parent `Node` of a table cell is the containing row. To get to
        # the parent *cell*, we need in fact its grandparent:
        parent = self.cell(index).granny
        if parent is None or parent.granny is None:
            return QModelIndex()
        return self.createIndex(parent.row, parent.col, parent)

    def columnCount(self, parent=QModelIndex()):
        return len(self.titles)

    def rowCount(self, parent=QModelIndex()):
        return len(self.cell(parent).children or ())

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role in ROLES:
            return self.cell(index).data(role)
        return super().data(index, role)

    def flags(self, index):
        if index.isValid():
            return self.cell(index).item.flags
        return super().flags(index)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.titles[section]

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        cell = self.cell(index)
        changed = cell.setData(value, role)
        if changed:
            # NOTE: This takes care to update cells after edits that don't
            # trigger an update of the self.rows collection for some reason
            # (and hence self._refresh is never called). In fact, we
            # we should trigger the update by re-querying self.rows, but right
            # now this is not guaranteed in all places...
            row = index.row()
            par = index.parent()
            cell.parent.invalidate()
            if self.rowCount(index) > 0:
                self.beginResetModel()
                self.endResetModel()
            else:
                self.dataChanged.emit(
                    self.index(row, 0, par),
                    self.index(row, self.columnCount()-1, par))
        return changed


class ItemView:

    """
    Mixin class for shared code of :class:`TableView` and :class:`TreeView`.
    Do not use directly.
    """

    selectionChangedSignal = Signal()

    allow_delete = False

    def __init__(self, parent=None, **kwargs):
        """Initialize with list of :class:`TableItem`."""
        super().__init__(parent, **kwargs)
        self.padding = {}
        self.setFont(monospace())
        self.setItemDelegate(ItemViewDelegate())
        self.setAlternatingRowColors(True)
        config.number.changed.connect(self.format_changed)

    def format_changed(self):
        # NOTE: this is only okay as long as there is only a single view for
        # each model (otherwise the signals will be emitted multiple times!):
        self.model().layoutAboutToBeChanged.emit()
        self.model().layoutChanged.emit()

    def set_viewmodel(self, rowitems, data=None, unit=(), titles=None):
        titles = list(titles or rowitems.__annotations__['return'])
        if unit is True:
            unit = list(titles)
        for i, u in enumerate(unit):
            if u and ui_units.get(u):
                titles[i] += '/' + ui_units.label(u)
        self.setModel(TableModel(titles, rowitems, data))

    def resizeEvent(self, event):
        """ Resize all sections to content and user interactive """
        super().resizeEvent(event)
        header = self.header()
        columns = [c for c in range(header.count())
                   if not self.isColumnHidden(c)]
        widths = list(map(self._columnContentWidth, columns))
        total = sum(widths)
        avail = event.size().width() - total

        part = avail // len(columns)
        avail -= part * len(columns)

        for i in range(len(columns)):
            widths[i] += part
        if avail != 0:
            widths[-1] += avail

        for index, width in zip(columns, widths):
            header.resizeSection(index, width)

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
        for a, b in ranges(rows)[::-1]:
            # TODO: these should be called from the model…
            del self.model().rows[a:b]

    def keyPressEvent(self, event):
        if self.state() == QAbstractItemView.NoState:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) \
                    and self.allow_delete:
                self.removeSelectedRows()
                event.accept()
                return
        super().keyPressEvent(event)

    def connectRemoveButton(self, button):
        self.allow_delete = True
        update = lambda *_: button.setEnabled(bool(self.selectedIndexes()))
        button.clicked.connect(self.removeSelectedRows)
        self.selectionChangedSignal.connect(update)
        self.rows.update_finished.connect(update)
        update()

    def connectClearButton(self, button):
        self.allow_delete = True
        update = lambda *_: button.setEnabled(bool(self.rows))
        button.clicked.connect(self.rows.clear)
        self.rows.update_finished.connect(update)
        update()

    def _columnContentWidth(self, column):
        return max(self.sizeHintForColumn(column),
                   self.header().sectionSizeHint(column))

    def sizeHint(self):
        # If you are not careful to immediately call set_viewmodel, it is
        # possible that we do not yet have a TableModel:
        if not hasattr(self.model(), 'titles'):
            return super().sizeHint()
        content_width = sum(map(self._columnContentWidth,
                                range(len(self.model().titles))))
        margins_width = (self.contentsMargins().left() +
                         self.contentsMargins().right())
        scrollbar_width = self.verticalScrollBar().width()
        total_width = (margins_width +
                       content_width +
                       scrollbar_width)
        height = super().sizeHint().height()
        return QSize(total_width, height)

    def sizeHintForColumn(self, column):
        return (super().sizeHintForColumn(column) +
                self.padding.get(column, 40))


class TableView(ItemView, QTableView):

    """
    A table widget based on Qt's QTableView for our :class:`TableModel`.

    - does not support expandable items
    - supports vertical header
    - currently supports background colors (since we don't use css for
      QTableView)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.horizontalHeader().setHighlightSections(False)
        self.verticalHeader().setHighlightSections(False)

    def header(self):
        return self.horizontalHeader()


class TreeView(ItemView, QTreeView):

    """
    A tree widget based on Qt's QTableView for our :class:`TableModel`.

    - supports expandable items
    - does not show item background color (apparently due to an
      incompatibility with css styling).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prevent the user from folding since this makes it easier to show
        # the same image after refreshing the model:
        self.setRootIsDecorated(False)
        self.setItemsExpandable(False)

    def resizeColumnsToContents(self):
        for i in range(self.model().columnCount()):
            self.resizeColumnToContents(i)

    def set_viewmodel(self, rowitems, data=None, unit=(), titles=None):
        super().set_viewmodel(rowitems, data, unit, titles)
        self.model().rowsInserted.connect(lambda *_: self.expandAll())
        self.model().modelReset.connect(lambda *_: self.expandAll())
        self.expandAll()


class ItemViewDelegate(QStyledItemDelegate):

    def delegate(self, index):
        cell = index.model().cell(index).item
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

class ItemDelegate(QStyledItemDelegate):

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
        if default is not None:
            self.default = default
        if fmtspec is not None:
            self.fmtspec = fmtspec

    def display(self, value):
        """Render the value as string."""
        if value is None:
            return ""
        return format(value, self.fmtspec)

    def edit(self, cell):
        return self.default if cell.ui_value is None else cell.ui_value


class StringDelegate(ItemDelegate):

    """Bare string value."""

    pass


class IntDelegate(ItemDelegate):

    """Integer value."""

    default = 0
    textAlignment = Qt.AlignRight | Qt.AlignVCenter

    # NOTE: This class is needed to create a spinbox without
    # `editor.setFrame(False)` which causes a display bug: display value is
    # still shown, partially covered by the spin buttons.

    def createEditor(self, parent, option, index):
        editor = QSpinBox(parent)
        editor.setRange(-(1 << 30), +(1 << 30))
        editor.setAlignment(Qt.Alignment(index.data(Qt.TextAlignmentRole)))
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.EditRole)
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
class QuantityDelegate(ItemDelegate):

    default = 0.0
    textAlignment = Qt.AlignRight | Qt.AlignVCenter

    @cachedproperty
    def fmtspec(self):
        return config.number.fmtspec

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
        editor.set_quantity_checked(index.data(Qt.EditRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.quantity)


class ExpressionDelegate(QuantityDelegate):

    default = ""
    textAlignment = Qt.AlignRight | Qt.AlignVCenter     # TODO…

    def edit(self, cell):
        expr = cell.expr and cell.expr.replace(' ', '')
        return expr or cell.ui_value

    # QStyledItemDelegate

    def createEditor(self, parent, option, index):
        return ExpressionSpinBox(parent, unit=None)

    def setEditorData(self, editor, index):
        editor.set_value(index.data(Qt.EditRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.value)


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
        enum = type(index.data(Qt.EditRole))
        editor = QComboBox(parent)
        editor.setEditable(not enum._strict)
        return editor

    def setEditorData(self, editor, index):
        enum = type(index.data(Qt.EditRole))
        editor.clear()
        editor.addItems(enum._values)
        editor.setCurrentIndex(editor.findText(str(index.data())))

    def setModelData(self, editor, model, index):
        enum = type(index.data(Qt.EditRole))
        value = editor.currentText()
        model.setData(index, enum(value))


delegates = {                   # default {type: value proxy} mapping
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
    cls = value if isinstance(value, type) else value.__class__
    return delegates[_get_best_base(cls, delegates)]


def _get_best_base(cls, bases):
    bases = tuple(base for base in bases if issubclass(cls, base))
    mro = getmro(cls)
    return min(bases, key=(mro + bases).index)


# Editors

class ReadOnlyDelegate(QStyledItemDelegate):

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setReadOnly(True)
        editor.setAlignment(Qt.Alignment(index.data(Qt.TextAlignmentRole)))
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.DisplayRole))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        pass


class AffixLineEdit(QWidget):

    """Single-line edit control with prefix/suffix text."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefix = QLabel()
        self.suffix = QLabel()
        self.edit = QLineEdit()
        self.edit.setFrame(False)
        self.setLayout(HBoxLayout([
            self.prefix,
            self.edit,
            self.suffix,
        ], tight=True))
        self.setAutoFillBackground(True)

    def focusInEvent(self, event):
        self.edit.setFocus()
        event.accept()
