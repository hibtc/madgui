"""
Parameter input dialog.
"""

from madgui.qt import QtGui, Qt

import madgui.widget.tableview as tableview


__all__ = [
    'ParamTable',
    'TabParamTables',
]


class ParamInfo:

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

    def __repr__(self):
        return "{}({}={})".format(
            self.__class__.__name__, self.name, self.proxy.value)


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

        super().__init__(columns=columns, **kwargs)
        # in case anyone turns the horizontalHeader back on:
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().hide()
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    def update(self):
        """Update dialog from the datastore."""
        # TODO: get along without resetting all the rows?
        rows = [ParamInfo(self.datastore, k, v)
                for k, v in self.datastore.get().items()]
        if len(rows) == len(self.rows):
            for i, row in enumerate(rows):
                self.rows[i] = row
        else:
            self.rows = rows

        # Set initial size:
        if not self.isVisible():
            self.selectRow(0)
            self.resizeColumnsToContents()
            self.updateGeometries()

    def keyPressEvent(self, event):
        """<Enter>: open editor; <Delete>/<Backspace>: remove value."""
        if self.state() == QtGui.QAbstractItemView.NoState:
            # TODO: deletion does not work currently.
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.setRowValue(self.curRow(), None)
                event.accept()
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.edit(self.model().index(self.curRow(), 1))
                event.accept()
                return
        super().keyPressEvent(event)

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

    def __init__(self, datastore, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.datastore = datastore
        self.setTabsClosable(False)
        self.currentChanged.connect(self.index_changed)

    @property
    def datastore(self):
        return self._datastore

    @datastore.setter
    def datastore(self, datastore):
        self._datastore = datastore
        # TODO: keep+reuse existing tabs as far as possible (?)
        self.clear()
        if datastore is None:
            return
        self.tabs = tabs = [
            ParamTable(ds, **self.kwargs)
            for ds in datastore.substores.values()
        ]
        for tab in tabs:
            # TODO: suppress empty tabs
            self.addTab(tab, tab.datastore.label)
        self.tabBar().setVisible(len(tabs) > 1)

    def update(self):
        self.tabs[self.currentIndex()].update()

    def index_changed(self, index):
        # DO NOT call into `self.update` from here. Otherwise there will be
        # infinite recursions for `ElementInfoBox`
        self.tabs[self.currentIndex()].update()

    def activate_tab(self, name):
        index = next((i for i, l in enumerate(self._datastore.substores)
                      if l == name), 0)
        if index != self.currentIndex():
            self.setCurrentIndex(index)
