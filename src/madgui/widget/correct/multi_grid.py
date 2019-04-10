"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from PyQt5.QtWidgets import QWidget

from madgui.util.qt import Queued, load_ui

from madgui.online.procedure import Corrector


class CorrectorWidget(QWidget):

    ui_file = 'multi_grid.ui'
    data_key = 'multi_grid'
    multi_step = False

    def __init__(self, session):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.corrector = Corrector(session, direct=not self.multi_step)
        self.corrector.start()
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def closeEvent(self, event):
        self.corrector.stop()
        self.view.hide_monitor_readouts()
        super().closeEvent(event)

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.apply()
        self.update_status()

    def init_controls(self):
        self.configSelect.set_corrector(self.corrector, self.data_key)
        self.fitSettingsWidget.set_corrector(self.corrector)
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
        self.corrector.strategy.changed.connect(self.update_fit)
        self.corrector.use_backtracking.changed.connect(self.update_fit)
        self.fitButton.clicked.connect(self.update_fit)
        self.applyButton.clicked.connect(self.on_execute_corrections)
        self.prevButton.setDefaultAction(
            self.corrector.saved_optics.create_undo_action(self))
        self.nextButton.setDefaultAction(
            self.corrector.saved_optics.create_redo_action(self))

    def update_status(self):
        self.corrector.update_vars()
        self.corrector.update_records()
        self.update_ui()

    def update_fit(self, *_):
        """Calculate initial positions / corrections."""
        self.corrector.update_vars()
        self.corrector.update_records()
        self.corrector.update_fit()
        self.update_ui()

    @Queued.method
    def update_ui(self):
        saved_optics = self.corrector.saved_optics
        self.applyButton.setEnabled(
            self.corrector.online_optic != saved_optics())
        if saved_optics() is not None:
            self.corrector.variables.touch()
        self.view.show_monitor_readouts(self.corrector.monitors[:])
