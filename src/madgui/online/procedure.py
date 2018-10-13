
from itertools import accumulate, product
import textwrap

import numpy as np

from madgui.qt import QtCore

import madgui.util.yaml as yaml
from madgui.util.collections import List

from madgui.model.match import Matcher, Constraint
from .orbit import fit_particle_orbit


class OrbitRecord:

    def __init__(self, monitor, readout, optics, tm):
        self.monitor = monitor
        self.readout = readout
        self.optics = optics
        self.tm = tm


class Corrector(Matcher):

    """
    Class for orbit correction procedure.
    """

    mode = 'xy'

    # TODO: elem_knobs

    def __init__(self, session, direct=True):
        super().__init__(session.model(), session.config['matching'])
        self.fit_results = None
        self.session = session
        self.control = control = session.control
        self.direct = direct
        self._knobs = control.get_knobs()
        self.file = None
        self.elem_knobs = None
        # save elements
        self.monitors = List()
        self.readouts = List()
        self.records = List()
        self.fit_range = None
        self._offsets = session.config['online_control']['offsets']
        self.optics = List()
        self.strategy = 'match'
        # for ORM
        kick_elements = ('hkicker', 'vkicker', 'kicker', 'sbend')
        self.all_kickers = [
            elem.name for elem in self.model.elements
            if elem.base_name.lower() in kick_elements]
        self.all_monitors = [
            elem.name for elem in self.model.elements
            if elem.base_name.lower().endswith('monitor')]

    def setup(self, config, dirs=None):
        dirs = dirs or self.mode

        self._clr_history()

        selected = self.selected = config
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

    def configure(self, config):
        elements = self.model.elements

        monitors = sorted(config['monitors'], key=elements.index)
        last_monitor = elements.index(monitors[-1])

        self.elem_knobs = elem_knobs = [
            (elem, knob) for name in self.all_kickers
            for elem in [elements[name]]
            if elem.index < last_monitor
            for knob in self.model.get_elem_knobs(elem)
        ]

        self.selected.update({
            'monitors': monitors,
            'steerers': {
                'x': [knob for elem, knob in elem_knobs
                      if elem.base_name != 'vkicker'],
                'y': [knob for elem, knob in elem_knobs
                      if elem.base_name == 'vkicker'],
            },
            'optics': [knob for _, knob in elem_knobs],
        })
        self.setup(self.selected)

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
        self.base_optics = {
            knob: self.model.read_param(knob)
            for knob in self.control.get_knobs()
        }
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

    def add_record(self, step, shot):
        self.update_vars()
        self.update_readouts()
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
            'steerers': [elem.name for elem, _ in self.elem_knobs],
            'knobs':    [knob for _, knob in self.elem_knobs],
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


class ProcBot:

    def __init__(self, widget, corrector):
        self.widget = widget
        self.corrector = corrector
        self.running = False
        self.model = corrector.model
        self.control = corrector.control
        self.totalops = 100
        self.progress = 0

    def start(self, num_ignore, num_average):
        self.corrector.records.clear()
        self.numsteps = len(self.corrector.optics)
        self.numshots = num_average + num_ignore + 1
        self.num_ignore = num_ignore
        self.totalops = self.numsteps * self.numshots
        self.progress = 0
        self.running = True
        self.widget.update_ui()
        self.widget.log("Started")
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(300)

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
            self.widget.log("optic {}".format(step))
            self.corrector.set_optic(step)

            self.last_readouts = self.read_monitors()
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
