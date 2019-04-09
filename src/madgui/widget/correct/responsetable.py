import os
from collections import namedtuple

from PyQt5.QtWidgets import QWidget

from madgui.util import yaml
from madgui.util.history import History
from madgui.util.collections import List
from madgui.util.qt import load_ui
from madgui.widget.dialog import Dialog
from madgui.widget.tableview import TableItem


ORM_Entry = namedtuple('ORM_Entry', ['monitor', 'knob', 'x', 'y'])


class ResponseTable(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_ui(self, __package__, 'responsetable.ui')

    def set_corrector(self, corrector):
        self.corrector = corrector
        self.orm = List()
        self.saved_orms = History()
        self.saved_orms.changed.connect(self.on_orms_changed)
        self.computeButton.clicked.connect(self.compute_orm)
        self.measureButton.clicked.connect(self.measure_orm)
        self.loadButton.clicked.connect(self.load_orm)
        self.saveButton.clicked.connect(self.save_orm)
        self.prevORMButton.setDefaultAction(
            self.saved_orms.create_undo_action(self))
        self.nextORMButton.setDefaultAction(
            self.saved_orms.create_redo_action(self))
        self.ormTable.set_viewmodel(self.get_orm_row, self.orm)

    def get_orm_row(self, i, r) -> (
            "Steerer", "Monitor", "X [mm/mrad]", "Y [mm/mrad]"):
        return [
            TableItem(r.knob),
            TableItem(r.monitor),
            TableItem(r.x),     # TODO: set_value and delegate
            TableItem(r.y),
        ]

    folder = '.'
    exportFilters = [
        ("YAML file", "*.yml"),
    ]

    def load_orm(self):
        from madgui.widget.filedialog import getOpenFileName
        filename = getOpenFileName(
            self.window(), 'Load Orbit Responses', self.folder,
            self.exportFilters)
        if filename:
            self.load_from(filename)

    def save_orm(self):
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self.window(), 'Export Orbit Responses', self.folder,
            self.exportFilters)
        if filename:
            self.export_to(filename)
            self.folder, _ = os.path.split(filename)

    def load_from(self, filename):
        data = yaml.load_file(filename)['orm']
        self.saved_orms.push([
            ORM_Entry(*entry)
            for entry in data
        ])

    def export_to(self, filename):
        yaml.save_file(filename, {
            'orm': [
                [entry.monitor, entry.knob, entry.x, entry.y]
                for entry in self.orm
            ]
        }, default_flow_style=True)

    def compute_orm(self):
        # TODO: for generic knobs (anything other than hkicker/vkicker->kick)
        # we need to use numerical ORM
        corrector = self.corrector
        sectormap = corrector.compute_sectormap().reshape((
            len(corrector.monitors), 2, len(corrector.variables)))
        self.saved_orms.push([
            ORM_Entry(mon, var, *sectormap[i_mon, :, i_var])
            for i_var, var in enumerate(corrector.variables)
            for i_mon, mon in enumerate(corrector.monitors)
        ])

    def measure_orm(self):
        from .orm_measure import MeasureWidget
        widget = MeasureWidget(self.corrector)
        dialog = Dialog(widget=widget, parent=self.window())
        if dialog.exec_():
            self.saved_orms.push(widget.final_orm)

    def on_orms_changed(self):
        self.orm[:] = self.saved_orms() or []
