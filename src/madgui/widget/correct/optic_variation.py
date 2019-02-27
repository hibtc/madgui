"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

__all__ = [
    'CorrectorWidget',
]

from functools import partial
import logging

import numpy as np
from PyQt5.QtWidgets import QAbstractItemView

from madgui.util.unit import change_unit, get_raw_label
from madgui.widget.tableview import TableItem, delegates

from madgui.online.procedure import ProcBot
from .multi_grid import CorrectorWidget as _Widget


class CorrectorWidget(_Widget):

    ui_file = 'optic_variation.ui'
    data_key = 'optic_variation'
    multi_step = True

    def get_optic_row(self, i, o) -> ("#", "kL (1)", "kL (2)"):
        return [
            TableItem(i+1),
        ] + [
            TableItem(change_unit(o[par.lower()], info.unit, info.ui_unit),
                      set_value=partial(self.set_optic_value, par),
                      delegate=delegates[float])
            for par in self.corrector.selected['optics']
            for info in [self.corrector.optic_params[i]]
        ]

    def get_record_row(self, i, r) -> ("Optic", "Monitor", "X", "Y"):
        return [
            TableItem(self.get_optic_name(r)),
            TableItem(r.monitor),
            TableItem(r.readout.posx, name='posx'),
            TableItem(r.readout.posy, name='posx'),
        ]

    def get_optic_name(self, record):
        for i, optic in enumerate(self.corrector.optics):
            if all(np.isclose(record.optics[k.lower()], v)
                    for k, v in optic.items()):
                return "Optic {}".format(i+1)
        return "custom optic"

    def set_optic_value(self, par, i, o, value):
        o[par.lower()] = value

    def closeEvent(self, event):
        self.bot.cancel()
        super().closeEvent(event)

    num_focus_levels = 6

    def init_controls(self):
        focus_choices = ["F{}".format(i+1)
                         for i in range(self.num_focus_levels)]
        self.read1stFocusComboBox.addItems(focus_choices)
        self.read2ndFocusComboBox.addItems(focus_choices)
        self.read1stFocusComboBox.setCurrentText("F1")
        self.read2ndFocusComboBox.setCurrentText("F4")

        corr = self.corrector
        self.opticsTable.set_viewmodel(self.get_optic_row, corr.optics)
        self.recordsTable.set_viewmodel(
            self.get_record_row, corr.records, unit=True)
        for tab in (self.opticsTable, self.recordsTable):
            tab.setSelectionBehavior(QAbstractItemView.SelectRows)
            tab.setSelectionMode(QAbstractItemView.ExtendedSelection)
        super().init_controls()

    def set_initial_values(self):
        self.bot = ProcBot(self, self.corrector)
        self.read_focus()
        self.modeXYButton.setChecked(True)
        self.update_status()

    def update_setup(self):
        self.opticsTable.model().titles[1:] = [
            "{}/{}".format(info.name, get_raw_label(info.ui_unit))
            for info in self.corrector.optic_params
        ]
        self._on_update_optics()
        super().update_setup()

    def _on_update_optics(self):
        self.opticComboBox.clear()
        self.opticComboBox.addItems([
            "Optic {}".format(i+1)
            for i in range(len(self.corrector.optics))
        ])
        self.setOpticButton.setEnabled(len(self.corrector.optics) > 0)

    def connect_signals(self):
        super().connect_signals()
        self.readFocusButton.clicked.connect(self.read_focus)
        self.recordButton.clicked.connect(self.corrector.add_record)
        self.setOpticButton.clicked.connect(self.set_optic)
        self.recordsTable.connectButtons(
            self.removeRecordsButton, self.clearRecordsButton)
        self.startProcedureButton.clicked.connect(self.start_bot)
        self.abortProcedureButton.clicked.connect(self.bot.cancel)
        # TODO: after add_record: disable "record" button until monitor
        # readouts updated (or maybe until "update" clicked as simpler
        # alternative)

    def set_optic(self):
        # TODO: disable "write" button until another optic has been selected
        # or the optic has changed in the DVM
        self.corrector.set_optic(self.opticComboBox.currentIndex())

    def read_focus(self):
        """Update focus level and automatically load QP values."""
        foci = [self.read1stFocusComboBox.currentIndex()+1,
                self.read2ndFocusComboBox.currentIndex()+1]

        corr = self.corrector
        ctrl = corr.control
        # TODO: this should be done with a more generic API
        # TODO: do this without beamoptikdll to decrease the waiting time
        dvm = ctrl.backend.beamoptikdll
        values, channels = dvm.GetMEFIValue()
        vacc = dvm.GetSelectedVAcc()
        try:
            optics = []
            for focus in foci:
                dvm.SelectMEFI(vacc, *channels._replace(focus=focus))
                optics.append({
                    par.lower(): ctrl.read_param(par)
                    for par in corr.selected['optics']
                })
            corr.optics[:] = optics
            self._on_update_optics()
        finally:
            dvm.SelectMEFI(vacc, *channels)

    def update_ui(self):
        super().update_ui()

        running = self.bot.running
        has_fit = bool(self.corrector.saved_optics())
        self.startProcedureButton.setEnabled(not running)
        self.abortProcedureButton.setEnabled(running)
        self.applyButton.setEnabled(not running and has_fit)

        self.read1stFocusComboBox.setEnabled(not running)
        self.read2ndFocusComboBox.setEnabled(not running)
        self.readFocusButton.setEnabled(not running)
        self.numIgnoredSpinBox.setEnabled(not running)
        self.numUsedSpinBox.setEnabled(not running)
        self.modeXButton.setEnabled(not running)
        self.modeYButton.setEnabled(not running)
        self.modeXYButton.setEnabled(not running)
        self.editConfigButton.setEnabled(not running)
        self.configComboBox.setEnabled(not running)
        self.manualTabWidget.setEnabled(not running)
        self.progressBar.setRange(0, self.bot.totalops)
        self.progressBar.setValue(self.bot.progress)

    def set_progress(self, progress):
        self.progressBar.setValue(progress)

    def start_bot(self):
        self.bot.start(
            self.numIgnoredSpinBox.value(),
            self.numUsedSpinBox.value())

    def log(self, text, *args, **kwargs):
        formatted = text.format(*args, **kwargs)
        logging.info(formatted)
        self.logEdit.appendPlainText(formatted)
