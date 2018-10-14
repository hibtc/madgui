"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from functools import partial

import numpy as np
import yaml

from madgui.qt import QtCore, QtGui, load_ui

from madgui.util.unit import ui_units, change_unit, get_raw_label
from madgui.util.qt import bold
from madgui.widget.tableview import TableItem
from madgui.model.match import Constraint

from ._common import EditConfigDialog
from .procedure import Corrector


class CorrectorWidget(QtGui.QWidget):

    ui_file = 'mgm_dialog.ui'
    data_key = 'multi_grid'
    multi_step = False

    def get_readout_row(self, i, r) -> ("Monitor", "X", "Y"):
        return [
            TableItem(r.name),
            TableItem(r.posx, name='posx'),
            TableItem(r.posy, name='posy'),
        ]

    def get_cons_row(self, i, c) -> ("Element", "Param", "Value", "Unit"):
        return [
            TableItem(c.elem.node_name),
            TableItem(c.axis),
            TableItem(c.value, set_value=self.set_cons_value, name=c.axis),
            TableItem(ui_units.label(c.axis)),
        ]

    def get_steerer_row(self, i, v) -> ("Steerer", "Now", "To Be", "Unit"):
        initial = self.corrector.cur_results.get(v.lower())
        matched = self.corrector.top_results.get(v.lower())
        changed = matched is not None and not np.isclose(initial, matched)
        style = {
            # 'foreground': QtGui.QColor(Qt.red),
            'font': bold(),
        } if changed else {}
        info = self.corrector._knobs[v.lower()]
        return [
            TableItem(v),
            TableItem(change_unit(initial, info.unit, info.ui_unit)),
            TableItem(change_unit(matched, info.unit, info.ui_unit),
                      set_value=self.set_steerer_value, **style),
            TableItem(get_raw_label(info.ui_unit)),
        ]

    def set_cons_value(self, i, c, value):
        self.corrector.constraints[i] = Constraint(c.elem, c.pos, c.axis, value)

    def set_steerer_value(self, i, v, value):
        info = self.corrector._knobs[v.lower()]
        value = change_unit(value, info.ui_unit, info.unit)
        results = self.corrector.top_results.copy()
        if results[v.lower()] != value:
            results[v.lower()] = value
            self.corrector._push_history(results)
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
        self.frame.del_curve("monitors")

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.apply()
        self.update_status()

    def init_controls(self):
        for tab in (self.tab_readouts, self.tab_targets, self.tab_corrections):
            tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
            tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        corr = self.corrector
        self.tab_readouts.set_viewmodel(
            self.get_readout_row, corr.readouts, unit=True)
        self.tab_corrections.set_viewmodel(
            self.get_steerer_row, corr.variables)
        self.tab_targets.set_viewmodel(
            self.get_cons_row, corr.constraints)
        self.corrector.session.window().open_graph('orbit')

    def set_initial_values(self):
        self.btn_fit.setFocus()
        self.radio_mode_xy.setChecked(True)
        self.update_config()
        self.update_status()

    def update_config(self):
        self.combo_config.clear()
        self.combo_config.addItems(list(self.configs))
        self.combo_config.setCurrentText(self.active)

    def connect_signals(self):
        self.btn_fit.clicked.connect(self.update_fit)
        self.btn_apply.clicked.connect(self.on_execute_corrections)
        self.combo_config.activated.connect(self.on_change_config)
        self.btn_edit_conf.clicked.connect(self.edit_config)
        self.radio_mode_x.clicked.connect(partial(self.on_change_mode, 'x'))
        self.radio_mode_y.clicked.connect(partial(self.on_change_mode, 'y'))
        self.radio_mode_xy.clicked.connect(partial(self.on_change_mode, 'xy'))
        self.btn_prev.clicked.connect(self.prev_vals)
        self.btn_next.clicked.connect(self.next_vals)
        self.radio_meth_match.clicked.connect(partial(self.on_change_meth, 'match'))
        self.radio_meth_orm.clicked.connect(partial(self.on_change_meth, 'orm'))
        self.radio_meth_tm.clicked.connect(partial(self.on_change_meth, 'tm'))

    def on_change_meth(self, strategy):
        self.corrector.strategy = strategy
        if self.corrector.fit_results and self.corrector.variables:
            self.corrector.compute_steerer_corrections(
                self.corrector.fit_results)
            self.corrector.variables.touch()
            self.update_ui()
            self.draw()

    def update_status(self):
        self.corrector.update_vars()
        self.corrector.update_readouts()
        self.corrector.update_records()
        self.update_setup()
        self.update_ui()
        QtCore.QTimer.singleShot(0, self.draw)

    def update_setup(self):
        pass

    def update_fit(self):
        """Calculate initial positions / corrections."""
        self.corrector.update()
        if self.corrector.fit_results and self.corrector.variables:
            self.corrector.compute_steerer_corrections(
                self.corrector.fit_results)
        self.update_ui()
        self.draw()

    def on_change_config(self, index):
        name = self.combo_config.itemText(index)
        self.corrector.setup(self.configs[name], self.corrector.mode)
        self.update_status()

    def on_change_mode(self, dirs):
        self.corrector.setup(self.configs[self.active], dirs)
        self.update_status()

        # TODO: make 'optimal'-column in tab_corrections editable and update
        #       self.btn_apply.setEnabled according to its values

    def prev_vals(self):
        self.corrector.history_move(-1)
        self.update_ui()

    def next_vals(self):
        self.corrector.history_move(+1)
        self.update_ui()

    def update_ui(self):
        hist_idx = self.corrector.hist_idx
        hist_len = len(self.corrector.hist_stack)
        self.btn_prev.setEnabled(hist_idx > 0)
        self.btn_next.setEnabled(hist_idx+1 < hist_len)
        self.btn_apply.setEnabled(
            self.corrector.cur_results != self.corrector.top_results)
        self.corrector.variables.touch()

        # TODO: do this only after updating readouts…
        QtCore.QTimer.singleShot(0, self.draw)

    def edit_config(self):
        dialog = EditConfigDialog(self.corrector.model, self.apply_config)
        dialog.exec_()

    def apply_config(self, text):
        try:
            data = yaml.safe_load(text)
        except yaml.error.YAMLError:
            QtGui.QMessageBox.critical(
                self,
                'Syntax error in YAML document',
                'There is a syntax error in the YAML document, please edit.')
            return False

        configs = data.get(self.data_key)
        if not configs:
            QtGui.QMessageBox.critical(
                self,
                'No config defined',
                'No configuration for this method defined.')
            return False

        model = self.corrector.model
        with open(model.filename, 'w') as f:
            f.write(text)

        self.configs = configs
        model.data[self.data_key] = configs
        conf = self.active
        if conf not in configs:
            conf = next(iter(configs))

        self.corrector.setup(conf)
        self.update_config()
        self.update_status()

        return True

    def draw(self):
        corr = self.corrector
        elements = corr.model.elements
        monitor_data = [
            {'s': elements[r.name].position,
             'x': r.posx + dx,
             'y': r.posy + dy}
            for r in self.corrector.readouts
            for dx, dy in [self.corrector._offsets.get(r.name.lower(), (0, 0))]
        ]
        curve_data = {
            name: np.array([d[name] for d in monitor_data])
            for name in ['s', 'x', 'y']
        }
        style = self.frame.config['line_view']['monitor_style']
        self.frame.add_curve("monitors", curve_data, style)

    @property
    def frame(self):
        return self.corrector.session.window()
