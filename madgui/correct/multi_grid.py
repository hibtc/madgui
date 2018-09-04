"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from functools import partial
from itertools import accumulate

import numpy as np
import yaml

from madgui.qt import QtCore, QtGui, load_ui

from madgui.core.unit import ui_units, change_unit, get_raw_label
from madgui.util.collections import List
from madgui.util.qt import bold
from madgui.widget.tableview import TableItem

from .orbit import fit_particle_orbit
from .match import Matcher, Constraint
from ._common import EditConfigDialog


class OrbitRecord:

    def __init__(self, monitor, readout, optics, tm):
        self.monitor = monitor
        self.readout = readout
        self.optics = optics
        self.tm = tm


class Corrector(Matcher):

    """
    Single target orbit correction via optic variation.
    """

    mode = 'xy'
    direct = True

    def __init__(self, control, configs):
        super().__init__(control.model(), None)
        self.fit_results = None
        self.active = None
        self.control = control
        self.configs = configs
        self._knobs = {knob.name.lower(): knob for knob in control.get_knobs()}
        # save elements
        self.monitors = List()
        self.readouts = List()
        self.records = List()
        self.fit_range = None
        self._offsets = control._frame.config['online_control']['offsets']
        self.optics = List()
        QtCore.QTimer.singleShot(0, partial(control._frame.open_graph, 'orbit'))

    def setup(self, name, dirs=None, force=False):
        if not name or (name == self.active and not force):
            return

        dirs = dirs or self.mode

        self._clr_history()

        selected = self.selected = self.configs[name]
        monitors = selected['monitors']
        steerers = sum([selected['steerers'][d] for d in dirs], [])
        targets  = selected['targets']

        params = [k.lower() for k in selected.get('optics', ())]
        self.optic_params = [self._knobs[k] for k in params]
        self.quads = params and [
            elem.name
            for elem in self.model.elements
            for knobs in [self.model.get_elem_knobs(elem)]
            if any(k.lower() in params for k in knobs)
        ]

        self.method = selected.get('method', ('jacobian', {}))
        self.active = name
        self.mode = dirs
        self.match_names = [s for s in steerers if isinstance(s, str)]
        self.assign = {k: v for s in steerers if isinstance(s, dict)
                       for k, v in s.items()}

        elements = self.model.elements
        self.targets = sorted(targets, key=elements.index)
        self.monitors[:] = sorted(monitors, key=elements.index)
        self._readouts = self.control.monitors.sublist(
            map(str.lower, self.monitors))
        self._readouts.as_list(self.readouts)
        fit_elements = list(self.targets) + list(self.monitors) + list(self.quads)
        self.fit_range = (min(fit_elements, key=elements.index),
                          max(fit_elements, key=elements.index))
        self.constraints[:] = sorted([
            Constraint(elements[target], elements[target].position, key, float(value))
            for target, values in targets.items()
            for key, value in values.items()
            if key[-1] in dirs
        ], key=lambda c: c.pos)
        self.variables[:] = [
            knob
            for knob in self.match_names + list(self.assign)
            if knob.lower() in self._knobs
        ]

    #def _involved_elements(self):      # with steerers!

    def _read_vars(self):
        model = self.model
        return {
            knob.lower(): model.read_param(knob)
            for knob in self.match_names + list(self.assign)
            if knob.lower() in self._knobs
        }

    def _clr_history(self):
        self.hist_stack = []
        self.hist_idx = -1
        self.cur_results = {}
        self.top_results = {}

    def _push_history(self, results=None):
        results = self._read_vars() if results is None else results
        if results != self.top_results:
            self.top_results = results
            self.hist_idx += 1
            self.hist_stack[self.hist_idx:] = [results]
        return results

    def history_move(self, move):
        self.hist_idx += move
        self.top_results = self.hist_stack[self.hist_idx]

    def update_vars(self):
        self.control.read_all()
        self.cur_results = self._push_history()

    def update(self):
        self.update_vars()
        self.update_readouts()
        self.update_records()
        self.update_fit()

    def update_readouts(self):
        self._readouts.invalidate()

    def update_records(self):
        if self.direct:
            self.records[:] = self.current_orbit_records()

    def update_fit(self):
        self.fit_results = None
        if len(self.records) < 2:
            return
        init_orbit, chi_squared, singular = \
            self.fit_particle_orbit(self.records)
        if singular:
            return
        self.fit_results = init_orbit
        self.model.update_twiss_args(init_orbit)

    def apply(self):
        self.model.write_params(self.top_results.items())
        self.control.write_params(self.top_results.items())
        super().apply()

    def set_optic(self, i):
        # only for optic variation method
        optic = self.optics[i]
        self.control.write_params(optic.items())
        self.model.write_params(optic.items())

    # computations

    def fit_particle_orbit(self, records):
        readouts = [r.readout for r in records]
        secmaps = [r.tm for r in records]
        return fit_particle_orbit(
            self.model, self._offsets, readouts, secmaps, self.fit_range[0])[0]

    def current_orbit_records(self):
        model = self.model
        start = self.fit_range[0]
        secmaps = model.get_transfer_maps([start] + list(self.monitors))
        secmaps = list(accumulate(secmaps, lambda a, b: np.dot(b, a)))
        optics = {k: model.globals[k] for k in self._knobs}
        return [
            OrbitRecord(monitor, readout, optics, secmap)
            for monitor, readout, secmap in zip(
                    self.monitors, self.readouts, secmaps)
        ]

    def compute_steerer_corrections(self, init_orbit):

        """
        Compute corrections for the x_steerers, y_steerers.

        :param dict init_orbit: initial conditions as returned by the fit
        """

        def offset(c):
            dx, dy = self._offsets.get(c.elem.name.lower(), (0, 0))
            if c.axis in ('x', 'posx'): return dx
            if c.axis in ('y', 'posy'): return dy
            return 0
        constraints = [
            (c.elem, None, c.axis, c.value+offset(c))
            for c in self.constraints
        ]
        model = self.model
        with model.undo_stack.rollback("Orbit correction", transient=True):
            model.update_globals(self.assign)
            model.update_twiss_args(init_orbit)
            model.match(
                vary=self.match_names,
                limits=self.selected.get('limits'),
                method=self.method,
                weight={'x': 1e3, 'y':1e3, 'px':1e2, 'py':1e2},
                constraints=constraints)
            self.match_results = self._push_history()
            return self.match_results


