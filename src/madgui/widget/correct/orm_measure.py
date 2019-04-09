import os
import time

import numpy as np
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QWidget

from madgui.util.qt import load_ui
from madgui.widget.tableview import TableItem, delegates

from madgui.online.procedure import Corrector, ProcBot
from .responsetable import ORM_Entry


class MeasureWidget(QWidget):

    ui_file = 'orm_measure.ui'
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
