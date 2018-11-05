import re

import matplotlib.pyplot as plt
import numpy as np
import yaml

from cpymad.util import is_identifier
from madgui.online.orbit import fit_particle_orbit
from .errors import Param, Ealign, ElemAttr, ScaleAttr, ScaleParam


def get_orm_derivs(model, monitors, knobs, base_orm, params):
    return [get_orm_deriv(model, monitors, knobs, base_orm, p) for p in params]


def get_orm_deriv(model, monitors, knobs, base_orm, param) -> np.array:
    """Compute the derivative of the orbit response matrix with respect to
    the parameter ``p`` as ``ΔR_ij/Δp``."""
    with model.undo_stack.rollback("orm_deriv", transient=True):
        with param.vary(model) as step:
            model.twiss.invalidate()
            varied_orm = model.get_orbit_response_matrix(monitors, knobs)
            return (varied_orm - base_orm) / step


def fit_model(measured_orm, model_orm, model_orm_derivs,
              steerer_errors=False,
              monitor_errors=False,
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
    if steerer_errors:
        A = np.hstack((A, -model_orm))
    if monitor_errors:
        A = np.hstack((A, +model_orm))
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


def load_yaml(filename):
    """Load yaml document from filename."""
    with open(filename) as f:
        return yaml.safe_load(f)


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
    data = load_yaml(filename)
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


def analyze(model, measured, fit_args):

    monitors = measured.monitors
    knobs = measured.knobs
    stddev = (measured.stddev if fit_args.get('stddev') else
              np.ones(measured.orm.shape))
    errors = create_errors_from_spec(fit_args['errors'])
    for error in errors:
        error.set_base(model.madx)
    model.madx.eoption(add=True)

    sel = [
        monitors.index(m.lower())
        for m in fit_args.get('fit_monitors', monitors)
    ]

    def info(comment):
        print("X_tot  =", np.array([err.base for err in errors]))
        print("red χ² =", reduced_chisq(
            ((measured.orm - model_orm) / stddev)[sel], len(errors)))
        print("    |x =", reduced_chisq(
            ((measured.orm - model_orm) / stddev)[sel][:, 0, :], len(errors)))
        print("    |y =", reduced_chisq(
            ((measured.orm - model_orm) / stddev)[sel][:, 1, :], len(errors)))
        make_plots(fit_args, model, measured, model_orm, comment)

    print("INITIAL")
    model.update_globals(measured.strengths.items())
    model_orm = model.get_orbit_response_matrix(monitors, knobs)
    info("initial")

    fit_twiss = fit_args.get('fit_twiss')
    if fit_twiss:
        print("TWISS INIT")
        model.update_twiss_args(fit_init_orbit(model, measured, fit_twiss))
        model_orm = model.get_orbit_response_matrix(monitors, knobs)
        info("twiss_init")
        model.madx.use(sequence=model.seq_name)

    for i in range(fit_args.get('iterations', 1)):
        print("ITERATION", i)

        results, chisq = fit_model(
            measured.orm, model_orm, get_orm_derivs(
                model, monitors, knobs, model_orm, errors),
            monitor_errors=fit_args.get('monitor_errors'),
            steerer_errors=fit_args.get('steerer_errors'),
            stddev=stddev,
            mode=fit_args.get('mode', 'xy'),
            monitors=sel,
        )

        for param, value in zip(errors, results.flatten()):
            param.base += value
            param.apply(model.madx, value)

        model_orm = model.get_orbit_response_matrix(monitors, knobs)

        print("red χ² =", chisq, "(linear hypothesis)")
        print("ΔX     =", results.flatten())
        info("iteration {}".format(i))


def make_plots(setup_args, model, measured, model_orm, comment="Response"):
    monitor_subset = setup_args.get('plot_monitors', [])
    steerer_subset = setup_args.get('plot_steerers', [])
    for monitor in measured.monitors:
        if monitor in monitor_subset:
            plot_monitor_response(
                plt.figure(1), monitor, model, measured, model_orm, comment)
            plt.show()
            plt.clf()
    for steerer in measured.steerers:
        if steerer in steerer_subset:
            plot_steerer_response(
                plt.figure(1), steerer, model, measured, model_orm, comment)
            plt.show()
            plt.clf()


def plot_monitor_response(fig, monitor, model, measured, model_orm, comment):
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

        lines.append(axes.plot(
            xpos,
            model_orm[i, j, :].flatten(),
            label=ax + " model"))

        axes.legend()

    fig.suptitle("{1}: {0}".format(monitor, comment))
    return lines


def plot_steerer_response(fig, steerer, model, measured, model_orm, comment):
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

        lines.append(axes.plot(
            xpos,
            model_orm[:, j, i].flatten(),
            label=ax + " model"))

        axes.legend()

    fig.suptitle("{1}: {0}".format(steerer, comment))
    return lines
