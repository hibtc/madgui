"""
Dialog for managing shown curves.
"""

import os

from madgui.qt import QtGui, load_ui
from madgui.widget.tableview import ColumnInfo
from madgui.widget.filedialog import getOpenFileName


def get_curve_name(cell):
    name, data, style = cell.data
    return name

def set_curve_name(cell, name):
    i, mgr = cell.row, cell.context
    _, data, style = cell.data
    mgr.available[i] = (name, data, style)

def get_curve_show(cell):
    i, mgr = cell.row, cell.context
    return i in mgr.selected

def set_curve_show(cell, show):
    i, mgr = cell.row, cell.context
    shown = i in mgr.selected
    if show and not shown:
        mgr.selected.append(i)
    elif not show and shown:
        mgr.selected.remove(i)


class CurveManager(QtGui.QWidget):

    ui_file = 'curvemanager.ui'

    columns = [
        ColumnInfo("curves", get_curve_name, set_curve_name,
                   checked=get_curve_show, setChecked=set_curve_show,
                   checkable=True,
                   resize=QtGui.QHeaderView.Stretch),
    ]

    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.available = scene.loaded_curves
        self.selected = scene.shown_curves
        self.folder = scene.model.path
        load_ui(self, __package__, self.ui_file)
        self.init_controls()
        self.connect_signals()

    def init_controls(self):
        self.tab.header().setHighlightSections(False)
        self.tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.tab.set_columns(self.columns, self.available, self)

    def connect_signals(self):
        self.btn_save.clicked.connect(self.on_btn_save)
        self.btn_load.clicked.connect(self.on_btn_load)
        self.tab.connectButtons(self.btn_remove)

    @property
    def data(self):
        return self.tab.rows

    def on_btn_save(self):
        model = self.scene.model
        data = {name: model.get_twiss_column(name)
                for name in model.get_graph_columns()}
        style = self.scene.config['reference_style']
        self.scene.snapshot_num += 1
        name = "snapshot {}".format(self.scene.snapshot_num)
        self.available.append((name, data, style))
        self.tab.edit(self.tab.model().index(len(self.available)-1, 0))

    def on_btn_load(self):
        filename = getOpenFileName(
            self.window(), 'Open data file for comparison',
            self.folder, self.dataFileFilters)
        if filename:
            self.folder, basename = os.path.split(filename)
            data = self.load_file(filename)
            style = self.scene.config['reference_style']
            self.available.append((basename, data, style))

    dataFileFilters = [
        ("Text files", "*.txt", "*.dat"),
        ("TFS tables", "*.tfs", "*.twiss"),
    ]

    def load_file(self, filename):
        from madgui.util.table import read_table, read_tfsfile
        if filename.lower().rsplit('.')[-1] not in ('tfs', 'twiss'):
            return read_table(filename)
        model = self.scene.model
        table = read_tfsfile(filename)
        data = table.copy()
        # TODO: this should be properly encapsulated:
        if 'sig11' in data:
            data['envx'] = data['sig11'] ** 0.5
        elif 'betx' in data:
            # FIXME TODO: use position-dependent emittances…
            try:
                ex = table.summary['ex']
            except ValueError:
                ex = model.ex()
            data['envx'] = (data['betx'] * ex) ** 0.5
        if 'sig33' in data:
            data['envy'] = data['sig33']**0.5
        elif 'bety' in data:
            try:
                ey = table.summary['ey']
            except ValueError:
                ey = model.ey()
            data['envy'] = (data['bety'] * ey) ** 0.5
        return data
