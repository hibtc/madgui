import re
from contextlib import ExitStack, contextmanager

import matplotlib.pyplot as plt
import numpy as np

from cpymad.util import is_identifier

import madgui.util.yaml as yaml
from madgui.online.orbit import fit_particle_orbit
from .errors import Param, Ealign, Efcomp, ElemAttr, ScaleAttr, ScaleParam


def get_orm_derivs(model, monitors, knobs, base_orm, params):
    return [get_orm_deriv(model, monitors, knobs, base_orm, p) for p in params]


def get_orm_deriv(model, monitors, knobs, base_orm, param) -> np.array:
    """Compute the derivative of the orbit response matrix with respect to
    the parameter ``p`` as ``ΔR_ij/Δp``."""
    print('.', end='', flush=True)
    with model.undo_stack.rollback("orm_deriv", transient=True):
        with param.vary(model) as step:
            model.twiss.invalidate()
            varied_orm = model.get_orbit_response_matrix(monitors, knobs)
            return (varied_orm - base_orm) / step


def fit_model(
        model, measured, stddev, errors, monitor_subset,
        mode='xy', iterations=50, method='minimize',
        callback=None, **kwargs):
    implementations = {
        'minimize': fit_model_minimize,
        'lstsq': fit_model_lstsq,
    }
    return implementations[method](
        model, measured, stddev, errors, monitor_subset,
        mode=mode, iterations=iterations, callback=callback, **kwargs)


def fit_model_lstsq_single(
        measured_orm, model_orm, model_orm_derivs,
        stddev=1,
        mode='xy',
        monitors=None,
        rcond=1e-8):
    """
    Fit model to the measured ORM via the given params
    (:class:`Param`). Return the best-fit solutions X for the parameters
    and the squared sum of residuals.

    ``measured_orm`` must be a numpy array with the same
    layout as returned our ``get_orm``.

    See also:
    Response Matrix Measurements and Analysis at DESY, Joachim Keil, 2005
    """
    # TODO: add rows for monitor/steerer sensitivity
    Y = measured_orm - model_orm
    A = np.array(model_orm_derivs)
    S = np.broadcast_to(stddev, Y.shape)
    if monitors:
        A = A[:, monitors, :, :]
        Y = Y[monitors, :, :]
        S = S[monitors, :, :]
    if mode == 'x' or mode == 'y':
        d = int(mode == 'y')
        A = A[:, :, d, :]
        Y = Y[:, d, :]
        S = S[:, d, :]
    n = Y.size
    A = A.reshape((-1, n)).T
    Y = Y.reshape((-1, 1))
    S = S.reshape((-1, 1))
    X = np.linalg.lstsq(A/S, Y/S, rcond=rcond)[0]
    return X, reduced_chisq((np.dot(A, X) - Y) / S, len(X))


def reduced_chisq(residuals, ddof):
    residuals = residuals.flatten()
    return np.dot(residuals.T, residuals) / (len(residuals) - ddof)


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


def create_errors_from_spec(spec):
    def error_from_spec(name, value):
        value = 1.0e-4 if value is None else value
        mult = name.endswith('*')
        name = name.rstrip('*')
        if '->' in name:
            elem, attr = name.split('->')
            if mult:
                return ScaleAttr(elem, attr, value)
            return ElemAttr(elem, attr, value)
        if '<' in name:
            elem, attr = re.match(r'(.*)\<(.*)\>', name).groups()
            return Ealign({'range': elem}, attr, value)
        if is_identifier(name):
            if mult:
                return ScaleParam(name, value)
            return Param(name, value)
        # TODO: efcomp field errors!
        raise ValueError("{!r} is not a valid error specification!"
                         .format(name))
    return [error_from_spec(name, value) for name, value in spec.items()]


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
        self.info("initial", sel)

    def info(self, comment, sel=None, errors=None, ddof=1):
        measured = self.measured
        if errors:
            print("X_tot  =", np.array([err.base for err in errors]))
        if sel is None:
            sel = slice(None)
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

    def fit(self, errors, monitors,
            mode='xy', iterations=50,
            use_stddev=True,
            method='minimize'):
        print("Fitting model")
        model = self.model
        measured = self.measured
        stddev = (measured.stddev if use_stddev else
                  np.ones(measured.orm.shape))

        sel = self.get_selected_monitors(monitors or self.monitors)
        for error in errors:
            error.set_base(model.madx)
        model.madx.eoption(add=True)

        def callback(comment, model_orm, sel, errors):
            self.model_orm = model_orm
            self.info(comment, sel, errors)

        fit_model(
            model, measured, stddev, errors, sel,
            mode=mode,
            iterations=iterations,
            method=method,
            callback=callback)
        self.model_orm = self.get_orbit_response()

        print("Errors =", [err.name for err in errors])

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


def fit_model_minimize(
        model, measured, stddev, errors,
        monitor_subset,
        bounds=None,
        mode='xy', iterations=100, callback=None):

    from scipy.optimize import minimize, Bounds

    monitors = measured.monitors
    knobs = measured.knobs
    stddev = measured.stddev
    sel = monitor_subset
    callback = callback or NOP

    d = [i for i, c in enumerate("xy") if c in mode]

    def objective(values):
        nonlocal model_orm, chisq
        with ExitStack() as stack:
            for error, value in zip(errors, values):
                error.step = value
                stack.enter_context(error.vary(model))
            model_orm = model.get_orbit_response_matrix(
                monitors, knobs)
            chisq = reduced_chisq(
                ((measured.orm - model_orm) / stddev)[sel][:, d, :], 1)
            print(values, chisq)
            return chisq

    error_values = np.zeros(len(errors))
    result = minimize(
        objective, error_values,
        bounds=Bounds(*bounds) if bounds else None,
        tol=1e-6, options={'maxiter': iterations})
    results = result.x
    print(result.message)

    for param, value in zip(errors, results.flatten()):
        param.base += value
        param.apply(model.madx, value)

    model_orm = model.get_orbit_response_matrix(
        monitors, knobs)
    chisq = reduced_chisq(
        ((measured.orm - model_orm) / stddev)[sel][:, d, :], 1)

    for err, val in zip(errors, results.flatten()):
        err.base += val

    print("red χ² =", chisq)
    print("ΔX     =", results.flatten())
    print("Errors =", [err.name for err in errors])
    callback("final", model_orm, sel, errors)


def fit_model_lstsq(
        model, measured, stddev, errors, monitor_subset,
        mode='xy', iterations=100, callback=None):

    monitors = measured.monitors
    knobs = measured.knobs
    callback = callback or NOP

    for i in range(iterations):
        print("ITERATION", i)
        model_orm = model.get_orbit_response_matrix(monitors, knobs)
        callback("iteration {}".format(i), errors, model_orm)
        print("...", end='', flush=True)

        results, chisq = fit_model_lstsq_single(
            measured.orm, model_orm, get_orm_derivs(
                model, monitors, knobs, model_orm, errors),
            stddev=stddev,
            mode=mode,
            monitors=monitor_subset,
        )

        print(" ->")
        print("ΔX     =", results.flatten())
        print("red χ² =", chisq, "(linear hypothesis)")

        for param, value in zip(errors, results.flatten()):
            param.base += value
            param.apply(model.madx, value)

    model_orm = model.get_orbit_response_matrix(monitors, knobs)
    callback("final", model_orm, monitor_subset, errors)


def NOP(*args, **kwargs):
    pass


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
