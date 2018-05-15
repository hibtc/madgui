"""
Parameter input dialog.
"""

from madgui.qt import QtGui, Qt
from madgui.core.unit import ui_units
import madgui.util.yaml as yaml

import madgui.widget.tableview as tableview


__all__ = [
    'ParamTable',
    'TabParamTables',
]

# TODO: combobox for unit?

class ParamInfo:

    """Row info for the TableView [internal]."""
    # TODO: merge this with madgui.online.api.ParamInfo

    def __init__(self, name, value, expr=None, inform=0, mutable=True):
        self.name = name
        self.value = value
        self.expr = expr
        self.inform = inform
        self.mutable = mutable
        self.unit = ui_units.label(name, value)


def get_unit(param):
    return ui_units.label(param.name, param.value)


def set_value(tab, item, index, value):
    tab.store({item.name: value}, **tab.fetch_args)


def cell_is_mutable(cell):
    return cell.item.mutable and not cell.model.context.readonly


def cell_textcolor(cell):
    return QtGui.QColor(Qt.black if cell.mutable else Qt.darkGray)


class ParamTable(tableview.TableView):

    """
    Input controls to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.
    """

    def __init__(self, fetch, store=None, units=True, data_key=None, **kwargs):
        """Initialize data."""

        self.fetch = fetch
        self.store = store
        self.units = units
        self.readonly = store is None
        self.data_key = data_key
        self.fetch_args = {}

        super().__init__(columns=self.columns, context=self, **kwargs)
        # in case anyone turns the horizontalHeader back on:
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().hide()
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    @property
    def columns(self):
        columns = [
            tableview.ColumnInfo("Parameter", 'name'),
            tableview.ExtColumnInfo(
                "Value", 'value', set_value, padding=50,
                convert=self.units and 'name',
                mutable=cell_is_mutable,
                foreground=cell_textcolor),
            tableview.ColumnInfo(
                "Unit", 'unit', resize=QtGui.QHeaderView.ResizeToContents),
        ]
        return columns if self.units else columns[:2]

    def update(self, **kw):
        """Update dialog from the datastore."""
        self.fetch_args.update(kw)
        # TODO: get along without resetting all the rows?
        rows = self.fetch(**self.fetch_args)
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

    # data im-/export

    exportFilters = [
        ("YAML file", "*.yml", "*.yaml"),
        ("JSON file", "*.json"),
    ]

    importFilters = [
        ("YAML file", "*.yml", "*.yaml"),
    ]

    @property
    def exporter(self):
        return self

    def importFrom(self, filename):
        """Import data from JSON/YAML file."""
        with open(filename, 'rt') as f:
            # Since JSON is a subset of YAML there is no need to invoke a
            # different parser (unless we want to validate the file):
            data = yaml.safe_load(f)
        if self.data_key:
            data = data[self.data_key]
        self.store(data, **self.fetch_args)

    def exportTo(self, filename):
        """Export parameters to YAML file."""
        data = {par.name: par.value
                for par in self.fetch(**self.fetch_args)}
        if self.data_key:
            data = {self.data_key: data}
        with open(filename, 'wt') as f:
            yaml.safe_dump(data, f, default_flow_style=False)


def cmd_font(cell):
    if cell.item.inform:
        font = QtGui.QFont()
        font.setBold(True)
        return font


def set_expr(tab, item, index, value):
    # Replace deferred expressions by their value if `not value`:
    tab.store({item.name: value or item.value}, **tab.fetch_args)


import cpymad.util as _dtypes
def is_expr_mutable(cell):
    return cell.item.dtype not in (_dtypes.PARAM_TYPE_STRING,
                                   _dtypes.PARAM_TYPE_STRING_ARRAY)


class CommandEdit(ParamTable):

    """
    TableView based editor window for MAD-X commands. Used for
    viewing/editing elements.

    In addition to the ParamTables features, this class is capable of
    indicating which parameters were explicitly specified by the user and
    showing the expression!
    """

    _col_style = dict(font=cmd_font)

    columns = [
        tableview.ColumnInfo("Parameter", 'name', **_col_style),
        tableview.ExtColumnInfo("Value", 'value', set_value, padding=50,
                                mutable=True, convert='name'),
        tableview.ColumnInfo("Unit", get_unit,
                             resize=QtGui.QHeaderView.ResizeToContents),
        tableview.ExtColumnInfo("Expression", 'expr', set_expr, padding=50,
                                mutable=is_expr_mutable,
                                resize=QtGui.QHeaderView.ResizeToContents),
    ]


def is_var_mutable(cell):
    return cell.item.inform > 0


# TODO: merge with CommandEdit (by unifying the globals API on cpymad side?)
class GlobalsEdit(ParamTable):

    columns = [
        tableview.ColumnInfo("Name", 'name'),
        tableview.ExtColumnInfo("Value", 'value', set_value, padding=50,
                                mutable=is_var_mutable),
        tableview.ExtColumnInfo("Expression", 'expr', set_expr, padding=50,
                                mutable=True,
                                resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, model):
        self._model = model
        super().__init__(self._fetch, self._model.update_globals)

    def _fetch(self):
        globals = self._model.globals
        return [
            ParamInfo(k.upper(), p.value, p.expr)
            for k, p in globals.cmdpar.items()
            if p.inform > 0
        ]



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
    def exporter(self):
        return self.currentWidget()
