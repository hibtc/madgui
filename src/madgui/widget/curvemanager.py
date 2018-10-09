"""
Dialog for managing shown curves.
"""

import os

from madgui.qt import QtGui, load_ui
from madgui.widget.tableview import TableItem
from madgui.widget.filedialog import getOpenFileName


class CurveManager(QtGui.QWidget):

    ui_file = 'curvemanager.ui'

    def show_curve(self, i, c) -> ("curves",):
        name, data, style = c

        def set_name(i, c, name):
            self.available[i] = (name, data, style)

        def set_checked(i, c, show):
            shown = i in self.selected
            if show and not shown:
                self.selected.append(i)
            elif not show and shown:
                self.selected.remove(i)
        return [
            TableItem(name, checked=i in self.selected,
                      checkable=True,
                      set_value=set_name, set_checked=set_checked),
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
        self.tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.tab.set_viewmodel(self.show_curve, self.available)

    def connect_signals(self):
        Button = QtGui.QDialogButtonBox
        self.btn_save.clicked.connect(self.on_btn_save)
        self.btn_load.clicked.connect(self.on_btn_load)
        self.btn_box.button(Button.Ok).clicked.connect(self.accept)
        self.tab.connectButtons(self.btn_remove)

    def accept(self):
        self.window().accept()

    @property
    def data(self):
        return self.tab.rows

    def on_btn_save(self):
        model = self.scene.model
        twiss = model.twiss()
        data = {name: twiss[name] for name in model.get_graph_columns()}
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
