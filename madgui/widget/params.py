"""
Parameter input dialog.
"""

import os

import cpymad.util as _dtypes

from madgui.qt import QtGui, Qt
from madgui.core.unit import ui_units, get_raw_label
from madgui.util.qt import bold
import madgui.util.yaml as yaml

from madgui.widget.tableview import TableView, TableItem


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

        super().__init__(**kwargs)
        self.set_rowgetter(self.get_param_row, titles=self.sections)
        # in case anyone turns the header back on:
        self.header().setHighlightSections(False)
        self.header().hide()
        self.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)

        self.setSizePolicy(QtGui.QSizePolicy.Preferred,
                           QtGui.QSizePolicy.Preferred)

    @property
    def sections(self):
        titles = self.get_param_row.__annotations__['return']
        return titles if self.units else titles[:-1]

    def get_param_row(self, item) -> ("Parameter", "Value", "Unit"):
        p = item.data
        mutable = p.mutable and not self.readonly
        textcolor = QtGui.QColor(Qt.black if mutable else Qt.darkGray)
        return [
            TableItem(p.name),
            TableItem(p.value, set_value=self.set_value,
                      name=self.units and p.name,
                      mutable=mutable,
                      foreground=textcolor),
            TableItem(ui_units.label(p.name, p.value)),
        ]

    def set_value(self, item, value):
        par = item.parent.data
        self.store({par.name: value}, **self.fetch_args)

    def set_expr(self, item, value):
        # Replace deferred expressions by their value if `not value`:
        par = item.parent.data
        self.set_value(item, value or par.value)

    def par_rows(self, par):
        expr = par.expr
        if expr:
            model = self._model
            globals = model.globals
            return [
                p for k in model.madx.expr_vars(expr)
                for p in [globals.cmdpar[k]]
                if p.inform > 0
            ]
        return ()

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


def is_expr_mutable(par):
    return (not isinstance(par.expr, list) and
            par.dtype not in (_dtypes.PARAM_TYPE_STRING,
                              _dtypes.PARAM_TYPE_STRING_ARRAY))


def get_var_name(name):
    parts = name.split('_')
    return "_".join(parts[:1] + list(map(str.upper, parts[1:])))


class CommandEdit(ParamTable):

    """
    TableView based editor window for MAD-X commands. Used for
    viewing/editing elements.

    In addition to the ParamTables features, this class is capable of
    indicating which parameters were explicitly specified by the user and
    showing the expression!
    """

    def get_param_row(self, item) -> ("Parameter", "Value", "Unit", "Expression"):
        p = item.data
        is_vector = isinstance(p.value, list)
        name = p.name.title()
        font = bold() if p.inform else None
        value = None if is_vector else p.value
        expr = None if is_vector else p.expr
        unit = None if is_vector else ui_units.label(p.name)
        mutable = not is_vector
        rows = self.vec_rows(p) if is_vector else self.par_rows(p)
        rowitems = self.get_vector_row if is_vector else self.get_knob_row
        return [
            TableItem(name, rows=rows, rowitems=rowitems, font=font),
            TableItem(value, set_value=self.set_value, mutable=mutable, name=p.name),
            TableItem(unit),
            TableItem(expr, set_value=self.set_expr, mutable=is_expr_mutable(p)),
        ]

    def get_knob_row(self, item):
        p = item.data
        return [
            TableItem(get_var_name(p.name), rows=self.par_rows(p),
                      rowitems=self.get_knob_row),
            TableItem(p.value, set_value=self.set_par_value, mutable=p.var_type > 0),
            TableItem(None, mutable=False),
            TableItem(p.expr, set_value=self.set_par_expr, mutable=True),
        ]

    def get_vector_row(self, item):
        p = item.data
        font = bold() if p.inform else None
        return [
            TableItem(p.name.title(), rows=self.par_rows(p),
                      rowitems=self.get_knob_row, font=font),
            TableItem(p.value, set_value=self.set_comp_value, mutable=True, name=p.name),
            TableItem(self.get_comp_unit(item)),
            TableItem(p.expr, set_value=self.set_comp_expr, mutable=is_expr_mutable(p)),
        ]

    def set_par_value(self, item, value):
        par = item.parent.data
        self._model.update_globals({par.name: value})

    def set_par_expr(self, item, value):
        par = item.parent.data
        # Replace deferred expressions by their value if `not value`:
        self.set_par_value(item, value or par.value)

    def vec_rows(self, par):
        return [
            ParamInfo('[{}]'.format(idx), val, expr, par.inform,
                    dtype=par.dtype, var_type=par.var_type)
            for idx, (val, expr) in enumerate(zip(par.value, par.expr))
        ]

    def set_comp_value(self, item, value):
        par = item.granny.data
        vec = list(par.definition)
        vec[item.parent.index] = value
        self.store({par.name: vec}, **self.fetch_args)

    def set_comp_expr(self, item, value):
        par = item.granny.parent.data
        self.set_comp_value(item, value or par.value)

    def get_comp_unit(self, item):
        par = item.granny.data
        units = ui_units.get(par.name)
        row = item.index
        if isinstance(units, list) and row < len(units):
            return get_raw_label(units[row])


# TODO: merge with CommandEdit (by unifying the globals API on cpymad side?)
class GlobalsEdit(ParamTable):

    def get_param_row(self, item) -> ("Name", "Value", "Expression"):
        p = item.data
        return [
            TableItem(get_var_name(p.name),
                      rows=self.par_rows(p), rowitems=self.get_param_row),
            TableItem(p.value, set_value=self.set_value, mutable=p.var_type > 0),
            TableItem(p.expr, set_value=self.set_expr, mutable=True),
        ]

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
