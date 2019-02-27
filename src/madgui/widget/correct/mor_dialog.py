"""
Multi grid correction method.
"""

from collections import namedtuple
import os
import time

import numpy as np
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QWidget

from madgui.util.collections import List
from madgui.util.history import History
from madgui.util.qt import Queued, load_ui
from madgui.util import yaml
from madgui.widget.dialog import Dialog
from madgui.widget.tableview import TableItem, delegates

from madgui.online.procedure import Corrector, ProcBot


ORM_Entry = namedtuple('ORM_Entry', ['monitor', 'knob', 'x', 'y'])


class CorrectorWidget(QWidget):

    ui_file = 'mor_dialog.ui'
    data_key = 'multi_grid'     # can reuse the multi grid configuration

    def get_orm_row(self, i, r) -> (
            "Steerer", "Monitor", "X [mm/mrad]", "Y [mm/mrad]"):
        return [
            TableItem(r.knob),
            TableItem(r.monitor),
            TableItem(r.x),     # TODO: set_value and delegate
            TableItem(r.y),
        ]

    def __init__(self, session):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.orm = List()
        self.saved_orms = History()
        self.corrector = Corrector(session)
        self.corrector.start()
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def closeEvent(self, event):
        self.corrector.stop()
        self.view.del_curve("readouts")

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.apply()
        self.update_status()

    def init_controls(self):
        self.configSelect.set_corrector(self.corrector, self.data_key)
        self.monitorTable.set_corrector(self.corrector)
        self.targetsTable.set_corrector(self.corrector)
        self.resultsTable.set_corrector(self.corrector)
        self.ormTable.set_viewmodel(self.get_orm_row, self.orm)
        self.view = self.corrector.session.window().open_graph('orbit')

    def set_initial_values(self):
        self.fitButton.setFocus()
        self.update_status()

    def connect_signals(self):
        self.corrector.setup_changed.connect(self.update_status)
        self.corrector.saved_optics.changed.connect(self.update_ui)
        self.saved_orms.changed.connect(self.update_ui)
        self.computeButton.clicked.connect(self.compute_orm)
        self.measureButton.clicked.connect(self.measure_orm)
        self.loadButton.clicked.connect(self.load_orm)
        self.saveButton.clicked.connect(self.save_orm)
        self.fitButton.clicked.connect(self.update_fit)
        self.applyButton.clicked.connect(self.on_execute_corrections)
        self.prevButton.setDefaultAction(
            self.corrector.saved_optics.create_undo_action(self))
        self.nextButton.setDefaultAction(
            self.corrector.saved_optics.create_redo_action(self))
        self.prevORMButton.setDefaultAction(
            self.saved_orms.create_undo_action(self))
        self.nextORMButton.setDefaultAction(
            self.saved_orms.create_redo_action(self))

    def update_status(self):
        self.corrector.update_vars()
        self.update_ui()

    def measure_orm(self):
        widget = MeasureWidget(self.corrector)
        dialog = Dialog(self.window())
        dialog.setWidget(widget)
        dialog.setWindowTitle("ORM scan")
        if dialog.exec_():
            self.saved_orms.push(widget.final_orm)

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

    def update_fit(self):
        """Calculate initial positions / corrections."""
        indexed = {}
        for entry in self.orm:
            monitor = entry.monitor.lower()
            knob = entry.knob.lower()
            indexed.setdefault(monitor, {})[knob] = [entry.x, entry.y]

        orm = np.array([
            [
                indexed[mon.lower()][var.lower()]
                for var in self.corrector.variables
            ]
            for mon in self.corrector.monitors
        ])
        orm = orm.transpose((0, 2, 1)).reshape(
            (2*len(self.corrector.monitors), len(self.corrector.variables)))
        results = self.corrector._compute_steerer_corrections_orm(orm)

        self.corrector.saved_optics.push(results)

    def update_ui(self):
        saved_optics = self.corrector.saved_optics
        self.applyButton.setEnabled(
            self.corrector.online_optic != saved_optics())
        if saved_optics() is not None:
            self.corrector.variables.touch()
        if self.saved_orms() is not None:
            self.orm[:] = self.saved_orms()
        self.draw_idle()

    @Queued.method
    def draw_idle(self):
        self.view.show_monitor_readouts(self.corrector.monitors[:])

    @property
    def frame(self):
        return self.corrector.session.window()


