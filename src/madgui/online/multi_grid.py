"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from functools import partial

import numpy as np
import yaml
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QAbstractItemView, QMessageBox, QWidget

from madgui.util.unit import change_unit, get_raw_label
from madgui.util.qt import bold, Queued, load_ui
from madgui.widget.tableview import TableItem, delegates
from madgui.widget.edit import TextEditDialog

from .procedure import Corrector, Target


class CorrectorWidget(QWidget):

    ui_file = 'multi_grid.ui'
    data_key = 'multi_grid'
    multi_step = False

    def get_readout_row(self, i, r) -> ("Monitor", "X", "Y"):
        return [
            TableItem(r.name),
            TableItem(r.posx, name='posx'),
            TableItem(r.posy, name='posy'),
        ]

    def get_cons_row(self, i, t) -> ("Target", "X", "Y"):
        mode = self.corrector.mode
        active_x = 'x' in mode
        active_y = 'y' in mode
        textcolor = QColor(Qt.darkGray), QColor(Qt.black)
        return [
            TableItem(t.elem),
            TableItem(t.x, name='x', set_value=self.set_x_value,
                      editable=active_x, foreground=textcolor[active_x],
                      delegate=delegates[float]),
            TableItem(t.y, name='y', set_value=self.set_y_value,
                      editable=active_y, foreground=textcolor[active_y],
                      delegate=delegates[float]),
        ]

    def get_steerer_row(self, i, v) -> ("Steerer", "Now", "To Be", "Unit"):
        initial = self.corrector.online_optic.get(v.lower())
        matched = self.corrector.saved_optics().get(v.lower())
        changed = matched is not None and not np.isclose(initial, matched)
        style = {
            # 'foreground': QColor(Qt.red),
            'font': bold(),
        } if changed else {}
        info = self.corrector._knobs[v.lower()]
        return [
            TableItem(v),
            TableItem(change_unit(initial, info.unit, info.ui_unit)),
            TableItem(change_unit(matched, info.unit, info.ui_unit),
                      set_value=self.set_steerer_value,
                      delegate=delegates[float], **style),
            TableItem(get_raw_label(info.ui_unit)),
        ]

    def set_x_value(self, i, t, value):
        self.corrector.targets[i] = Target(t.elem, value, t.y)

    def set_y_value(self, i, t, value):
        self.corrector.targets[i] = Target(t.elem, t.x, value)

    def set_steerer_value(self, i, v, value):
        info = self.corrector._knobs[v.lower()]
        value = change_unit(value, info.ui_unit, info.unit)
        results = self.corrector.saved_optics().copy()
        if results[v.lower()] != value:
            results[v.lower()] = value
            self.corrector.saved_optics.push(results)
            self.update_ui()

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
        for tab in (self.monitorTable, self.targetsTable, self.resultsTable):
            tab.setSelectionBehavior(QAbstractItemView.SelectRows)
            tab.setSelectionMode(QAbstractItemView.ExtendedSelection)
        corr = self.corrector
        self.monitorTable.set_viewmodel(
            self.get_readout_row, corr.readouts, unit=True)
        self.resultsTable.set_viewmodel(
            self.get_steerer_row, corr.variables)
        self.targetsTable.set_viewmodel(
            self.get_cons_row, corr.targets, unit=True)
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
        self.fitButton.clicked.connect(self.update_fit)
        self.applyButton.clicked.connect(self.on_execute_corrections)
        self.configComboBox.activated.connect(self.on_change_config)
        self.editConfigButton.clicked.connect(self.edit_config)
        self.modeXButton.clicked.connect(partial(self.on_change_mode, 'x'))
        self.modeYButton.clicked.connect(partial(self.on_change_mode, 'y'))
        self.modeXYButton.clicked.connect(partial(self.on_change_mode, 'xy'))
        self.prevButton.clicked.connect(self.prev_vals)
        self.nextButton.clicked.connect(self.next_vals)
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

        # TODO: make 'optimal'-column in resultsTable editable and update
        #       self.applyButton.setEnabled according to its values

    def prev_vals(self):
        self.corrector.saved_optics.undo()
        self.update_ui()

    def next_vals(self):
        self.corrector.saved_optics.redo()
        self.update_ui()

    def update_ui(self):
        saved_optics = self.corrector.saved_optics
        self.prevButton.setEnabled(saved_optics.can_undo())
        self.nextButton.setEnabled(saved_optics.can_redo())
        self.applyButton.setEnabled(
            self.corrector.online_optic != saved_optics())
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
