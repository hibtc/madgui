"""
Dialog for managing curves in a :class:`~madgui.plot.twissfigure.TwissFigure`.
"""

__all__ = [
    'CurveManager',
]

import os

import numpy as np
from PyQt5.QtWidgets import QAbstractItemView, QDialogButtonBox, QWidget

from madgui.util.qt import load_ui
from madgui.widget.tableview import TableItem, delegates
from madgui.widget.filedialog import getOpenFileName

from madgui.plot.twissfigure import UserData

Button = QDialogButtonBox


class CurveManager(QWidget):

    ui_file = 'curvemanager.ui'

    def show_curve(self, i, c) -> ("curves",):
        def set_name(i, c, name):
            if not self.plotted.node(name):
                self.available[i] = UserData(name, c.data, c.style)

        def set_checked(i, c, show):
            self.plotted.node(c.name).enable(show)
        return [
            TableItem(c.name, checked=self.plotted.node(c.name).enabled(),
                      checkable=True, delegate=delegates[str],
                      set_value=set_name, set_checked=set_checked),
        ]

    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.available = scene.user_tables
        self.plotted = scene.scene_graph.node('user_curves')
        self.folder = scene.model.path
        load_ui(self, __package__, self.ui_file)
        self.init_controls()
        self.connect_signals()

    def init_controls(self):
        self.curveTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.curveTable.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.curveTable.set_viewmodel(self.show_curve, self.available)

    def connect_signals(self):
        self.saveButton.clicked.connect(self.on_btn_save)
        self.loadButton.clicked.connect(self.on_btn_load)
        self.buttonBox.button(Button.Ok).clicked.connect(self.accept)
        self.curveTable.connectRemoveButton(self.removeButton)

    def accept(self):
        self.window().accept()

    @property
    def data(self):
        return self.curveTable.rows

    def on_btn_save(self):
        scene = self.scene
        twiss = scene.model.twiss()
        data = {name: twiss[name] for name in scene.get_graph_columns()}
        style = scene.config['reference_style']
        scene.snapshot_num += 1
        name = "snapshot {}".format(scene.snapshot_num)
        scene.add_curve(name, data, style)
        self.curveTable.edit(
            self.curveTable.model().index(len(self.available)-1, 0))

    def on_btn_load(self):
        filename = getOpenFileName(
            self.window(), 'Open data file for comparison',
            self.folder, self.dataFileFilters)
        if filename:
            self.folder, basename = os.path.split(filename)
            data = self.load_file(filename)
            style = self.scene.config['reference_style']
            self.scene.add_curve(basename, data, style)

    dataFileFilters = [
        ("Text files", "*.txt", "*.dat"),
        ("TFS tables", "*.tfs", "*.twiss"),
    ]

    def load_file(self, filename):
        table = self._load_table(filename)
        elems = self.scene.model.elements
        if 'name' in table and 's' not in table:
            table['s'] = np.array([
                elem.position + elem.length if elem else float("nan")
                for name in table['name']
                for elem in [elems[name] if name in elems else None]
            ])
        return table

    def _load_table(self, filename):
        from madgui.util.table import read_table, read_tfsfile
        if not filename.lower().endswith(('.tfs', '.twiss')):
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