class MeasureWidget(QWidget):

    ui_file = 'mor_measure.ui'
    extension = '.orm_measurement.yml'

    def __init__(self, corrector):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.corrector = Corrector(corrector.session, False)
        self.corrector.setup({
            'monitors': corrector.monitors,
            'optics': corrector.variables,
        })
        self.corrector.start()
        self.bot = ProcBot(self, self.corrector)

        elem_by_knob = {}
        for elem in corrector.model.elements:
            for knob in corrector.model.get_elem_knobs(elem):
                elem_by_knob.setdefault(knob.lower(), elem)

        self.steerers = [
            elem_by_knob[v.lower()]
            for v in corrector.variables
        ]

        self.corrector.add_record = self.add_record
        self.raw_records = []

        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def add_record(self, step, shot):
        if shot == 0:
            self.raw_records.append([])
        records = {r.name: r.data for r in self.corrector.readouts}
        self.raw_records[-1].append(records)
        self.corrector.write_shot(step, shot, {
            monitor: [data['posx'], data['posy'],
                      data['envx'], data['envy']]
            for monitor, data in records.items()
        })

    def sizeHint(self):
        return QSize(600, 400)

    def init_controls(self):
        self.opticsTable.set_viewmodel(
            self.get_corrector_row, unit=(None, 'kick'))

    def set_initial_values(self):
        self.d_phi = {}
        self.default_dphi = 2e-4
        self.opticsTable.rows[:] = self.steerers
        self.fileEdit.setText(
            "{date}_{time}_{sequence}_{monitor}"+self.extension)
        self.update_ui()

    def connect_signals(self):
        self.startButton.clicked.connect(self.start_bot)
        self.cancelButton.clicked.connect(self.cancel)

    def get_corrector_row(self, i, c) -> ("Kicker", "ΔΦ"):
        return [
            TableItem(c.name),
            TableItem(self.d_phi.get(c.name.lower(), self.default_dphi),
                      name='kick', set_value=self.set_kick,
                      delegate=delegates[float]),
        ]

    def set_kick(self, i, c, value):
        self.d_phi[c.name.lower()] = value

    @property
    def running(self):
        return bool(self.bot) and self.bot.running

    def closeEvent(self, event):
        self.bot.cancel()
        super().closeEvent(event)

    def update_ui(self):
        running = self.running
        valid = bool(self.corrector.optic_params)
        self.cancelButton.setEnabled(running)
        self.startButton.setEnabled(not running and valid)
        self.numIgnoredSpinBox.setEnabled(not running)
        self.numUsedSpinBox.setEnabled(not running)
        self.opticsTable.setEnabled(not running)
        self.progressBar.setEnabled(running)
        self.progressBar.setRange(0, self.bot.totalops)
        self.progressBar.setValue(self.bot.progress)

    def set_progress(self, progress):
        self.progressBar.setValue(progress)

    def update_fit(self):
        """Called when procedure finishes succesfully."""
        full_data = np.array([
            [
                np.mean([
                    [shot[monitor]['posx'], shot[monitor]['posy']]
                    for shot in series
                ], axis=0)
                for monitor in self.corrector.monitors
            ]
            for series in self.raw_records
        ])
        differences = full_data[1:] - full_data[[0]]
        deltas = [
            self.d_phi.get(v.lower(), self.default_dphi)
            for v in self.corrector.variables
        ]
        self.final_orm = [
            ORM_Entry(mon, var, *differences[i_var, i_mon] / deltas[i_var])
            for i_var, var in enumerate(self.corrector.variables)
            for i_mon, mon in enumerate(self.corrector.monitors)
        ]

        self.window().accept()

    def start_bot(self):
        self.corrector.set_optics_delta(self.d_phi, self.default_dphi)
        self.bot.start(
            self.numIgnoredSpinBox.value(),
            self.numUsedSpinBox.value())

        now = time.localtime(time.time())
        fname = os.path.join(
            '.',
            self.fileEdit.text().format(
                date=time.strftime("%Y-%m-%d", now),
                time=time.strftime("%H-%M-%S", now),
                sequence=self.corrector.model.seq_name,
                monitor=self.corrector.monitors[-1],
            ))

        self.corrector.open_export(fname)

    def cancel(self):
        self.bot.cancel()
        self.window().reject()

    def log(self, text, *args, **kwargs):
        formatted = text.format(*args, **kwargs)
        self.logEdit.appendPlainText(formatted)
