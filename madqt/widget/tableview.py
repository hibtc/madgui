# encoding: utf-8
"""
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import MutableSequence
from contextlib import contextmanager

from madqt.qt import QtCore, QtGui, Qt


__all__ = [
    'ColumnInfo',
    'ItemsList',
    'TableModel'
    'TableView',
]


class ColumnInfo(object):

    """Column specification for a table widget."""

    def __init__(self, title, gettext):
        """
        :param str title: column title
        :param callable gettext: item -> str
        """
        self.title = title
        self.gettext = gettext


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

    # QAbstractTableModel overrides

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

    """A table widget using a :class:`TableModel` to handle the data."""

    def __init__(self, columns, *args, **kwargs):
        """Initialize with list of :class:`ColumnInfo`."""
        super(TableView, self).__init__(*args, **kwargs)
        self.setModel(TableModel(columns))
        self.setShowGrid(False)

    @property
    def rows(self):
        """List-like access to the data."""
        return self.model().rows

    @rows.setter
    def rows(self, rows):
        """List-like access to the data."""
        self.model().rows = rows
