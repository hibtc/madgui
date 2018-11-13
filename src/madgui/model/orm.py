from contextlib import contextmanager

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import Bounds

import madgui.util.yaml as yaml
from madgui.util.fit import reduced_chisq, fit
from madgui.online.orbit import fit_particle_orbit
from .errors import Ealign, Efcomp, apply_errors


class OrbitResponse:

    def __init__(self, strengths, records, monitors, knobs, steerers):
        self.monitors = monitors
        self.knobs = knobs
        self.steerers = steerers
        self.strengths = strengths
        self.responses = responses = {
            (monitor, knob): (
                (orbit - base), (strength - strengths[knob]), (error + _err))
            for (monitor, knob), (strength, orbit, error) in records.items()
            if knob
            for _, base, _err in [records[monitor, None]]
        }
        self.base_orbit = {
            monitor: (orbit, error)
            for (monitor, knob), (_, orbit, error) in records.items()
            if not knob
        }
        no_response = (
            np.array([0.0, 0.0]),    # delta_orbit
            1e5,                     # delta_param
            np.array([1.0, 1.0]))    # mean_error    TODO use base error
        self.orm = np.dstack([
            np.vstack([
                delta_orbit / delta_param
                for monitor in monitors
                for delta_orbit, delta_param, _ in [
                        responses.get(
                            (monitor.lower(), knob.lower()), no_response)]
            ])
            for knob in knobs
        ])
        self.stddev = np.dstack([
            np.vstack([
                np.sqrt(mean_error) / delta_param
                for monitor in monitors
                for _, delta_param, mean_error in [
                        responses.get(
                            (monitor.lower(), knob.lower()), no_response)]
            ])
            for knob in knobs
        ])

    @classmethod
    def load(cls, model, filenames):
        strengths = {}
        records = {}
        for s, r in map(load_record_file, filenames):
            strengths.update(s)
            records.update(r)
        monitors = {mon.lower() for mon, _ in records}
        knobs = {knob.lower() for _, knob in records if knob}
        return cls(strengths, records, *sorted_mesh(model, monitors, knobs))


def sorted_mesh(model, monitors, knobs):
    elems = model.elements
    knob_elems = {}
    for elem in elems:
        for knob in model.get_elem_knobs(elem):
            knob_elems.setdefault(knob.lower(), []).append(elem.name)
    monitors = sorted(monitors, key=elems.index)
    knobs = sorted(knobs, key=lambda k: elems.index(knob_elems[k][0]))
    steerers = [knob_elems[k][0] for k in knobs]
    return monitors, knobs, steerers


def load_record_file(filename):
    data = yaml.load_file(filename)
    strengths = data['model']
    records = {
        (monitor, knob): (s, np.mean([
            shot[monitor][:2]
            for shot in record['shots']
        ], axis=0), np.var([
            shot[monitor][:2]
            for shot in record['shots']
        ], axis=0, ddof=1) / len(record['shots']))
        for record in data['records']
        for knob, s in (record['optics'] or {None: None}).items()
        for monitor in data['monitors']
    }
    return strengths, records


class Readout:
    def __init__(self, name, posx, posy):
        self.name = name
        self.posx = posx
        self.posy = posy


def fit_init_orbit(model, measured, fit_monitors):
    fit_monitors = sorted(fit_monitors, key=model.elements.index)
    range_start = fit_monitors[0]
    base_orbit = measured.base_orbit
    readouts = [
        Readout(monitor, *base_orbit[monitor.lower()][0])
        for monitor in fit_monitors
    ]
    secmaps = [
        model.sectormap(range_start, monitor)
        for monitor in fit_monitors
    ]
    offsets = {}
    (twiss_init, chisq, singular), curve = fit_particle_orbit(
        model, offsets, readouts, secmaps, fit_monitors[0])
    return twiss_init


