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
from madgui.util.qt import fit_button, bold
from madgui.widget.tableview import TableItem

from .orbit import fit_particle_orbit, MonitorReadout
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

    def __init__(self, control, configs):
        super().__init__(control.model(), None)
        self.fit_results = None
        self.control = control
        self.configs = configs
        self._knobs = {knob.name.lower(): knob for knob in control.get_knobs()}
        # save elements
        self.design_values = {}
        self.monitors = List()
        self.readouts = List()
        self.records = List()
        self.fit_range = None
        self._offsets = control._frame.config['online_control']['offsets']
        QtCore.QTimer.singleShot(0, partial(control._frame.open_graph, 'orbit'))

    def setup(self, name, dirs=None):
        dirs = dirs or self.mode

        selected = self.selected = self.configs[name]
        monitors = selected['monitors']
        steerers = sum([selected['steerers'][d] for d in dirs], [])
        targets  = selected['targets']

        self.method = selected.get('method', ('jacobian', {}))
        self.active = name
        self.mode = dirs
        self.match_names = [s for s in steerers if isinstance(s, str)]
        self.assign = {k: v for s in steerers if isinstance(s, dict)
                       for k, v in s.items()}

        elements = self.model.elements
        self.targets = sorted(targets, key=elements.index)
        self.monitors[:] = sorted(monitors, key=elements.index)
        self.fit_range = (min(self._fit_elements(), key=elements.index),
                          max(self._fit_elements(), key=elements.index))
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

    def _fit_elements(self):
        return list(self.targets) + list(self.monitors)

    #def _involved_elements(self):      # with steerers!

    def update(self):
        self.control.read_all()
        self.update_readouts()
        self.update_records()
        self.update_fit()

    def update_readouts(self):
        self.readouts[:] = [
            # NOTE: this triggers model._retrack in stub!
            MonitorReadout(monitor, self.control.read_monitor(monitor))
            for monitor in self.monitors
        ]

    def update_records(self):
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
            self.match_results = {
                knob.lower(): model.read_param(knob)
                for knob in self.match_names + list(self.assign)
                if knob.lower() in self._knobs
            }
            return self.match_results


class CorrectorWidget(QtGui.QWidget):

    steerer_corrections = None

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

    def get_steerer_row(self, i, v) -> ("Steerer", "Initial", "Final", "Unit"):
        initial = self.corrector.design_values.get(v.lower())
        matched = self.corrector.match_results.get(v.lower())
        changed = matched is not None and not np.isclose(initial, matched)
        style = {
            #'foreground': QtGui.QColor(Qt.red),
            'font': bold(),
        } if changed else {}
        info = self.corrector._knobs[v.lower()]
        return [
            TableItem(v),
            TableItem(change_unit(initial, info.unit, info.ui_unit)),
            TableItem(change_unit(matched, info.unit, info.ui_unit), **style),
            TableItem(get_raw_label(info.ui_unit)),
        ]

    def set_cons_value(self, i, c, value):
        self.corrector.constraints[i] = Constraint(c.elem, c.pos, c.axis, value)

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

    def on_execute_corrections(self):
        """Apply calculated corrections."""
        self.corrector.model.write_params(self.steerer_corrections.items())
        self.corrector.control.write_params(self.steerer_corrections.items())
        self.corrector.apply()

    def init_controls(self):
        for tab in (self.mon_tab, self.con_tab, self.var_tab):
            tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
            tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        corr = self.corrector
        self.mon_tab.set_rowgetter(self.get_readout_row, corr.readouts, unit=True)
        self.var_tab.set_rowgetter(self.get_steerer_row, corr.variables)
        self.con_tab.set_rowgetter(self.get_cons_row, corr.constraints)
        self.combo_config.addItems(list(self.corrector.configs))
        self.combo_config.setCurrentText(self.corrector.active)
        fit_button(self.btn_edit_conf)

    def set_initial_values(self):
        self.update_fit_button.setFocus()
        self.radio_mode_xy.setChecked(True)
        self.corrector.update()

    def connect_signals(self):
        self.update_fit_button.clicked.connect(self.update_fit)
        self.execute_corrections.clicked.connect(self.on_execute_corrections)
        self.combo_config.currentIndexChanged.connect(self.on_change_config)
        self.btn_edit_conf.clicked.connect(self.edit_config)
        self.radio_mode_x.clicked.connect(partial(self.on_change_mode, 'x'))
        self.radio_mode_y.clicked.connect(partial(self.on_change_mode, 'y'))
        self.radio_mode_xy.clicked.connect(partial(self.on_change_mode, 'xy'))

    def update_fit(self):
        """Calculate initial positions / corrections."""
        self.corrector.update()

        if not self.corrector.fit_results or not self.corrector.variables:
            self.steerer_corrections = None
            self.execute_corrections.setEnabled(False)
            return
        self.steerer_corrections = \
            self.corrector.compute_steerer_corrections(self.corrector.fit_results)
        self.execute_corrections.setEnabled(True)
        self.corrector.variables.touch()    # update table view
        #self.var_tab.resizeColumnToContents(0)

    def on_change_config(self, index):
        name = self.combo_config.itemText(index)
        self.corrector.setup(name, self.corrector.mode)
        self.corrector.update()

    def on_change_mode(self, dirs):
        self.corrector.setup(self.corrector.active, dirs)
        self.corrector.update()

        # TODO: make 'optimal'-column in var_tab editable and update
        #       self.execute_corrections.setEnabled according to its values

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

        configs = data.get('multi_grid')
        if not configs:
            QtGui.QMessageBox.critical(
                self,
                'No config defined',
                'No multi grid configuration defined.')
            return False

        model = self.corrector.model
        with open(model.filename, 'w') as f:
            f.write(text)

        self.corrector.configs = configs
        self.data['multi_grid'] = configs

        conf = self.corrector.active if self.corrector.active in configs else next(iter(configs))
        self.corrector.setup(conf)
        self.corrector.update()

        return True
