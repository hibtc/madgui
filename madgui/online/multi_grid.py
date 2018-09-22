"""
Multi grid correction method.
"""

# TODO:
# - use CORRECT command from MAD-X rather than custom numpy method?
# - combine with optic variation method

from functools import partial
from itertools import accumulate, product

import numpy as np
import yaml

from madgui.qt import QtCore, QtGui, load_ui

from madgui.util.unit import ui_units, change_unit, get_raw_label
from madgui.util.collections import List
from madgui.util.qt import bold
from madgui.widget.tableview import TableItem
from madgui.model.match import Matcher, Constraint

from .orbit import fit_particle_orbit
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
        super().__init__(control.model(), control._frame.config['matching'])
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
        self.strategy = 'match'
        QtCore.QTimer.singleShot(
            0, partial(control._frame.open_graph, 'orbit'))

    def setup(self, name, dirs=None, force=False):
        if not name or (name == self.active and not force):
            return

        dirs = dirs or self.mode

        self._clr_history()

        selected = self.selected = self.configs[name]
        monitors = selected['monitors']
        steerers = sum([selected['steerers'][d] for d in dirs], [])
        targets = selected['targets']

        params = [k.lower() for k in selected.get('optics', ())]
        self.optic_params = [self._knobs[k] for k in params
                             if k in self._knobs]
        self.optic_elems = params and [
            elem.name
            for elem in self.model.elements
            if any(k.lower() in params
                   for k in self.model.get_elem_knobs(elem))
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
        fit_elements = (list(self.targets) + list(self.monitors) +
                        list(self.optic_elems))
        self.fit_range = (min(fit_elements, key=elements.index, default=0),
                          max(fit_elements, key=elements.index, default=0))
        self.constraints[:] = sorted([
            Constraint(elements[target],
                       elements[target].position,
                       key, float(value))
            for target, values in targets.items()
            for key, value in values.items()
            if key[-1] in dirs
        ], key=lambda c: c.pos)
        self.variables[:] = [
            knob
            for knob in self.match_names + list(self.assign)
            if knob.lower() in self._knobs
        ]

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
        self.base_optics = self._read_vars()
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

    active_optic = None

    def set_optic(self, i):
        optic = {}
        if self.active_optic is not None:
            optic.update({
                k: self.base_optics[k] for k in self.optics[self.active_optic]
            })
        if i is not None:
            optic.update(self.optics[i])
        # only for optic variation method
        self.control.write_params(optic.items())
        self.model.write_params(optic.items())
        self.active_optic = i

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
        strats = {
            'match': self._compute_steerer_corrections_match,
            'orm': self._compute_steerer_corrections_orm,
            'tm': self._compute_steerer_corrections_tm,
        }
        return strats[self.strategy](init_orbit)

    def _compute_steerer_corrections_match(self, init_orbit):
        """
        Compute corrections for the x_steerers, y_steerers.

        :param dict init_orbit: initial conditions as returned by the fit
        """

        def offset(c):
            dx, dy = self._offsets.get(c.elem.name.lower(), (0, 0))
            if c.axis in ('x', 'posx'):
                return dx
            if c.axis in ('y', 'posy'):
                return dy
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
                weight={'x': 1e3, 'y': 1e3, 'px': 1e2, 'py': 1e2},
                constraints=constraints)
            self.match_results = self._push_history()
            return self.match_results

    def _compute_steerer_corrections_tm(self, init_orbit):
        return self._compute_steerer_corrections_orm(init_orbit, 'tm')

    def _compute_steerer_corrections_orm(self, init_orbit, calc_orm='match'):
        def offset(c):
            dx, dy = self._offsets.get(c.elem.name.lower(), (0, 0))
            if c.axis in ('x', 'posx'):
                return dx
            if c.axis in ('y', 'posy'):
                return dy
            return 0
        targets = {
            (c.elem.name, c.axis): c.value+offset(c)
            for c in self.constraints
        }
        S = [
            i for i, (elem, axis) in enumerate(product(self.monitors, 'xy'))
            if (elem.lower(), axis) in targets
        ]

        y_measured = np.array([
            [r.posx, r.posy]
            for r in self.readouts
        ]).flatten()

        y_target = np.array([
            targets.get((elem.lower(), axis), 0.0)
            for elem, axis in product(self.monitors, 'xy')
        ])

        if calc_orm == 'match':
            orm = self.compute_orbit_response_matrix(init_orbit)
        else:
            orm = self.compute_sectormap(init_orbit)

        dvar = np.linalg.lstsq(
            orm.T[S, :], (y_target-y_measured)[S], rcond=1e-10)[0]

        globals_ = self.model.globals
        self.match_results = self._push_history({
            var.lower(): globals_[var] + delta
            for var, delta in zip(self.variables, dvar)
        })
        return self.match_results

    def compute_sectormap(self, init_orbit):
        model = self.model
        elems = model.elements
        with model.undo_stack.rollback("Orbit correction", transient=True):
            model.update_twiss_args(init_orbit)
            model.sector.invalidate()

            elem_by_knob = {}
            for elem in elems:
                for knob in model.get_elem_knobs(elem):
                    elem_by_knob.setdefault(knob.lower(), elem.index)

            return np.vstack([
                np.hstack([
                    model.sectormap(c, m)[[0, 2], 1+2*is_vkicker].flatten()
                    for m in self.monitors
                ])
                for v in self.variables
                for c in [elem_by_knob[v.lower()]]
                for is_vkicker in [elems[c].base_name == 'vkicker']
            ])

    def compute_orbit_response_matrix(self, init_orbit):
        model = self.model
        madx = model.madx

        madx.command.select(flag='interpolate', clear=True)
        tw_args = model._get_twiss_args().copy()
        tw_args.update(init_orbit)
        tw_args['table'] = 'orm_tmp'

        tw0 = madx.twiss(**tw_args)
        x0, y0 = tw0.x, tw0.y
        M = [model.elements[m].index for m in self.monitors]

        def orm_row(var, step):
            try:
                madx.globals[var] += step
                tw1 = madx.twiss(**tw_args)
                x1, y1 = tw1.x, tw1.y
                return np.vstack(((x1-x0)[M],
                                  (y1-y0)[M])).T.flatten() / step
            finally:
                madx.globals[var] -= step
        return np.vstack([
            orm_row(v, 1e-4) for v in self.variables
        ])


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
        self.tab_readouts.set_viewmodel(
            self.get_readout_row, corr.readouts, unit=True)
        self.tab_corrections.set_viewmodel(
            self.get_steerer_row, corr.variables)
        self.tab_targets.set_viewmodel(
            self.get_cons_row, corr.constraints)

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
