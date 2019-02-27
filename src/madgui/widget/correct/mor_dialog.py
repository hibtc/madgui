"""
Multi grid correction method.
"""

import numpy as np
from PyQt5.QtWidgets import QWidget

from madgui.util.qt import Queued, load_ui

from .procedure import Corrector


class CorrectorWidget(QWidget):

    ui_file = 'mor_dialog.ui'
    data_key = 'multi_grid'     # can reuse the multi grid configuration

    def __init__(self, session):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
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
        self.responseTable.set_corrector(self.corrector)
        self.monitorTable.set_corrector(self.corrector)
        self.targetsTable.set_corrector(self.corrector)
        self.resultsTable.set_corrector(self.corrector)
        self.view = self.corrector.session.window().open_graph('orbit')

    def set_initial_values(self):
        self.fitButton.setFocus()
        self.update_status()

    def connect_signals(self):
        self.corrector.setup_changed.connect(self.update_status)
        self.corrector.saved_optics.changed.connect(self.update_ui)
        self.fitButton.clicked.connect(self.update_fit)
        self.applyButton.clicked.connect(self.on_execute_corrections)
        self.prevButton.setDefaultAction(
            self.corrector.saved_optics.create_undo_action(self))
        self.nextButton.setDefaultAction(
            self.corrector.saved_optics.create_redo_action(self))

    def update_status(self):
        self.corrector.update_vars()
        self.update_ui()

    def update_fit(self):
        """Calculate initial positions / corrections."""
        indexed = {}
        for entry in self.responseTable.orm:
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

    @Queued.method
    def update_ui(self):
        saved_optics = self.corrector.saved_optics
        self.applyButton.setEnabled(
            self.corrector.online_optic != saved_optics())
        if saved_optics() is not None:
            self.corrector.variables.touch()
        self.view.show_monitor_readouts(self.corrector.monitors[:])
