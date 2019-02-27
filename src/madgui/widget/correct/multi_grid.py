"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from functools import partial

import yaml
from PyQt5.QtWidgets import QMessageBox, QWidget

from madgui.util.qt import Queued, load_ui
from madgui.widget.edit import TextEditDialog

from madgui.online.procedure import Corrector


class CorrectorWidget(QWidget):

    ui_file = 'multi_grid.ui'
    data_key = 'multi_grid'
    multi_step = False

    def __init__(self, session, active=None):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.configs = session.model().data.get(self.data_key, {})
        self.active = active or next(iter(self.configs))
        self.corrector = Corrector(session, direct=not self.multi_step)
        self.corrector.start()
        self.corrector.setup(self.configs[self.active])
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
        self.monitorTable.set_corrector(self.corrector)
        self.targetsTable.set_corrector(self.corrector)
        self.resultsTable.set_corrector(self.corrector)
        self.view = self.corrector.session.window().open_graph('orbit')

    def set_initial_values(self):
        self.fitButton.setFocus()
        self.modeXYButton.setChecked(True)
        self.update_config()
        self.update_status()

    def update_config(self):
        self.configComboBox.clear()
        self.configComboBox.addItems(list(self.configs))
        self.configComboBox.setCurrentText(self.active)

    def connect_signals(self):
        self.corrector.saved_optics.changed.connect(self.update_ui)
        self.fitButton.clicked.connect(self.update_fit)
        self.applyButton.clicked.connect(self.on_execute_corrections)
        self.configComboBox.activated.connect(self.on_change_config)
        self.editConfigButton.clicked.connect(self.edit_config)
        self.modeXButton.clicked.connect(partial(self.on_change_mode, 'x'))
        self.modeYButton.clicked.connect(partial(self.on_change_mode, 'y'))
        self.modeXYButton.clicked.connect(partial(self.on_change_mode, 'xy'))
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

    def on_change_config(self, index):
        name = self.configComboBox.itemText(index)
        self.corrector.setup(self.configs[name], self.corrector.mode)
        self.update_status()

    def on_change_mode(self, dirs):
        self.corrector.setup(self.configs[self.active], dirs)
        self.update_status()

    def update_ui(self):
        saved_optics = self.corrector.saved_optics
        self.applyButton.setEnabled(
            self.corrector.online_optic != saved_optics())
        if saved_optics() is not None:
            self.corrector.variables.touch()
        self.draw_idle()

    def edit_config(self):
        model = self.corrector.model
        with open(model.filename) as f:
            text = f.read()
        dialog = TextEditDialog(text, self.apply_config)
        dialog.setWindowTitle(model.filename)
        dialog.exec_()

    def apply_config(self, text):
        try:
            data = yaml.safe_load(text)
        except yaml.error.YAMLError:
            QMessageBox.critical(
                self,
                'Syntax error in YAML document',
                'There is a syntax error in the YAML document, please edit.')
            return False

        configs = data.get(self.data_key)
        if not configs:
            QMessageBox.critical(
                self,
                'No config defined',
                'No configuration for this method defined.')
            return False

        model = self.corrector.model
        with open(model.filename, 'w') as f:
            f.write(text)

        self.configs = configs
        model.data[self.data_key] = configs
        conf = configs.get(self.active, next(iter(configs)))

        self.corrector.setup(conf)
        self.update_config()
        self.update_status()

        return True

    @Queued.method
    def draw_idle(self):
        self.view.show_monitor_readouts(
            self.corrector.monitors[:])

    @property
    def frame(self):
        return self.corrector.session.window()
