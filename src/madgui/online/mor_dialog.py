"""
Multi grid correction method.
"""

from collections import namedtuple
from functools import partial
import os
import time

import numpy as np

from madgui.qt import Qt, QtCore, QtGui, load_ui

from madgui.util.unit import change_unit, get_raw_label
from madgui.util.collections import List
from madgui.util.qt import bold, Queued
from madgui.util import yaml
from madgui.widget.dialog import Dialog
from madgui.widget.tableview import TableItem, delegates

from ._common import EditConfigDialog
from .procedure import Corrector, Target, ProcBot


ORM_Entry = namedtuple('ORM_Entry', ['monitor', 'knob', 'x', 'y'])


class CorrectorWidget(QtGui.QWidget):

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
        textcolor = QtGui.QColor(Qt.darkGray), QtGui.QColor(Qt.black)
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
        results = self.corrector.top_results.copy()
        if results[v.lower()] != value:
            results[v.lower()] = value
            self.corrector._push_history(results)
            self.update_ui()

    def __init__(self, session, active=None):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.orm = List()
        self.hist_stack = []
        self.hist_index = -1
        self.configs = session.model().data.get(self.data_key, {})
        self.active = active or next(iter(self.configs))
        self.corrector = Corrector(session)
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
        for tab in (self.tab_readouts, self.tab_targets, self.tab_corrections):
            tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
            tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        corr = self.corrector
        self.tab_orm.set_viewmodel(
            self.get_orm_row, self.orm)
        self.tab_readouts.set_viewmodel(
            self.get_readout_row, corr.readouts, unit=True)
        self.tab_corrections.set_viewmodel(
            self.get_steerer_row, corr.variables)
        self.tab_targets.set_viewmodel(
            self.get_cons_row, corr.targets, unit=True)
        self.view = self.corrector.session.window().open_graph('orbit')

    def set_orm(self, orm):
        self.hist_index += 1
        self.hist_stack[self.hist_index:] = [orm]
        self.orm[:] = orm
        self.update_ui()

    def prev_orm(self):
        if self.hist_index >= 1:
            self.hist_index -= 1
            self.orm[:] = self.hist_stack[self.hist_index]
            self.update_ui()

    def next_orm(self):
        if self.hist_index < len(self.hist_stack) - 1:
            self.hist_index += 1
            self.orm[:] = self.hist_stack[self.hist_index]
            self.update_ui()

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
        self.btn_compute.clicked.connect(self.compute_orm)
        self.btn_measure.clicked.connect(self.measure_orm)
        self.btn_load.clicked.connect(self.load_orm)
        self.btn_save.clicked.connect(self.save_orm)
        self.btn_fit.clicked.connect(self.update_fit)
        self.btn_apply.clicked.connect(self.on_execute_corrections)
        self.combo_config.activated.connect(self.on_change_config)
        self.btn_edit_conf.clicked.connect(self.edit_config)
        self.radio_mode_x.clicked.connect(partial(self.on_change_mode, 'x'))
        self.radio_mode_y.clicked.connect(partial(self.on_change_mode, 'y'))
        self.radio_mode_xy.clicked.connect(partial(self.on_change_mode, 'xy'))
        self.btn_prev.clicked.connect(self.prev_vals)
        self.btn_next.clicked.connect(self.next_vals)
        self.btn_prev_orm.clicked.connect(self.prev_orm)
        self.btn_next_orm.clicked.connect(self.next_orm)

    def update_status(self):
        self.corrector.update_vars()
        self.update_ui()

    def measure_orm(self):
        widget = MeasureWidget(self.corrector)
        dialog = Dialog(self.window())
        dialog.setWidget(widget)
        dialog.setWindowTitle("ORM scan")
        if dialog.exec_():
            self.set_orm(widget.final_orm)

    def compute_orm(self):
        # TODO: for generic knobs (anything other than hkicker/vkicker->kick)
        # we need to use numerical ORM
        corrector = self.corrector
        sectormap = corrector.compute_sectormap().reshape((
            len(corrector.monitors), 2, len(corrector.variables)))
        self.set_orm([
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
        self.set_orm([
            ORM_Entry(*entry)
            for entry in data
        ])

    def export_to(self, filename):
        data = yaml.safe_dump({
            'orm': [
                [entry.monitor, entry.knob, entry.x, entry.y]
                for entry in self.orm
            ]
        })
        with open(filename, 'wt') as f:
            f.write(data)

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

        self.corrector.match_results = results
        self.corrector._push_history(results)
        self.update_ui()

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
        self.btn_prev_orm.setEnabled(
            self.hist_index > 0)
        self.btn_next_orm.setEnabled(
            self.hist_index < len(self.hist_stack) - 1)
        self.draw_idle()

    def edit_config(self):
        dialog = EditConfigDialog(self.corrector.model, self.apply_config)
        dialog.exec_()

    def apply_config(self, text):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
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

    @Queued.method
    def draw(self):
        self.view.show_monitor_readouts(self.corrector.monitors[:])

    @property
    def frame(self):
        return self.corrector.session.window()


class MeasureWidget(QtGui.QWidget):

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
        return QtCore.QSize(600, 400)

    def init_controls(self):
        self.ctrl_correctors.set_viewmodel(
            self.get_corrector_row, unit=(None, 'kick'))

    def set_initial_values(self):
        self.d_phi = {}
        self.default_dphi = 2e-4
        self.ctrl_correctors.rows[:] = self.steerers
        self.ctrl_file.setText(
            "{date}_{time}_{sequence}_{monitor}"+self.extension)
        self.update_ui()

    def connect_signals(self):
        self.btn_start.clicked.connect(self.start_bot)
        self.btn_cancel.clicked.connect(self.cancel)

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
        self.btn_cancel.setEnabled(running)
        self.btn_start.setEnabled(not running and valid)
        self.num_shots_wait.setEnabled(not running)
        self.num_shots_use.setEnabled(not running)
        self.ctrl_correctors.setEnabled(not running)
        self.ctrl_progress.setEnabled(running)
        self.ctrl_progress.setRange(0, self.bot.totalops)
        self.ctrl_progress.setValue(self.bot.progress)

    def set_progress(self, progress):
        self.ctrl_progress.setValue(progress)

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
            self.num_shots_wait.value(),
            self.num_shots_use.value())

        now = time.localtime(time.time())
        fname = os.path.join(
            '.',
            self.ctrl_file.text().format(
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
        self.status_log.appendPlainText(formatted)
