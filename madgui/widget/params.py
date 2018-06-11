"""
Parameter input dialog.
"""

import os

import cpymad.util as _dtypes

from madgui.qt import QtGui, Qt
from madgui.core.unit import ui_units, get_raw_label
import madgui.util.yaml as yaml

from madgui.widget.tableview import TableView, ColumnInfo


__all__ = [
    'ParamTable',
    'TabParamTables',
]

# TODO: combobox for unit?

class ParamInfo:

    """Row info for the TableView [internal]."""
    # TODO: merge this with madgui.online.api.ParamInfo

    def __init__(self, name, value, expr=None, inform=0, mutable=True,
                 dtype=None, var_type=1):
        self.name = name
        self.value = value
        self.expr = expr
        self.inform = inform
        self.mutable = mutable
        self.unit = ui_units.label(name, value)
        self.dtype = dtype
        self.var_type = var_type


def get_unit(cell):
    param = cell.data
    if not isinstance(param.value, list):
        return ui_units.label(param.name, param.value)


def set_value(cell, value):
    tab, param = cell.context, cell.data
    tab.store({param.name: value}, **tab.fetch_args)


def cell_is_mutable(cell):
    return cell.data.mutable and not cell.context.readonly


def cell_textcolor(cell):
    return QtGui.QColor(Qt.black if cell.mutable else Qt.darkGray)


