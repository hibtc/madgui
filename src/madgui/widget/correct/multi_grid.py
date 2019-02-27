"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from functools import partial

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
        self.methodMatchButton.clicked.connect(
            partial(self.on_change_meth, 'match'))
        self.methodORMButton.clicked.connect(
            partial(self.on_change_meth, 'orm'))
        self.methodSectormapButton.clicked.connect(
            partial(self.on_change_meth, 'tm'))
        self.backtrackCheckBox.clicked.connect(self.on_check_backtracking)

    def on_change_meth(self, strategy):
        self.corrector.strategy = strategy
        self.update_fit()

    def on_check_backtracking(self, checked):
        self.corrector.use_backtracking = checked
        self.update_fit()

    def update_status(self):
        self.corrector.update_vars()
        self.corrector.update_records()
        self.update_setup()
        self.update_ui()

    def update_setup(self):
        if self.corrector.knows_targets_readouts():
            self.backtrackCheckBox.setEnabled(True)
        else:
            self.backtrackCheckBox.setEnabled(False)
            self.backtrackCheckBox.setChecked(True)

    def update_fit(self):
        """Calculate initial positions / corrections."""
        self.corrector.update_vars()
        self.corrector.update_records()
        self.corrector.update_fit()
        self.update_ui()

    def update_ui(self):
        saved_optics = self.corrector.saved_optics
        self.applyButton.setEnabled(
            self.corrector.online_optic != saved_optics())
        if saved_optics() is not None:
            self.corrector.variables.touch()
        self.draw_idle()

    @Queued.method
    def draw_idle(self):
        self.view.show_monitor_readouts(
            self.corrector.monitors[:])

    @property
    def frame(self):
        return self.corrector.session.window()
