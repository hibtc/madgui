import numpy as np
import yaml

from .errors import Param, Ealign, Efcomp


class NumericalORM:

    """Helper for ORM calculations."""

    def __init__(self, model, monitors, steerers, knobs):
        self.madx = model.madx
        self.monitors = [model.elements[el] for el in monitors]
        self.steerers = [model.elements[el] for el in steerers]
        self.knobs = knobs
        self.twiss_args = model.twiss_args
        self.base_tw = None
        self.base_orm = None

    def set_operating_point(self, table='base'):
        """Set the base model, and calculate the model ORM. Must be called
        before other methods."""
        self.base_tw = self.twiss(table)
        self.base_orm = self.get_orm()

    def twiss(self, table):
        """Compute TWISS with the current settings, using a specified table
        name in MAD-X."""
        return self.madx.twiss(**dict(self.twiss_args, table=table))

    def get_orm_derivs(self, params):
        return [self.get_orm_deriv(p) for p in params]

    def get_orm_deriv(self, param) -> np.array:
        """Compute the derivative of the orbit response matrix with respect to
        the parameter ``p`` as ``ΔR_ij/Δp``."""
        backup_tw = self.base_tw
        backup_orm = self.base_orm
        with param.vary(self) as step:
            print("DERIV", param)
            self.set_operating_point('base_deriv')
            try:
                return (self.base_orm - backup_orm) / step
            finally:
                self.base_tw = backup_tw
                self.base_orm = backup_orm

    def get_orm(self) -> np.array:
        """
        Get the orbit response matrix ``R_ij`` of monitor measurements ``i``
        as a function of knob ``j``.

        The matrix rows are arranged as consecutive pairs of x/y values for
        each monitors, i.e.:

            x_0, y_0, x_1, y_1, …
        """
        return np.vstack([
            self._get_knob_response(knob)
            for knob in self.knobs
        ]).T

    def _get_knob_response(self, knob):
        """Calculate column ``R_j`` of the orbit response matrix corresponding
        to the knob ``j`` (specified by name) by performing a second twiss pass
        with a slightly varied knob value."""
        tw0 = self.base_tw
        with Param(knob, 2e-4, self.madx).vary(self) as step:
            tw1 = self.twiss('vary')
            idx = [mon.index for mon in self.monitors]
            return np.vstack((
                (tw1.x - tw0.x)[idx],
                (tw1.y - tw0.y)[idx],
            )).T.flatten() / step


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
    return X, reduced_chisq(A, X, Y, S)


def reduced_chisq(A, X, Y, S):
    residuals = (np.dot(A, X) - Y) / S
    return np.dot(residuals.T, residuals) / (len(residuals) - len(X))


def load_yaml(filename):
    """Load yaml document from filename."""
    with open(filename) as f:
        return yaml.safe_load(f)


class DataRecord:

    def __init__(self, sequence, strengths, records):
        self.sequence = sequence
        self.strengths = strengths
        self.records = records


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
    numerics = NumericalORM(model, monitors, steerers, knobs)
    numerics.set_operating_point()

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

    return monitors, steerers, base_orbit, measured_orm, numerics, stddev


def analyze(model, data_records, fit_args):

    monitors, steerers, base_orbit, measured_orm, numerics, stddev = get_orms(
        model, data_records, fit_args)

    errors = create_errors_from_spec(fit_args)
    for error in errors:
        error.set_base(numerics.madx)

    for i in range(fit_args.get('iterations', 1)):
        print("ITERATION", i)
        numerics.set_operating_point()

        results, chisq = fit_model(
            measured_orm, numerics.base_orm, numerics.get_orm_derivs(errors),
            monitor_errors=fit_args.get('monitor_errors'),
            steerer_errors=fit_args.get('steerer_errors'),
            stddev=stddev)
        print("ΔX     =", results.flatten())
        print("red χ² =", chisq)
        print("X_tot  =", np.array([
            err.base + delta
            for err, delta in zip(errors, results.flatten())
        ]))

        for param, value in zip(errors, results.flatten()):
            param.base += value
            param.apply(numerics.madx, param.base)
        print()
        print()
