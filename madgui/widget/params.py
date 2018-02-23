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

    def update(self, **kw):
        """Update dialog from the datastore."""
        # TODO: get along without resetting all the rows?
        self.datastore.kw.update(kw)
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

    def __init__(self, tabs=()):
        super().__init__()
        self.kw = {}
        self.setTabsClosable(False)
        for name, page in tabs:
            self.addTab(page, name)
        self.currentChanged.connect(self.update)

    def update(self):
        self.currentWidget().update(**self.kw)

    def activate_tab(self, name):
        index = next((i for i in range(self.count())
                      if self.tabText(i).lower() == name.lower()), 0)
        if index != self.currentIndex():
            self.setCurrentIndex(index)
