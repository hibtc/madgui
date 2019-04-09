"""
Parameter input dialog.
"""

# TODO: combobox for unit?

__all__ = [
    'ParamInfo',
    'ParamTable',
    'CommandEdit',
    'GlobalsEdit',
    'MatrixTable',
    'TabParamTables',
    'model_params_dialog',
]

from functools import partial

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QAbstractItemView, QSizePolicy, QTabWidget

from cpymad.types import dtype_to_native

from madgui.util.unit import ui_units, get_raw_label
from madgui.util.qt import bold
from madgui.util.export import export_params, import_params

from madgui.widget.tableview import (
    TreeView, TableItem, ExpressionDelegate, delegates)


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


class ParamTable(TreeView):

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
        self.set_viewmodel(self.get_param_row, titles=self.sections)
        self.header().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

        self.setSizePolicy(QSizePolicy.Preferred,
                           QSizePolicy.Preferred)

    @property
    def sections(self):
        titles = self.get_param_row.__annotations__['return']
        return titles if self.units else titles[:-1]

    def get_param_row(self, i, p) -> ("Parameter", "Value", "Unit"):
        font = bold() if p.inform else None
        mutable = p.mutable and not self.readonly
        textcolor = QColor(Qt.black if mutable else Qt.darkGray)
        delegate = delegates.get(dtype_to_native.get(p.dtype))
        extra_args = {'delegate': delegate} if delegate else {}
        return [
            TableItem(p.name, font=font),
            TableItem(p.value, set_value=self.set_value,
                      name=self.units and p.name,
                      mutable=mutable,
                      foreground=textcolor,
                      **extra_args),
            TableItem(ui_units.label(p.name, p.value)),
        ]

    def set_value(self, i, par, value):
        self.store({par.name: value}, **self.fetch_args)

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
            self.resizeColumnsToContents()
            self.updateGeometries()

    def keyPressEvent(self, event):
        """<Enter>: open editor; <Delete>/<Backspace>: remove value."""
        if self.state() == QAbstractItemView.NoState:
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
        data = import_params(filename, data_key=self.data_key)
        self.store(data, **self.fetch_args)

    def exportTo(self, filename):
        """Export parameters to YAML file."""
        data = {par.name: par.value
                for par in self.fetch_params(**self.fetch_args)}
        export_params(filename, data, data_key=self.data_key)

    def fetch_params(self, **fetch_args):
        return self.fetch(**fetch_args)


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

    def get_param_row(self, i, p) -> ("Parameter", "Value", "Unit"):
        is_vector = isinstance(p.value, list)
        name = p.name.title()
        font = bold() if p.inform else None
        value = None if is_vector else p.value
        expr = None if is_vector else p.expr
        unit = None if is_vector else ui_units.label(p.name)
        mutable = not is_vector
        rows = self.vec_rows(p) if is_vector else self.par_rows(p)
        rowitems = (partial(self.get_vector_row, p) if is_vector
                    else self.get_knob_row)
        delegate = {}
        if dtype_to_native.get(p.dtype) in (bool, int, float):
            delegate = {'delegate': ExpressionDelegate()}
        return [
            TableItem(name, rows=rows, rowitems=rowitems, font=font),
            TableItem(value, set_value=self.set_value, mutable=mutable,
                      name=p.name, toolTip=expr, expr=expr, **delegate),
            TableItem(unit),
        ]

    def get_knob_row(self, i, p):
        mutable = p.var_type > 0
        return [
            TableItem(get_var_name(p.name), rows=self.par_rows(p),
                      rowitems=self.get_knob_row),
            TableItem(p.value, set_value=self.set_par_value, mutable=mutable,
                      name=p.name, toolTip=p.expr, expr=p.expr,
                      delegate=ExpressionDelegate()),
            TableItem(None, mutable=False),
        ]

    def get_vector_row(self, parent, i, p):
        font = bold() if p.inform else None
        set_value = partial(self.set_comp_value, parent)
        return [
            TableItem(p.name.title(), rows=self.par_rows(p),
                      rowitems=self.get_knob_row, font=font),
            TableItem(p.value, set_value=set_value, mutable=True, name=p.name),
            TableItem(self.get_comp_unit(parent, i)),
        ]

    def set_par_value(self, i, par, value):
        self._model.update_globals({par.name: value})

    def vec_rows(self, par):
        return [
            ParamInfo('[{}]'.format(idx), val, expr, par.inform,
                      dtype=par.dtype, var_type=par.var_type)
            for idx, (val, expr) in enumerate(zip(par.value, par.expr))
        ]

    def set_comp_value(self, par, i, _, value):
        vec = list(par.definition)
        vec[i] = value
        self.store({par.name: vec}, **self.fetch_args)

    def get_comp_unit(self, par, i):
        units = ui_units.get(par.name)
        if isinstance(units, list) and i < len(units):
            return get_raw_label(units[i])