class CorrectorWidget(QtGui.QWidget):

    ui_file = 'mgm_dialog.ui'

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

    def __init__(self, corrector):
        super().__init__()
        load_ui(self, __package__, self.ui_file)
        self.corrector = corrector
        self.corrector.start()
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
        self.tab_readouts.set_viewmodel(self.get_readout_row, corr.readouts, unit=True)
        self.tab_corrections.set_viewmodel(self.get_steerer_row, corr.variables)
        self.tab_targets.set_viewmodel(self.get_cons_row, corr.constraints)

    def set_initial_values(self):
        self.btn_fit.setFocus()
        self.radio_mode_xy.setChecked(True)
        self.update_config()
        self.update_status()

    def update_config(self):
        self.combo_config.clear()
        self.combo_config.addItems(list(self.corrector.configs))
        self.combo_config.setCurrentText(self.corrector.active)

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
            self.corrector.compute_steerer_corrections(self.corrector.fit_results)
        self.update_ui()
        self.draw()
        #self.tab_corrections.resizeColumnToContents(0)

    def on_change_config(self, index):
        name = self.combo_config.itemText(index)
        self.corrector.setup(name, self.corrector.mode)
        self.update_status()

    def on_change_mode(self, dirs):
        self.corrector.setup(self.corrector.active, dirs)
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

    data_key = 'multi_grid'

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

        self.corrector.configs = configs
        model.data[self.data_key] = configs
        conf = self.corrector.active
        if conf not in configs:
            conf = next(iter(configs))

        self.corrector.setup(conf, force=True)
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
        return self.window().parent()
