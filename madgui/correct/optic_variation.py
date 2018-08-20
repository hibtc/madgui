"""
Utilities for the optic variation method (Optikvarianzmethode) for beam
alignment.
"""

from functools import partial

import numpy as np

from madgui.qt import QtCore, QtGui, load_ui
from madgui.core.unit import ui_units, change_unit, get_raw_label
from madgui.widget.tableview import TableItem
from madgui.util import yaml
from madgui.util.qt import bold

from .multi_grid import Corrector as _Corrector
from ._common import EditConfigDialog
from .match import Constraint



__all__ = [
    'Corrector',
    'CorrectorWidget',
]


class Corrector(_Corrector):
    direct = False



class CorrectorWidget(QtGui.QWidget):

    initial_particle_orbit = None

    ui_file = 'ovm_dialog.ui'

    def get_optic_row(self, i, o) -> ("#", "kL (1)", "kL (2)"):
        return [
            TableItem(i+1),
        ] + [
            TableItem(change_unit(o[par.lower()], info.unit, info.ui_unit),
                      set_value=partial(self.set_optic_value, par))
            for par in self.corrector.selected['optics']
            for info in [self.corrector.optic_params[i]]
        ]

    def get_readout_row(self, i, r) -> ("Monitor", "X", "Y"):
        return [
            TableItem(r.name),
            TableItem(r.posx, name='posx'),
            TableItem(r.posy, name='posy'),
        ]

    def get_record_row(self, i, r) -> ("Optic", "Monitor", "X", "Y"):
        return [
            TableItem(self.get_optic_name(r)),
            TableItem(r.monitor),
            TableItem(r.readout.posx, name='posx'),
            TableItem(r.readout.posy, name='posx'),
        ]

    def get_cons_row(self, i, c) -> ("Element", "Param", "Value", "Unit"):
        return [
            TableItem(c.elem.node_name),
            TableItem(c.axis),
            TableItem(c.value, set_value=self.set_cons_value, name=c.axis),
            TableItem(ui_units.label(c.axis)),
        ]

    def get_optic_name(self, record):
        for i, optic in enumerate(self.corrector.optics):
            if all(np.isclose(record.optics[k.lower()], v)
                    for k, v in optic.items()):
                return "Optic {}".format(i+1)
        return "custom optic"

    def set_optic_value(self, par, i, o, value):
        o[par.lower()] = value

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

    def get_steerer_row(self, i, v) -> ("Steerer", "Now", "To Be", "Unit"):
        initial = self.corrector.cur_results.get(v.lower())
        matched = self.corrector.top_results.get(v.lower())
        changed = matched is not None and not np.isclose(initial, matched)
        style = {
            #'foreground': QtGui.QColor(Qt.red),
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

    def __init__(self, corrector):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.corrector = corrector
        self.corrector.start()
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def closeEvent(self, event):
        self.bot.cancel()
        self.corrector.stop()
        self.frame.del_curve("monitors")

    num_focus_levels = 6

    def init_controls(self):
        focus_choices = ["F{}".format(i+1)
                         for i in range(self.num_focus_levels)]
        self.read_focus1.addItems(focus_choices)
        self.read_focus2.addItems(focus_choices)
        self.read_focus1.setCurrentText("F1")
        self.read_focus2.setCurrentText("F4")

        corr = self.corrector

        self.tab_optics.set_viewmodel(self.get_optic_row, corr.optics)
        self.tab_targets.set_viewmodel(self.get_cons_row, corr.constraints)
        self.tab_readouts.set_viewmodel(self.get_readout_row, corr.readouts, unit=True)
        self.tab_records.set_viewmodel(self.get_record_row, corr.records, unit=True)
        self.tab_corrections.set_viewmodel(self.get_steerer_row, corr.variables)

        self.combo_config.addItems(list(self.corrector.configs))
        self.combo_config.setCurrentText(self.corrector.active)

    def set_initial_values(self):
        self.bot = ProcBot(self, self.corrector)
        self.update_setup()
        self.update_ui()

    def update_setup(self):
        self.tab_optics.model().titles[1:] = [
            "{}/{}".format(info.name, get_raw_label(info.ui_unit))
            for info in self.corrector.optic_params
        ]
        self._on_update_optics()
        self.read_focus()
        self.corrector.update_readouts()

    def _on_update_optics(self):
        self.combo_set_optic.clear()
        self.combo_set_optic.addItems([
            "Optic {}".format(i+1)
            for i in range(len(self.corrector.optics))
        ])
        self.btn_set_optic.setEnabled(len(self.corrector.optics) > 0)

    def connect_signals(self):
        self.btn_edit_conf.clicked.connect(self.edit_config)
        self.btn_read_focus.clicked.connect(self.read_focus)
        self.combo_config.currentIndexChanged.connect(self.on_change_config)
        self.radio_mode_x.clicked.connect(partial(self.on_change_mode, 'x'))
        self.radio_mode_y.clicked.connect(partial(self.on_change_mode, 'y'))
        self.radio_mode_xy.clicked.connect(partial(self.on_change_mode, 'xy'))
        self.btn_update.clicked.connect(self.corrector.update_readouts)
        self.btn_record.clicked.connect(self.add_record)
        self.btn_set_optic.clicked.connect(self.set_optic)
        self.tab_records.connectButtons(self.btn_rec_remove, self.btn_rec_clear)
        self.btn_fit.clicked.connect(self.update_fit)
        self.btn_apply.clicked.connect(self.on_execute_corrections)
        self.btn_proc_start.clicked.connect(self.bot.start)
        self.btn_proc_abort.clicked.connect(self.bot.cancel)
        self.btn_prev.clicked.connect(self.prev_vals)
        self.btn_next.clicked.connect(self.next_vals)

    def on_change_config(self, index):
        name = self.combo_config.itemText(index)
        self.corrector.setup(name, self.corrector.mode)
        self.update_status()

    def on_change_mode(self, dirs):
        self.corrector.setup(self.corrector.active, dirs)
        self.corrector.update()

    def add_record(self):
        # TODO: disable "record" button until monitor readouts updated
        # (or maybe until "update" clicked as simpler alternative)
        self.corrector.update_vars()
        self.corrector.update_readouts()
        self.corrector.records.extend(
            self.corrector.current_orbit_records())

    def set_optic(self):
        # TODO: disable "write" button until another optic has been selected
        # or the optic has changed in the DVM
        self.corrector.set_optic(self.combo_set_optic.currentIndex())

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.apply()

    def update_fit(self):
        """Calculate initial positions / corrections."""
        self.corrector.update()
        if self.corrector.fit_results and self.corrector.variables:
            self.corrector.compute_steerer_corrections(self.corrector.fit_results)
        self.update_ui()

    def read_focus(self):
        """Update focus level and automatically load QP values."""
        foci = [self.read_focus1.currentIndex()+1,
                self.read_focus2.currentIndex()+1]

        corr = self.corrector
        ctrl = corr.control
        # TODO: this should be done with a more generic API
        # TODO: do this without beamoptikdll to decrease the waiting time
        dvm = ctrl._plugin._dvm
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

        configs = data.get('optic_variation')
        if not configs:
            QtGui.QMessageBox.critical(
                self,
                'No config defined',
                'No optic variation configuration defined.')
            return False

        model = self.corrector.model
        with open(model.filename, 'w') as f:
            f.write(text)

        self.corrector.configs = configs
        model.data['optic_variation'] = configs

        conf = self.corrector.active if self.corrector.active in configs else next(iter(configs))
        self.corrector.setup(conf)
        self.corrector.update()

        self.update_setup()

        return True

    def prev_vals(self):
        self.corrector.history_move(-1)
        self.update_ui()

    def next_vals(self):
        self.corrector.history_move(+1)
        self.update_ui()

    def update_ui(self):
        running = self.bot.running
        has_fit = self.corrector.fit_results is not None
        self.btn_proc_start.setEnabled(not running)
        self.btn_proc_abort.setEnabled(running)
        self.btn_apply.setEnabled(not running and has_fit)

        self.read_focus1.setEnabled(not running)
        self.read_focus2.setEnabled(not running)
        self.btn_read_focus.setEnabled(not running)
        self.num_shots_wait.setEnabled(not running)
        self.num_shots_use.setEnabled(not running)
        self.radio_mode_x.setEnabled(not running)
        self.radio_mode_y.setEnabled(not running)
        self.radio_mode_xy.setEnabled(not running)
        self.btn_edit_conf.setEnabled(not running)
        self.combo_config.setEnabled(not running)
        self.tab_manual.setEnabled(not running)
        self.ctrl_progress.setRange(0, self.bot.totalops)
        self.ctrl_progress.setValue(self.bot.progress)

        hist_idx = self.corrector.hist_idx
        hist_len = len(self.corrector.hist_stack)
        self.btn_prev.setEnabled(hist_idx > 0)
        self.btn_next.setEnabled(hist_idx+1 < hist_len)
        self.btn_apply.setEnabled(
            self.corrector.cur_results != self.corrector.top_results)
        self.corrector.variables.touch()
        # TODO: do this only after updating readouts…
        QtCore.QTimer.singleShot(0, self.draw)

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
        return self.window().parent()


class ProcBot:

    def __init__(self, widget, corrector):
        self.widget = widget
        self.corrector = corrector
        self.running = False
        self.model = corrector.model
        self.control = corrector.control
        self.totalops = 100
        self.progress = 0

    def start(self):
        num_ignore = self.widget.num_shots_wait.value()
        num_average = self.widget.num_shots_use.value()
        self.corrector.records.clear()
        self.numsteps = len(self.corrector.optics)
        self.numshots = num_average + num_ignore + 1
        self.num_ignore = num_ignore
        self.totalops = self.numsteps * self.numshots
        self.progress = 0
        self.running = True
        self.widget.update_ui()
        self.log("Started")
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(300)

    def finish(self):
        self.stop()
        self.widget.update_fit()
        self.log("Finished\n")

    def cancel(self):
        if self.running:
            self.stop()
            self.reset()
            self.log("Cancelled by user.\n")

    def stop(self):
        if self.running:
            self.corrector.set_optic(0)
            self.running = False
            self.timer.stop()
            self.widget.update_ui()

    def reset(self):
        self.corrector.fit_results = None
        self.widget.update_ui()

    def poll(self):
        if not self.running:
            return

        step = self.progress // self.numshots
        shot = self.progress % self.numshots

        if shot == 0:
            self.log("optic {}".format(step))
            self.corrector.set_optic(step)

            self.last_readouts = self.read_monitors()
            self.progress += 1
            self.widget.ctrl_progress.setValue(self.progress)
            return

        readouts = self.read_monitors()
        if readouts == self.last_readouts:
            return
        self.last_readouts = readouts

        self.progress += 1
        self.widget.ctrl_progress.setValue(self.progress)

        if shot <= self.num_ignore:
            self.log('  -> shot {} (ignored)', shot)
            return

        self.log('  -> shot {}', shot)
        self.widget.add_record()

        if self.progress == self.totalops:
            self.finish()

    def read_monitors(self):
        return {mon: self.control.read_monitor(mon)
                for mon in self.corrector.monitors}

    def log(self, text, *args, **kwargs):
        self.widget.status_log.appendPlainText(
            text.format(*args, **kwargs))
