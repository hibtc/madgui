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


class DataRecord:

    def __init__(self, sequence, strengths, records):
        self.sequence = sequence
        self.strengths = strengths
        self.records = records


def load_record_files(filenames):
    return join_record_files(map(load_record_file, filenames))


def load_record_file(filename):
    data = load_yaml(filename)
    sequence = data['sequence']
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
    return DataRecord(sequence, strengths, records)


def join_record_files(data_records):
    mats = iter(data_records)
    acc = next(mats)
    for mat in mats:
        assert acc.sequence == mat.sequence
        assert acc.strengths == mat.strengths
        acc.records.update(mat.records)
    return acc


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


def get_orms(model, measured, fit_args):

    strengths = measured.strengths
    records = measured.records

    responses = {
        (monitor, knob): (
            (orbit - base), (strength - strengths[knob]), (error + _err))
        for (monitor, knob), (strength, orbit, error) in records.items()
        if knob
        for _, base, _err in [records[monitor, None]]
    }

    base_orbit = {
        monitor: (orbit, error)
        for (monitor, knob), (_, orbit, error) in records.items()
        if not knob
    }

    # Get list of all knobs and corresponding knobs:
    elems = model.elements
    knob_elems = {}
    for elem in elems:
        for knob in model.get_elem_knobs(elem):
            knob_elems.setdefault(knob.lower(), []).append(elem.name)

    monitors = sorted({mon.lower() for mon, _ in records}, key=elems.index)
    knobs = sorted({knob.lower() for _, knob in records if knob},
                   key=lambda k: elems.index(knob_elems[k][0]))
    steerers = [knob_elems[k][0] for k in knobs]

    model.update_globals(strengths.items())

    no_response = (np.array([0.0, 0.0]),    # delta_orbit
                   1e5,                     # delta_param
                   np.array([1.0, 1.0]))    # mean_error    TODO use base error
    measured_orm = np.vstack([
        np.hstack([
            delta_orbit / delta_param
            for monitor in monitors
            for delta_orbit, delta_param, _ in [
                    responses.get(
                        (monitor.lower(), knob.lower()), no_response)]
        ])
        for knob in knobs
    ]).T

    stddev = np.vstack([
        np.hstack([
            np.sqrt(mean_error) / delta_param
            for monitor in monitors
            for _, delta_param, mean_error in [
                    responses.get(
                        (monitor.lower(), knob.lower()), no_response)]
        ])
        for knob in knobs
    ]).T if fit_args.get('stddev', False) else 1

    return monitors, steerers, knobs, base_orbit, measured_orm, stddev


def analyze(model, data_records, fit_args):

    monitors, steerers, knobs, base_orbit, measured_orm, stddev = get_orms(
        model, data_records, fit_args)

    errors = create_errors_from_spec(fit_args)
    for error in errors:
        error.set_base(model.madx)

    model_orm = model.get_orbit_response_matrix(monitors, knobs)
    print("INITIAL red χ² = ", reduced_chisq(
        (measured_orm - model_orm) / stddev, len(errors)))
    make_plots(
        fit_args, model, monitors, steerers,
        model_orm, measured_orm, stddev)

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
        print()
        print()

        model_orm = model.get_orbit_response_matrix(monitors, knobs)
        print("red χ² = ", reduced_chisq(
            (measured_orm - model_orm) / stddev, len(errors)), "(actual)")
        make_plots(
            fit_args, model, monitors, steerers,
            model_orm, measured_orm, stddev)


def make_plots(
        setup_args, model, monitors, steerers,
        model_orm, measured_orm, stddev):
    monitor_subset = setup_args.get('plot_monitors', [])
    steerer_subset = setup_args.get('plot_steerers', [])

    plot_monitor_response(
        model, monitors, steerers, monitor_subset,
        model_orm, measured_orm, stddev)

    plot_steerer_response(
        model, monitors, steerers, steerer_subset,
        model_orm, measured_orm, stddev)


def plot_monitor_response(
        model, monitors, steerers, monitor_subset,
        model_orm, measured_orm, stddev):
    xpos = [model.elements[elem].position for elem in steerers]

    shape = (len(monitors), 2, len(steerers))
    measured_orm = measured_orm.reshape(shape)
    model_orm = model_orm.reshape(shape)
    stddev = stddev.reshape(shape)

    for i, monitor in enumerate(monitors):
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

        plt.suptitle(monitor)

        plt.show()
        plt.cla()


def plot_steerer_response(
        model, monitors, steerers, steerer_subset,
        model_orm, measured_orm, stddev):

    shape = (len(monitors), 2, len(steerers))
    measured_orm = measured_orm.reshape(shape)
    model_orm = model_orm.reshape(shape)
    stddev = stddev.reshape(shape)

    xpos = [model.elements[elem].position for elem in monitors]
    for i, steerer in enumerate(steerers):
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

        plt.suptitle(steerer)

        plt.show()
        plt.cla()
