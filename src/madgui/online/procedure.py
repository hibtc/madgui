from itertools import accumulate, product
import logging
import textwrap

import numpy as np

from madgui.qt import QtCore

import madgui.util.yaml as yaml
from madgui.util.collections import List

from madgui.model.match import Matcher
from .control import MonitorReadout
from .orbit import fit_particle_orbit


class OrbitRecord:

    def __init__(self, monitor, readout, optics, tm):
        self.monitor = monitor
        self.readout = readout
        self.optics = optics
        self.tm = tm


class Target:

    def __init__(self, elem, x, y):
        self.elem = elem
        self.x = x
        self.y = y


class Corrector(Matcher):

    """
    Class for orbit correction procedure.
    """

    mode = 'xy'

    def __init__(self, session, direct=True):
        super().__init__(session.model(), session.config['matching'])
        self.session = session
        self.control = control = session.control
        self.direct = direct
        self._knobs = control.get_knobs()
        self.file = None
        self.use_backtracking = True
        self.use_delta_objective = False
        # save elements
        self.monitors = List()
        self.targets = List()
        self.readouts = List()
        self.records = List()
        self.fit_range = None
        self.objective_values = {}
        self._offsets = session.config['online_control']['offsets']
        self.optics = List()
        self.strategy = 'match'
        # for ORM
        kick_elements = ('hkicker', 'vkicker', 'kicker', 'sbend')
        self.all_kickers = [
            elem for elem in self.model.elements
            if elem.base_name.lower() in kick_elements]
        self.all_monitors = [
            elem.name for elem in self.model.elements
            if elem.base_name.lower().endswith('monitor')]

    def setup(self, config, dirs=None):
        dirs = dirs or self.mode

        self._clr_history()

        elements = self.model.elements
        self.selected = config
        monitors = sorted(config['monitors'], key=elements.index)
        last_mon = max(map(elements.index, monitors), default=0)

        knob_elems = {}
        for elem in elements:
            for knob in self.model.get_elem_knobs(elem):
                knob_elems.setdefault(knob.lower(), []).append(elem)

        # steerer optics -> good default for ORM analysis
        optic_knobs = config.setdefault('optics', [
            knob
            for name in self.all_kickers
            for elem in [elements[name]]
            if elem.index < last_mon
            for knob in self.model.get_elem_knobs(elem)
        ])
        optic_knobs = [k.lower() for k in optic_knobs]

        self.optic_elems = [
            elem.name.lower()
            for knob in optic_knobs
            for elem in knob_elems[knob]
        ]

        self.optic_params = [self._knobs[k] for k in optic_knobs
                             if k in self._knobs]

        # again, steerer optics only useful for ORM
        config.setdefault('steerers', {
            'x': [knob for knob in optic_knobs
                  if any(elem.base_name != 'vkicker'
                         for elem in knob_elems[knob])],
            'y': [knob for knob in optic_knobs
                  if any(elem.base_name == 'vkicker'
                         for elem in knob_elems[knob])],
        })

        targets = config.setdefault('targets', {})
        steerers = sum([config['steerers'][d] for d in dirs], [])

        self.method = config.get('method', ('jacobian', {}))
        self.mode = dirs
        self.match_names = [s for s in steerers if isinstance(s, str)]
        self.assign = {k: v for s in steerers if isinstance(s, dict)
                       for k, v in s.items()}

        targets = sorted(targets, key=elements.index)
        self.objective_values.update({
            t.elem: (t.x, t.y)
            for t in self.targets
        })
        self.targets[:] = [
            Target(elem, x, y)
            for elem in targets
            for x, y in [self.objective_values.get(elem, (0, 0))]
        ]
        self.monitors[:] = sorted(monitors, key=elements.index)
        fit_elements = targets + list(self.monitors) + list(self.optic_elems)
        self.fit_range = (min(fit_elements, key=elements.index, default=0),
                          max(fit_elements, key=elements.index, default=0))
        self.variables[:] = [
            knob
            for knob in self.match_names + list(self.assign)
            if knob.lower() in self._knobs
        ]

    def set_optics_delta(self, deltas, default):
        self.base_optics = {
            knob: self.model.read_param(knob)
            for knob in self.control.get_knobs()
        }
        self.optics = [{}] + [
            {knob: self.base_optics[knob] + delta}
            for knob in self.match_names
            if knob.lower() in self._knobs
            for delta in [deltas.get(knob.lower(), default)]
            if delta
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

    def _push_history(self, results):
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
        self.base_optics = {
            knob: self.model.read_param(knob)
            for knob in self.control.get_knobs()
        }
        self.cur_results = self._push_history(self._read_vars())

    def update_readouts(self):
        last_readouts = self._read_monitors()
        while True:
            readouts = self._read_monitors()
            if readouts == last_readouts:
                break
            last_readouts = readouts
        self.readouts[:] = [
            MonitorReadout(monitor, data)
            for monitor, data in readouts.items()
        ]
        return list(self.readouts)

    def _read_monitors(self):
        return {
            monitor: self.control.read_monitor(monitor)
            for monitor in self.monitors
        }

    def update_records(self):
        if self.direct:
            self.records[:] = self.current_orbit_records()

    def update_fit(self):
        if len(self.records) < 2 or len(self.variables) < 1:
            return

        if self.use_backtracking:
            init_orbit, chi_squared, singular = \
                self.fit_particle_orbit(self.records)
            if singular or not init_orbit:
                return
            self.model.update_twiss_args(init_orbit)

        self.compute_steerer_corrections()

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
        # NOTE: It is currently necessary to always change `model` before
        # `control` because the test backend asks the model for new SD values.
        # TODO: we should let have the test backend have its own model to
        # prevent such issues.
        self.model.write_params(optic.items())
        self.control.write_params(optic.items())
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

    def compute_steerer_corrections(self):
        strats = {
            'match': self._compute_steerer_corrections_match,
            'orm': self._compute_steerer_corrections_orm_ndiff1,
            'tm': self._compute_steerer_corrections_orm_sectormap,
        }
        self.match_results = results = strats[self.strategy]()
        self._push_history(results)
        return results

    def _compute_steerer_corrections_match(self):
        """
        Compute corrections for the x_steerers, y_steerers.
        """
        model = self.model
        constraints = self._get_constraints()
        with model.undo_stack.rollback("Orbit correction", transient=True):
            model.update_globals(self.assign)
            model.match(
                vary=self.match_names,
                limits=self.selected.get('limits'),
                method=self.method,
                weight={'x': 1e3, 'y': 1e3, 'px': 1e2, 'py': 1e2},
                constraints=constraints)
            return self._read_vars()

    def _compute_steerer_corrections_orm_sectormap(self):
        return self._compute_steerer_corrections_orm(
            self.compute_sectormap())

    def _compute_steerer_corrections_orm_ndiff1(self):
        return self._compute_steerer_corrections_orm(
            self.compute_orbit_response_matrix())

    def _get_objective_deltas(self):
        use_delta_objective = self.use_delta_objective
        if use_delta_objective and not self.knows_targets_readouts():
            use_delta_objective = False
            logging.warning(
                "Matching absolute orbit (more sensitive to inaccurate "
                "backtracking)!")

        if use_delta_objective:
            measured = {
                (r.name.lower(), ax): val
                for r in self.readouts
                for ax, val in zip("xy", (r.posx, r.posy))
            }
        else:
            offsets = self._offsets
            elem_twiss = self.model.get_elem_twiss
            measured = {
                (el, ax): elem_twiss(t.elem)[ax] - offset
                for t in self.targets
                for el in [t.elem.lower()]
                for ax, offset in zip("xy", offsets.get(el, (0, 0)))
            }
        return [
            (el, ax, objective_value - measured_value)
            for el, ax, objective_value in self._get_objectives()
            for measured_value in [measured.get(((el, ax)))]
        ]

    def _compute_steerer_corrections_orm(self, orm):
        mons, axs, deltas = zip(*self._get_objective_deltas())
        targets = set(zip(mons, axs))
        S = [
            i for i, (elem, axis) in enumerate(product(self.monitors, 'xy'))
            if (elem.lower(), axis) in targets
        ]
        dvar = np.linalg.lstsq(
            orm.T[S, :], deltas, rcond=1e-10)[0]
        globals_ = self.model.globals
        return {
            var.lower(): globals_[var] + delta
            for var, delta in zip(self.variables, dvar)
        }

    def _get_constraints(self):
        model = self.model
        elements = model.elements
        elem_twiss = model.get_elem_twiss
        return [
            (elements[mon], None, ax, elem_twiss(mon)[ax] + delta)
            for mon, ax, delta in self._get_objective_deltas()
        ]

    def knows_targets_readouts(self):
        targets = {t.elem.lower() for t in self.targets}
        monitors = {m.lower() for m in self.monitors}
        return targets.issubset(monitors)

    def _get_objectives(self):
        return [
            (t.elem.lower(), ax, val)
            for t in self.targets
            for ax, val in zip("xy", (t.x, t.y))
            if ax in self.mode
        ]

    def compute_sectormap(self):
        model = self.model
        elems = model.elements
        with model.undo_stack.rollback("Orbit correction", transient=True):
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

    # TODO: share implementation with `madgui.model.orm.NumericalORM`!!
    def compute_orbit_response_matrix(self):
        model = self.model
        madx = model.madx

        madx.command.select(flag='interpolate', clear=True)
        tw_args = model._get_twiss_args().copy()
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

    def add_record(self, step, shot):
        # update_vars breaks ORM procedures because it re-reads base_optics!
        # self.update_vars()
        self.control.read_all()
        records = self.current_orbit_records()
        self.records.extend(records)
        if self.file:
            if shot == 0:
                self.write_data([{
                    'optics': self.optics[step],
                }])
                self.file.write('  shots:\n')
            self.write_data([{
                r.monitor: [r.readout.posx, r.readout.posy,
                            r.readout.envx, r.readout.envy]
                for r in records
            }], "  ")

    def open_export(self, fname):
        self.file = open(fname, 'wt', encoding='utf-8')

        self.write_data({
            'sequence': self.model.seq_name,
            'monitors': self.selected['monitors'],
            'steerers': self.optic_elems,
            'knobs':    self.selected['optics'],
            'twiss_args': self.model._get_twiss_args(),
        })
        self.write_data({
            'model': self.base_optics,
        }, default_flow_style=False)
        self.file.write(
            '#    posx[m]    posy[m]    envx[m]    envy[m]\n'
            'records:\n')

    def close_export(self):
        if self.file:
            self.file.close()
            self.file = None

    def write_data(self, data, indent="", **kwd):
        self.file.write(textwrap.indent(yaml.safe_dump(data, **kwd), indent))
        self.file.flush()


class ProcBot:

    def __init__(self, widget, corrector):
        self.widget = widget
        self.corrector = corrector
        self.running = False
        self.model = corrector.model
        self.control = corrector.control
        self.totalops = 100
        self.progress = 0
        self.timer = None

    def start(self, num_ignore, num_average, gui=True):
        self.corrector.records.clear()
        self.numsteps = len(self.corrector.optics)
        self.numshots = num_average + num_ignore + 1
        self.num_ignore = num_ignore
        self.totalops = self.numsteps * self.numshots
        self.progress = 0
        self.running = True
        self.widget.update_ui()
        self.widget.log("Started")
        self.last_readouts = None
        if gui:
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(self.poll)
            self.timer.start(2000)

    def finish(self):
        self.stop()
        self.widget.update_fit()
        self.widget.log("Finished\n")

    def cancel(self):
        if self.running:
            self.stop()
            self.reset()
            self.widget.log("Cancelled by user.\n")

    def stop(self):
        if self.running:
            self.corrector.close_export()
            self.corrector.set_optic(None)
            self.running = False
            self.widget.update_ui()
        if self.timer:
            self.timer.stop()
            self.timer = None

    def reset(self):
        self.widget.update_ui()

    def poll(self):
        if not self.running:
            return

        step = self.progress // self.numshots
        shot = self.progress % self.numshots

        if shot == 0:
            self.widget.log(
                "optic {} of {}: {}", step, self.numsteps,
                self.corrector.optics[step])
            self.corrector.set_optic(step)

            self.progress += 1
            self.widget.set_progress(self.progress)
            return

        readouts = self.read_monitors()
        if readouts == self.last_readouts:
            return
        self.last_readouts = readouts

        self.progress += 1
        self.widget.set_progress(self.progress)

        if shot <= self.num_ignore:
            self.widget.log('  -> shot {} (ignored)', shot)
            return

        self.widget.log('  -> shot {}', shot)
        self.corrector.add_record(step, shot-self.num_ignore-1)

        if self.progress == self.totalops:
            self.finish()

    def read_monitors(self):
        self.corrector.update_readouts()
        return {r.name: r.data for r in self.corrector.readouts}