# TODO: merge with CommandEdit (by unifying the globals API on cpymad side?)
class GlobalsEdit(ParamTable):

    def get_param_row(self, i, p) -> ("Name", "Value"):
        return [
            TableItem(get_var_name(p.name),
                      rows=self.par_rows(p), rowitems=self.get_param_row),
            TableItem(p.value, set_value=self.set_value, mutable=p.var_type > 0,
                      name=p.name, toolTip=p.expr, expr=p.expr,
                      delegate=ExpressionDelegate()),
        ]

    exportFilters = [
        ("Strength file", "*.str"),
        ("YAML file", "*.yml", "*.yaml"),
    ]

    def __init__(self, model, **kwargs):
        super().__init__(
            self._fetch, model.update_globals, model=model, **kwargs)

    def _fetch(self):
        globals = self._model.globals
        return [p for k, p in globals.cmdpar.items() if p.var_type > 0]


class MatrixTable(ParamTable):

    def __init__(self, fetch, shape, get_name, **kwargs):
        self.shape = shape
        self.get_name = get_name
        super().__init__(fetch, **kwargs)
        self.header().show()

    @property
    def sections(self):
        return [
            self.get_name('[i]', j+1)
            for j in range(self.shape[1])
        ]

    def get_param_row(self, i, row):
        return [
            TableItem(val, toolTip=self._tooltip(name, val),
                      name=self.units and name)
            for j, val in enumerate(row)
            for name in [self.get_name(i+1, j+1)]
        ]

    def _tooltip(self, name, value):
        if self.units:
            suffix = ' ' + ui_units.label(name, value)
        else:
            suffix = ''
        return '{} = {}{}'.format(name, value, suffix)

    def fetch_params(self, **fetch_args):
        data = self.fetch(**fetch_args)
        return [
            ParamInfo(self.get_name(i+1, j+1), data[i][j])
            for i in range(self.shape[0])
            for j in range(self.shape[1])
        ]


class TabParamTables(QTabWidget):

    """
    TabWidget that manages multiple ParamTables inside.
    """

    def __init__(self, tabWidget=()):
        super().__init__()
        self.kw = {}
        self.setTabsClosable(False)
        for name, page in tabWidget:
            self.addTab(page, name)
        self.currentChanged.connect(self.update)

    def update(self):
        self.currentWidget().update(**self.kw)
        if hasattr(self.window(), 'serious'):
            self.window().serious.updateButtons()

    @property
    def exporter(self):
        return self.currentWidget()


def model_params_dialog(model, parent=None, folder='.'):
    """Create a dialog to edit parameters of a given Model."""
    from madgui.widget.elementinfo import EllipseWidget
    from madgui.widget.dialog import Dialog

    widget = TabParamTables([
        ('Twiss', ParamTable(model.fetch_twiss, model.update_twiss_args,
                             data_key='twiss')),
        ('Beam', ParamTable(model.fetch_beam, model.update_beam,
                            data_key='beam')),
        ('Globals', GlobalsEdit(model, data_key='globals')),
        ('Ellipse', EllipseWidget(model)),
    ])
    widget.update()
    # NOTE: Ideally, we'd like to update after changing initial conditions
    # (rather than after twiss), but changing initial conditions usually
    # implies also updating twiss, so this is a good enough approximation
    # for now:
    model.updated.connect(widget.update)

    dialog = Dialog(parent)
    dialog.setSimpleExportWidget(widget, folder)
    dialog.setWindowTitle("Initial conditions")
    return dialog
