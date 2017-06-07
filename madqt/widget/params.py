# encoding: utf-8
"""
Parameter input dialog.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import QtCore, QtGui, Qt

import madqt.widget.tableview as tableview
from madqt.util.layout import VBoxLayout


__all__ = [
    'ParamTable',
    'TabParamTables',
]


class ParamInfo(object):

    """Row info for the TableView [internal]."""

    def __init__(self, datastore, key, value):
        self.name = key
        self.datastore = datastore
        default = datastore.default(key)
        editable = datastore.mutable(key)
        textcolor = Qt.black if editable else Qt.darkGray
        self.proxy = tableview.makeValue(
            value, default=default,
            editable=editable,
            textcolor=textcolor)
        self.proxy.dataChanged.connect(self.on_edit)

    def on_edit(self, value):
        self.datastore.update({self.name: value})


class ParamTable(tableview.TableView):

    """
    Input controls to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.
    """

    # TODO: disable/remove Cancel/Apply buttons in non-transactional mode
    # TODO: add "transactional" mode: update only after *applying*
    # TODO: visually indicate rows with non-default values: "bold"
    # TODO: move rows with default or unset values to bottom? [MAD-X]

    def __init__(self, datastore, **kwargs):
        """Initialize data."""

        self.datastore = datastore

        columns = [
            tableview.ColumnInfo("Parameter", 'name'),
            tableview.ColumnInfo("Value", 'proxy', padding=50),
        ]

        super(ParamTable, self).__init__(columns=columns, **kwargs)
        # in case anyone turns the horizontalHeader back on:
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().hide()
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    def update(self):
        """Update dialog from the datastore."""
        self.rows = [ParamInfo(self.datastore, k, v)
                     for k, v in self.datastore.get().items()]
        self.selectRow(0)
        # Set initial size:
        if not self.isVisible():
            self.resizeColumnsToContents()
            self.updateGeometries()

    def keyPressEvent(self, event):
        """<Enter>: open editor; <Delete>/<Backspace>: remove value."""
        if self.state() == QtGui.QAbstractItemView.NoState:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.setRowValue(self.curRow(), None)
                event.accept()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.edit(self.model().index(self.curRow(), 1))
                event.accept()
                return
        super(ParamTable, self).keyPressEvent(event)

    def curRow(self):
        # This is failsafe only in SingleSelection widgets:
        return self.selectedIndexes()[0].row()

    def setRowValue(self, row, value):
        """Set the value of the parameter in the specified row."""
        model = self.model()
        index = model.index(row, 1)
        model.setData(index, value)


class TabParamTables(QtGui.QTabWidget):

    """
    TabWidget that manages multiple ParamTables inside.
    """

    def __init__(self, datastore, index=0, **kwargs):
        super(TabParamTables, self).__init__()

        self.datastore = datastore

        self.tabs = tabs = [
            ParamTable(ds, **kwargs)
            for ds in datastore.substores.values()
        ]

        # TODO: move this to update()
        self.setTabsClosable(False)
        for tab in tabs:
            # TODO: suppress empty tabs
            self.addTab(tab, tab.datastore.label)
        self.setCurrentIndex(index)
        self.currentChanged.connect(self.update)

        if len(tabs) == 1:
            self.tabBar().hide()

    def update(self, index=None):
        self.tabs[self.currentIndex()].update()


# TODO:
# - update model <-> update values
# - fix beam/twiss handling:
# - store + save separately: only overrides / all
# - use units provided by tao
# - consistent behaviour/use of controls
