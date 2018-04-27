"""
Parameter input dialog.
"""

from functools import partial

from madgui.qt import QtGui, Qt
from madgui.core.unit import ui_units

import madgui.widget.tableview as tableview


__all__ = [
    'ParamTable',
    'TabParamTables',
]

# TODO: combobox for unit?

class ParamInfo:

    """Row info for the TableView [internal]."""

    def __init__(self, key, value):
        self.name = key
        self.value = value
        self.unit = ui_units.label(key, value)


def set_value(datastore, rows, index, value):
    datastore.update({rows[index].name: value})
    rows[index].value = value


class ParamTable(tableview.TableView):

    """
    Input controls to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.
    """

    # TODO: disable/remove Cancel/Apply buttons in non-transactional mode
    # TODO: add "transactional" mode: update only after *applying*
    # TODO: visually indicate rows with non-default values: "bold"
    # TODO: move rows with default or unset values to bottom? [MAD-X]

    def __init__(self, datastore, units=True, **kwargs):
        """Initialize data."""

        self.datastore = datastore
        setter = partial(set_value, datastore)
        mutable = lambda cell: datastore.mutable(cell.item.name)
        textcolor = lambda cell: Qt.black if cell.mutable else Qt.darkGray

        columns = [
            tableview.ColumnInfo("Parameter", 'name'),
            tableview.ColumnInfo("Value", 'value', setter, padding=50,
                                 convert=units and 'name',
                                 mutable=mutable,
                                 textcolor=textcolor),
            tableview.ColumnInfo("Unit", 'unit',
                                 resize=QtGui.QHeaderView.ResizeToContents),
        ]
        if not units:
            columns = columns[:2]

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
        rows = [ParamInfo(k, v)
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
        if hasattr(self.window(), 'serious'):
            self.window().serious.updateButtons()

    def activate_tab(self, name):
        index = next((i for i in range(self.count())
                      if self.tabText(i).lower() == name.lower()), 0)
        if index != self.currentIndex():
            self.setCurrentIndex(index)

    @property
    def datastore(self):
        return self.currentWidget().datastore
