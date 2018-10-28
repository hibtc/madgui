import matplotlib.pyplot as plt
import numpy as np
import yaml

from .errors import Param, Ealign, Efcomp


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
    S = np.array(stddev)
    if steerer_errors:
        A = np.hstack((A, -model_orm))
    if monitor_errors:
        A = np.hstack((A, +model_orm))
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
        self.orm = np.vstack([
            np.hstack([
                delta_orbit / delta_param
                for monitor in monitors
                for delta_orbit, delta_param, _ in [
                        responses.get(
                            (monitor.lower(), knob.lower()), no_response)]
            ])
            for knob in knobs
        ]).T
        self.stddev = np.vstack([
            np.hstack([
                np.sqrt(mean_error) / delta_param
                for monitor in monitors
                for _, delta_param, mean_error in [
                        responses.get(
                            (monitor.lower(), knob.lower()), no_response)]
            ])
            for knob in knobs
        ]).T

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
    # TODO: EALIGN, tilt, FINT, FINTX, L, AT, …
    return [
        Param(knob, step)
        for knob, step in spec.get('knobs', {}).items()
    ] + [
        Ealign(**s)
        for s in spec.get('ealign', ())
    ] + [
        Efcomp(**s)
        for s in spec.get('efcomp', ())
    ]


def analyze(model, measured, fit_args):

    model.update_globals(measured.strengths.items())
    monitors = measured.monitors
    knobs = measured.knobs
    measured_orm = measured.orm
    stddev = measured.stddev

    errors = create_errors_from_spec(fit_args)
    for error in errors:
        error.set_base(model.madx)

    model_orm = model.get_orbit_response_matrix(monitors, knobs)
    print("INITIAL")
    print("red χ² =", reduced_chisq(
        (measured_orm - model_orm) / stddev, len(errors)))
    print("X_tot  =", np.array([err.base for err in errors]))
    make_plots(fit_args, model, measured, model_orm, "initial")

    for i in range(fit_args.get('iterations', 1)):
        print("ITERATION", i)

        results, chisq = fit_model(
            measured_orm, model_orm, get_orm_derivs(
                model, monitors, knobs, model_orm, errors),
            monitor_errors=fit_args.get('monitor_errors'),
            steerer_errors=fit_args.get('steerer_errors'),
            stddev=stddev)
        print("ΔX     =", results.flatten())
        print("X_tot  =", np.array([
            err.base + delta
            for err, delta in zip(errors, results.flatten())
        ]))
        print("red χ² =", chisq, "(linear hypothesis)")

        for param, value in zip(errors, results.flatten()):
            param.base += value
            param.apply(model.madx, param.base)

        model_orm = model.get_orbit_response_matrix(monitors, knobs)
        print("red χ² =", reduced_chisq(
            (measured_orm - model_orm) / stddev, len(errors)), "(actual)")
        make_plots(fit_args, model, measured, model_orm,
                   "Iteration {}".format(i))


def make_plots(setup_args, model, measured, model_orm, comment="Response"):
    monitor_subset = setup_args.get('plot_monitors', [])
    steerer_subset = setup_args.get('plot_steerers', [])
    plot_monitor_response(model, measured, monitor_subset, model_orm, comment)
    plot_steerer_response(model, measured, steerer_subset, model_orm, comment)


def plot_monitor_response(model, measured, monitor_subset, model_orm, comment):
    shape = (len(measured.monitors), 2, len(measured.steerers))
    measured_orm = measured.orm.reshape(shape)
    model_orm = model_orm.reshape(shape)
    stddev = measured.stddev.reshape(shape)
    xpos = [model.elements[elem].position for elem in measured.steerers]

    for i, monitor in enumerate(measured.monitors):
        if monitor not in monitor_subset:
            continue

        for j, ax in enumerate("xy"):
            axes = plt.subplot(1, 2, 1+j)
            plt.title(ax)
            plt.xlabel(r"steerer position [m]")
            if ax == 'x':
                plt.ylabel(r"orbit response $\Delta x/\Delta \phi$ [mm/mrad]")
            else:
                axes.yaxis.tick_right()

            plt.errorbar(
                xpos,
                measured_orm[i, j, :].flatten(),
                stddev[i, j, :].flatten(),
                label=ax + " measured")

            plt.plot(
                xpos,
                model_orm[i, j, :].flatten(),
                label=ax + " model")

            plt.legend()

        plt.suptitle("{1}: {0}".format(monitor, comment))

        plt.show()
        plt.cla()


def plot_steerer_response(model, measured, steerer_subset, model_orm, comment):
    shape = (len(measured.monitors), 2, len(measured.steerers))
    measured_orm = measured.orm.reshape(shape)
    model_orm = model_orm.reshape(shape)
    stddev = measured.stddev.reshape(shape)
    xpos = [model.elements[elem].position for elem in measured.monitors]

    for i, steerer in enumerate(measured.steerers):
        if steerer not in steerer_subset:
            continue

        for j, ax in enumerate("xy"):
            axes = plt.subplot(1, 2, 1+j)
            plt.title(ax)
            plt.xlabel(r"monitor position [m]")
            if ax == 'x':
                plt.ylabel(r"orbit response $\Delta x/\Delta \phi$ [mm/mrad]")
            else:
                axes.yaxis.tick_right()

            plt.errorbar(
                xpos,
                measured_orm[:, j, i].flatten(),
                stddev[:, j, i].flatten(),
                label=ax + " measured")

            plt.plot(
                xpos,
                model_orm[:, j, i].flatten(),
                label=ax + " model")

            plt.legend()

        plt.suptitle("{1}: {0}".format(steerer, comment))

        plt.show()
        plt.cla()
