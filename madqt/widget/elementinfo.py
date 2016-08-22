"""
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import MutableSequence
from contextlib import contextmanager

from madqt.qt import QtCore, QtGui, Qt
import madqt.core.unit as unit


class ColumnInfo(object):

    def __init__(self, title, gettext):
        """
        :param str title: column title
        :param callable gettext: item -> str
        """
        self.title = title
        self.gettext = gettext


class ItemsList(MutableSequence):

    """A list-like interface adapter for a wx.ListCtrl."""

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

    def __init__(self, columns):
        super(TableModel, self).__init__()
        self.columns = columns
        self._rows = ItemsList(self, [])

    @property
    def rows(self):
        return self._rows

    @rows.setter
    def rows(self, rows):
        self._rows[:] = rows

    def columnCount(self, parent):
        return len(self.columns)

    def rowCount(self, parent):
        return len(self.rows)

    def data(self, index, role):
        if not index.isValid():
            return None
        elif role != Qt.DisplayRole:
            return None
        column = self.columns[index.column()]
        item = self.rows[index.row()]
        return column.gettext(item)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.columns[section].title
        return None


class TableView(QtGui.QTableView):

    def __init__(self, columns, *args, **kwargs):
        super(TableView, self).__init__(*args, **kwargs)
        self.setModel(TableModel(columns))
        self.setShowGrid(False)

    @property
    def rows(self):
        return self.model().rows

    @rows.setter
    def rows(self, rows):
        self.model().rows = rows


def _format_key(item):
    return item[0]


def _format_val(item):
    val = item[1]
    if isinstance(val, list):
        return '[{}]'.format(
            ", ".join(_format_val((None, v)) for v in val)
        )
    elif isinstance(val, (float, unit.units.Quantity)):
        return unit.format_quantity(val, '.3f')
    elif isinstance(val, basestring):
        return val
    else:
        return str(val)


class ElementInfoBox(TableView):

    columns = [
        ColumnInfo('Parameter', _format_key),
        ColumnInfo('Value', _format_val),
    ]

    def __init__(self, segment, el_name, *args, **kwargs):
        super(ElementInfoBox, self).__init__(self.columns, *args, **kwargs)

        self.segment = segment
        self.el_name = el_name

        self.segment.updated.connect(self.update)

    def closeEvent(self, event):
        self.segment.updated.disconnect(self.update)
        event.accept()

    @property
    def el_name(self):
        return self._el_name

    @el_name.setter
    def el_name(self, name):
        self._el_name = name
        self.update()

    @property
    def element(self):
        elements = self.segment.universe.madx.active_sequence.elements
        raw_element = elements[self.el_name]
        return self.segment.utool.dict_add_unit(raw_element)

    def update(self):

        """
        Update the contents of the managed popup window.
        """

        el = self.element
        rows = list(el.items())

        # convert to title case:
        rows = [(k.title(), v) for (k, v) in rows]

        # presort alphanumerically:
        # (with some luck the order on the elements with equal key in the
        # subsequent sort will be left invariant)
        rows = sorted(rows)

        # sort preferred elements to top:
        order = [
            'Name',
            'Type',
            'At',
            'L',
            'Ksl',
            'Knl',
        ]
        order = {k: i for i, k in enumerate(order)}
        rows = sorted(rows, key=lambda row: order.get(row[0], len(order)))
        rows = [row for row in rows if row[0] != 'Vary']

        # update view:
        self.rows = rows

        self.resizeColumnsToContents()