class Analysis:

    def __init__(self, model, measured):
        self.model = model
        self.measured = measured
        self.monitors = measured.monitors
        self.steerers = measured.steerers
        self.knobs = measured.knobs

    def init(self, strengths=None):
        print("INITIAL")
        if strengths is None:
            strengths = self.measured.strengths
        self.model.update_globals(strengths.items())
        self.model_orm = self.get_orbit_response()
        sel = self.get_selected_monitors(self.monitors)
        self.info(sel)

    def info(self, sel=None, ddof=0):
        if sel is None:
            sel = slice(None)
        measured = self.measured
        model_orm = self.model_orm
        stddev = measured.stddev
        print("red χ² =", reduced_chisq(
            ((measured.orm - model_orm) / stddev)[sel], ddof))
        print("    |x =", reduced_chisq(
            ((measured.orm - model_orm) / stddev)[sel][:, 0, :], ddof))
        print("    |y =", reduced_chisq(
            ((measured.orm - model_orm) / stddev)[sel][:, 1, :], ddof))

    def get_orbit_response(self):
        return self.model.get_orbit_response_matrix(
            self.monitors, self.knobs)

    def get_selected_monitors(self, selected):
        return [self.monitors.index(m.lower()) for m in selected]

    def plot_monitors(self, select=None, save_to=None):
        if select is None:
            select = self.monitors
        print("plotting monitors: {}".format(" ".join(select)))
        make_monitor_plots(
            select, self.model, self.measured, self.model_orm,
            save_to=save_to)

    def plot_steerers(self, select=None, save_to=None):
        if select is None:
            select = self.steerers
        print("plotting steerers: {}".format(" ".join(select)))
        make_steerer_plots(
            select, self.model, self.measured, self.model_orm,
            save_to=save_to)

    def backtrack(self, monitors):
        print("TWISS INIT")
        self.model.update_twiss_args(
            fit_init_orbit(self.model, self.measured, monitors))
        self.model_orm = self.get_orbit_response()

    def fit(self, errors, monitors, delta=1e-4,
            mode='xy', iterations=50, bounds=None,
            tol=1e-8, use_stddev=True, **kwargs):

        model = self.model
        measured = self.measured
        stddev = (measured.stddev if use_stddev else
                  np.ones(measured.orm.shape))
        err_names = ', '.join(map(repr, errors))

        print("====================")
        print("FIT:", ', '.join(monitors or self.monitors))
        print("VIA:", err_names)

        sel = self.get_selected_monitors(monitors or self.monitors)
        model.madx.eoption(add=True)

        def callback(state):
            print("")
            print("----------------------")
            print("nit    =", state.nit)
            print("Errors :", err_names)
            print("ΔX     =", state.dx)
            print("X_tot  =", state.x)
            print(":: (fit) ::")
            self.info(sel)
            print(":: (overall) ::")
            self.info()
            print("----------------------")

        dims = [i for i, c in enumerate("xy") if c in mode]
        obj_slice = lambda y: y[sel][:, dims, :]

        def objective(values):
            self.model_orm = get_orm(
                model, measured.monitors, measured.knobs, errors, values)
            return obj_slice(self.model_orm)

        x0 = np.zeros(len(errors))
        result = fit(
            objective, x0, obj_slice(measured.orm), obj_slice(stddev),
            bounds=None if bounds is None else Bounds(*bounds), delta=delta,
            tol=tol, iterations=iterations, callback=callback, **kwargs)
        print(result.message)
        apply_errors(model, errors, result.x)
        return result

    @classmethod
    @contextmanager
    def app(cls, model_file, record_files):
        from madgui.core.app import init_app
        from madgui.core.session import Session
        from madgui.core.config import load as load_config
        from glob import glob

        init_app(['madgui'])

        if isinstance(record_files, str):
            record_files = glob(record_files)

        config = load_config(isolated=True)
        with Session(config) as session:
            session.load_model(
                model_file,
                stdout=False)
            model = session.model()
            measured = OrbitResponse.load(model, record_files)
            yield cls(model, measured)


def get_orm(model, monitors, knobs, errors, values):
    with model.undo_stack.rollback("orm_deriv", transient=True):
        with apply_errors(model, errors, values):
            print(".", end='', flush=True)
            model.twiss.invalidate()
            return model.get_orbit_response_matrix(monitors, knobs)