class ParamTable(TableView):

    """
    Input controls to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.
    """

    def __init__(self, fetch, store=None, units=True, model=None,
                 data_key=None, **kwargs):
        """Initialize data."""

        self.fetch = fetch
        self.store = store
        self.units = units
        self._model = model
        self.readonly = store is None
        self.data_key = data_key
        self.fetch_args = {}

        super().__init__(columns=self.columns, context=self, **kwargs)
        # in case anyone turns the header back on:
        self.header().setHighlightSections(False)
        self.header().hide()
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    @property
    def columns(self):
        columns = [
            ColumnInfo("Parameter", 'name'),
            ColumnInfo("Value", 'value', set_value, padding=50,
                       convert=self.units and 'name',
                       mutable=cell_is_mutable,
                       foreground=cell_textcolor),
            ColumnInfo("Unit", 'unit',
                       resize=QtGui.QHeaderView.ResizeToContents),
        ]
        return columns if self.units else columns[:2]

    def update(self, **kw):
        """Update dialog from the datastore."""
        self.fetch_args.update(kw)
        # TODO: get along without resetting all the rows?
        self.rows = self.fetch(**self.fetch_args)

        # Set initial size:
        if not self.isVisible():
            #self.selectRow(0)
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
    ]

    importFilters = [
        ("YAML file", "*.yml", "*.yaml"),
        ("JSON file", "*.json"),
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
        export_params(filename, data, data_key=self.data_key)


def export_params(filename, data, data_key=None):
    """Export parameters to .YAML/.STR file."""
    if data_key:
        data = {data_key: data}
    _, ext = os.path.splitext(filename.lower())
    if ext in ('.yml', '.yaml'):
        text = yaml.safe_dump(data, default_flow_style=False)
    elif ext == '.str':
        text = ''.join([
            '{} = {!r};\n'.format(k, v)
            for k, v in data.items()
        ])
    else:
        raise ValueError("Unknown file format for export: {!r}"
                            .format(filename))
    with open(filename, 'wt') as f:
        f.write(text)


def cmd_font(cell):
    if cell.data.inform:
        font = QtGui.QFont()
        font.setBold(True)
        return font


def set_expr(cell, value):
    # Replace deferred expressions by their value if `not value`:
    set_value(cell, value or cell.data.value)


def is_expr_mutable(cell):
    return (not isinstance(cell.data.expr, list) and
            cell.data.dtype not in (_dtypes.PARAM_TYPE_STRING,
                                    _dtypes.PARAM_TYPE_STRING_ARRAY))


def get_name(cell):
    return cell.data.name.title()

def get_rows(cell):
    par = cell.data
    if isinstance(par.value, list):
        return [
            ParamInfo('[{}]'.format(idx), val, expr, par.inform,
                      dtype=par.dtype, var_type=par.var_type)
            for idx, (val, expr) in enumerate(zip(par.value, par.expr))
        ]
    return par_rows(cell)

def set_component_value(cell, value):
    tab, par = cell.context, cell.granny.data
    vec = list(par.definition)
    vec[cell.row] = value
    tab.store({par.name: vec}, **tab.fetch_args)

def set_component_expr(cell, value):
    set_component_value(cell, value or cell.data.value)

def get_component_unit(cell):
    units = ui_units.get(cell.granny.data.name)
    row = cell.row
    if isinstance(units, list) and row < len(units):
        return get_raw_label(units[row])

def get_value(cell):
    if not isinstance(cell.data.value, list):
        return cell.data.value

def get_expr(cell):
    if not isinstance(cell.data.expr, list):
        return cell.data.expr

def is_par_mutable(cell):
    return not isinstance(cell.data.value, list)


def get_par_columns(cell):
    return (CommandEdit.vector_columns
            if isinstance(cell.data.value, list) else
            par_columns)


def get_var_name(cell):
    parts = cell.data.name.split('_')
    return "_".join(parts[:1] + list(map(str.upper, parts[1:])))

def is_var_mutable(cell):
    return cell.data.var_type > 0


def par_rows(cell):
    expr = cell.data.expr
    if expr:
        model = cell.context._model
        globals = model.globals
        return [
            p for k in model.madx.expr_vars(expr)
            for p in [globals.cmdpar[k]]
            if p.inform > 0
        ]
    return ()


def set_par_value(cell, value):
    tab, param = cell.context, cell.data
    tab._model.update_globals({param.name: value})


def set_par_expr(cell, value):
    # Replace deferred expressions by their value if `not value`:
    set_par_value(cell, value or cell.data.value)

par_columns = []
par_columns.extend([
    ColumnInfo("Name", get_var_name, rows=par_rows, columns=par_columns),
    ColumnInfo("Value", 'value', set_par_value, padding=50,
               mutable=is_var_mutable),
    ColumnInfo("Unit", lambda c: None, mutable=False),
    ColumnInfo("Expression", 'expr', set_par_expr, padding=50,
               mutable=True,
               resize=QtGui.QHeaderView.ResizeToContents),
])


class CommandEdit(ParamTable):

    """
    TableView based editor window for MAD-X commands. Used for
    viewing/editing elements.

    In addition to the ParamTables features, this class is capable of
    indicating which parameters were explicitly specified by the user and
    showing the expression!
    """

    _col_style = dict(font=cmd_font)

    vector_columns = [
        ColumnInfo(None, get_name, rows=par_rows, columns=par_columns, **_col_style),
        # TODO: fix conversion and get_unit
        ColumnInfo(None, 'value', set_component_value, padding=50,
                   mutable=True, convert='name'),
        ColumnInfo(None, get_component_unit,
                   resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo(None, 'expr', set_component_expr, padding=50,
                   mutable=is_expr_mutable,
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    columns = [
        ColumnInfo("Parameter", get_name,
                   rows=get_rows, columns=get_par_columns, **_col_style),
        ColumnInfo("Value", get_value, set_value, padding=50,
                   mutable=is_par_mutable, convert='name'),
        ColumnInfo("Unit", get_unit,
                   resize=QtGui.QHeaderView.ResizeToContents),
        ColumnInfo("Expression", get_expr, set_expr, padding=50,
                   mutable=is_expr_mutable,
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]


var_columns = []
var_columns.extend([
    ColumnInfo("Name", get_var_name, rows=par_rows, columns=var_columns),
    ColumnInfo("Value", 'value', set_value, padding=50,
               mutable=is_var_mutable),
    ColumnInfo("Expression", 'expr', set_expr, padding=50,
               mutable=True,
               resize=QtGui.QHeaderView.ResizeToContents),
])


# TODO: merge with CommandEdit (by unifying the globals API on cpymad side?)
class GlobalsEdit(ParamTable):

    columns = var_columns

    exportFilters = [
        ("Strength file", "*.str"),
        ("YAML file", "*.yml", "*.yaml"),
    ]

    def __init__(self, model):
        super().__init__(self._fetch, model.update_globals, model=model)

    def _fetch(self):
        globals = self._model.globals
        return [p for k, p in globals.cmdpar.items() if p.var_type > 0]



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
