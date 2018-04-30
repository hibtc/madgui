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


def get_unit(param):
    return ui_units.label(param.name, param.value)


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
        self.use_units = units

        super().__init__(columns=self.columns, **kwargs)
        # in case anyone turns the horizontalHeader back on:
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().hide()
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    @property
    def columns(self):
        datastore = self.datastore
        setter = partial(set_value, datastore)
        mutable = lambda cell: datastore.mutable(cell.item.name)
        textcolor = lambda cell: QtGui.QColor(Qt.black if cell.mutable else Qt.darkGray)
        columns = [
            tableview.ColumnInfo("Parameter", 'name'),
            tableview.ColumnInfo("Value", 'value', setter, padding=50,
                                 convert=self.use_units and 'name',
                                 mutable=mutable,
                                 foreground=textcolor),
            tableview.ColumnInfo("Unit", 'unit',
                                 resize=QtGui.QHeaderView.ResizeToContents),
        ]
        return columns if self.use_units else columns[:2]

    def update(self, **kw):
        """Update dialog from the datastore."""
        # TODO: get along without resetting all the rows?
        rows = self.retrieve_rows(**kw)
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

    def retrieve_rows(self, **kw):
        self.datastore.kw.update(kw)
        return [ParamInfo(k, v) for k, v in self.datastore.get().items()]

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


def cmd_background(cell):
    if cell.item.inform:
        return QtGui.QColor(Qt.darkCyan)


from cpymad.util import is_identifier
def cmd_mutable(cell):
    expr = cell.item.expr
    return not expr or isinstance(expr, list) or is_identifier(expr)


def cmd_set_attr(view, item, idx, value):
    expr = item.expr
    if expr and not isinstance(expr, list) and is_identifier(expr):
        view.command._madx.globals[expr] = value
    else:
        setattr(view.command, item.name, value)
    item.value = value
    item.inform = 1

def cmd_set_expr(view, item, idx, value):
    setattr(view.command, item.name, value)
    # TODO: update item.value!
    item.expr = value
    item.inform = 1


class CommandEdit(ParamTable):

    """
    TableView based editor window for MAD-X commands. Used for
    viewing/editing elements.

    In addition to the ParamTables features, this class is capable of
    indicating which parameters were explicitly specified by the user and
    showing the expression!
    """

    _col_style = dict(backgroundColor=cmd_background)

    columns = [
        tableview.ColumnInfo("Parameter", 'name', **_col_style),
        tableview.ExtColumnInfo("Value", 'value', cmd_set_attr, padding=50,
                                mutable=cmd_mutable, convert='name',
                                **_col_style),
        tableview.ColumnInfo("Unit", get_unit,
                             resize=QtGui.QHeaderView.ResizeToContents,
                             **_col_style),
        tableview.ExtColumnInfo("Expression", 'expr', cmd_set_expr, padding=50,
                                mutable=True,
                                resize=QtGui.QHeaderView.ResizeToContents,
                                **_col_style),
    ]

    def __init__(self, retrieve):
        self.retrieve = retrieve
        self.command = None
        super().__init__(None, context=self)

    def retrieve_rows(self, **kw):
        self.command = self.retrieve(**kw)
        return list(self.command.cmdpar.values())


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