def make_monitor_plots(
        monitor_subset, model, measured, model_orm, comment="Response",
        save_to=None, base_orm=None):
    for index, monitor in enumerate(measured.monitors):
        if monitor in monitor_subset:
            plot_monitor_response(
                plt.figure(1), monitor,
                model, measured, base_orm, model_orm, comment)
            if save_to is None:
                plt.show()
            else:
                plt.savefig('{}-mon-{}-{}.png'.format(save_to, index, monitor))
            plt.clf()


def make_steerer_plots(
        steerer_subset, model, measured, model_orm, comment="Response",
        save_to=None, base_orm=None):
    for index, steerer in enumerate(measured.steerers):
        if steerer in steerer_subset:
            plot_steerer_response(
                plt.figure(1), steerer,
                model, measured, base_orm, model_orm, comment)
            if save_to is None:
                plt.show()
            else:
                plt.savefig('{}-ste-{}-{}.png'.format(save_to, index, steerer))
            plt.clf()


def plot_monitor_response(
        fig, monitor, model, measured, base_orm, model_orm, comment):
    xpos = [model.elements[elem].position for elem in measured.steerers]
    i = measured.monitors.index(monitor)
    lines = []

    for j, ax in enumerate("xy"):
        axes = fig.add_subplot(1, 2, 1+j)
        axes.set_title(ax)
        axes.set_xlabel(r"steerer position [m]")
        if ax == 'x':
            axes.set_ylabel(r"orbit response $\Delta x/\Delta \phi$ [mm/mrad]")
        else:
            axes.yaxis.tick_right()

        axes.errorbar(
            xpos,
            measured.orm[i, j, :].flatten(),
            measured.stddev[i, j, :].flatten(),
            label=ax + " measured")

        if base_orm is not None:
            axes.plot(
                xpos,
                base_orm[i, j, :].flatten(),
                label=ax + " base model")

        lines.append(axes.plot(
            xpos,
            model_orm[i, j, :].flatten(),
            label=ax + " model"))

        axes.legend()

    fig.suptitle("{1}: {0}".format(monitor, comment))
    return lines


def plot_steerer_response(
        fig, steerer, model, measured, base_orm, model_orm, comment):
    xpos = [model.elements[elem].position for elem in measured.monitors]
    i = measured.steerers.index(steerer)
    lines = []

    for j, ax in enumerate("xy"):
        axes = fig.add_subplot(1, 2, 1+j)
        axes.set_title(ax)
        axes.set_xlabel(r"monitor position [m]")
        if ax == 'x':
            axes.set_ylabel(r"orbit response $\Delta x/\Delta \phi$ [mm/mrad]")
        else:
            axes.yaxis.tick_right()

        axes.errorbar(
            xpos,
            measured.orm[:, j, i].flatten(),
            measured.stddev[:, j, i].flatten(),
            label=ax + " measured")

        if base_orm is not None:
            axes.plot(
                xpos,
                base_orm[i, j, :].flatten(),
                label=ax + " base model")

        lines.append(axes.plot(
            xpos,
            model_orm[:, j, i].flatten(),
            label=ax + " model"))

        axes.legend()

    fig.suptitle("{1}: {0}".format(steerer, comment))
    return lines


ERR_ATTR = {
    'sbend': ['angle', 'e1', 'e2', 'k0', 'hgap', 'fint'],
    'quadrupole': ['k1', 'k1s'],
    'hkicker': ['kick', 'tilt'],
    'vkicker': ['kick', 'tilt'],
    'srotation': ['angle'],
}

ERR_EALIGN = ['dx', 'dy', 'ds', 'dpsi', 'dphi', 'dtheta']


# scaling: monitor
# scaling: kicker

def get_elem_ealign(model, name, attrs=ERR_EALIGN, delta=1e-3):
    return [
        Ealign({'range': name}, attr, delta)
        for attr in attrs
    ]


def get_elem_efcomp(model, name, delta=1e-3):
    elem = model.elements[name]
    kwargs = dict(order=None, radius=None)
    if elem.base_name == 'sbend':
        return [Efcomp({'range': name}, 'dkn', [delta], **kwargs)]
    if elem.base_name == 'quadrupole':
        return [
            Efcomp({'range': name}, 'dkn', [0, delta], **kwargs),
            Efcomp({'range': name}, 'dks', [0, delta], **kwargs),
        ]
    return []
