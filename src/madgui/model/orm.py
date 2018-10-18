import itertools

import numpy as np
import yaml

from .errors import Param, Ealign, Efcomp


class _BaseORM:

    """Helper for ORM calculations."""

    def __init__(self, madx, sequ, twiss_args, monitors, steerers, knobs):
        self.madx = madx
        self.sequ = sequ = madx.sequence[sequ]
        self.elms = elms = sequ.expanded_elements
        self.monitors = [elms[el] for el in monitors]
        self.steerers = [elms[el] for el in steerers]
        self.knobs = knobs
        self.twiss_args = twiss_args
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

    def fit_model(self, measured_orm, params,
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
        Y = measured_orm - self.base_orm
        A = np.array([self.get_orm_deriv(param) for param in params])
        S = np.array(stddev)
        if steerer_errors:
            A = np.hstack((A, -self.base_orm))
        if monitor_errors:
            A = np.hstack((A, +self.base_orm))
        n = Y.size
        A = A.reshape((-1, n)).T
        Y = Y.reshape((-1, 1))
        S = S.reshape((-1, 1))
        X = np.linalg.lstsq(A/S, Y/S, rcond=rcond)[0]
        return X, reduced_chisq(A, X, Y, S)


class NumericalORM(_BaseORM):

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
        with Param(knob).vary(self) as step:
            tw1 = self.twiss('vary')
            idx = [mon.index for mon in self.monitors]

            x0 = np.vstack([tw0.x[idx], tw0.y[idx]]).T * 1e3
            x1 = np.vstack([tw1.x[idx], tw1.y[idx]]).T * 1e3
            print("COMPUTE", knob, self.madx.eval(knob))
            print("\n".join(
                "{:6} {}: {: .3f} {: .3f} -> {: .3f} {: .3f} | {: .3f} {: .3f}"
                .format(mon.name, knob, *np.hstack([a, b, b - a]))
                for a, b, mon in zip(x0, x1, self.monitors)
            ))

            return np.vstack((
                (tw1.x - tw0.x)[idx],
                (tw1.y - tw0.y)[idx],
            )).T.flatten() / step


class AnalyticalORM(_BaseORM):

    def get_orm(self) -> np.array:
        """Calculate the orbit response matrix ``R_ij`` of monitor
        measurements ``i`` as a function of knob ``j`` from the analytical
        formula. Altough this returns all combinations, only the uncoupled
        compenents x(hkick), y(vkick) are valid."""
        I = [elem.index for elem in self.steerers]
        J = [elem.index for elem in self.monitors]
        tw = self.base_tw
        rx = np.sqrt(tw.betx[I, None] * tw.betx[None, J] *
                     np.sin(2*np.pi*(tw.mux[None, J] - tw.mux[I, None])))
        ry = np.sqrt(tw.bety[I, None] * tw.bety[None, J] *
                     np.sin(2*np.pi*(tw.muy[None, J] - tw.muy[I, None])))
        # FIXME: this packing is inconsistent with the numerical case…
        return np.hstack((rx, ry)).T


def reduced_chisq(A, X, Y, S):
    residuals = (np.dot(A, X) - Y) / S
    return np.dot(residuals.T, residuals) / (len(residuals) - len(X))


def load_yaml(filename):
    """Load yaml document from filename."""
    with open(filename) as f:
        return yaml.safe_load(f)


class ResponseMatrix:

    def __init__(self, sequence, strengths,
                 monitors, steerers, knobs,
                 responses):
        self.sequence = sequence
        self.strengths = strengths
        self.monitors = monitors
        self.steerers = steerers
        self.knobs = knobs
        self.responses = responses


def load_record_file(filename):
    data = load_yaml(filename)
    sequence = data['sequence']
    strengths = data['model']
    monitors = data['monitors']
    steerers = data['steerers']
    knobs = dict(zip(steerers, data['knobs']))
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
    print("MEASURED")
    print("\n".join(
        "{:6} {}: {: .3f} {: .3f} -> {: .3f} {: .3f}"
        " | {: .3f} {: .3f} ± {: .3f} {: .3f}"
        .format(monitor, knob, *np.hstack([
            base, orbit, orbit-base, np.sqrt(error+_err)])*1e3)
        for (monitor, knob), (strength, orbit, error) in records.items()
        if knob
        for _, base, _err in [records[monitor, None]]
    ))
    return ResponseMatrix(sequence, strengths, monitors, steerers, knobs, {
        (monitor, knob): (
            (orbit - base), (strength - strengths[knob]), (error + _err))
        for (monitor, knob), (strength, orbit, error) in records.items()
        if knob
        for _, base, _err in [records[monitor, None]]
    })


def groupby(data, key=None):
    return [
        (k, list(g))
        for k, g in itertools.groupby(sorted(data, key=key), key=key)
    ]


def join_record_files(orbit_responses):
    mats = iter(orbit_responses)
    acc = next(mats)
    acc.monitors = set(acc.monitors)
    acc.steerers = set(acc.steerers)
    acc.knobs = acc.knobs.copy()
    for mat in mats:
        assert acc.sequence == mat.sequence
        assert acc.strengths == mat.strengths
        acc.responses.update(mat.responses)
        acc.monitors.update(mat.monitors)
        acc.steerers.update(mat.steerers)
        acc.knobs.update(mat.knobs)
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


def analyze(madx, twiss_args, measured, fit_args):
    madx.globals.update(measured.strengths)
    elems = madx.sequence[measured.sequence].expanded_elements
    monitors = sorted(measured.monitors, key=elems.index)
    steerers = sorted(measured.steerers, key=elems.index)
    knobs = [measured.knobs[elem] for elem in steerers]
    numerics = NumericalORM(
        madx, measured.sequence, twiss_args,
        monitors=monitors, steerers=steerers,
        knobs=knobs)
    numerics.set_operating_point()
    measured_orm = np.vstack([
        np.hstack([
            delta_orbit / delta_param
            for monitor in monitors
            for delta_orbit, delta_param, _ in [
                    measured.responses.get((monitor, knob))]
        ])
        for knob in knobs
    ]).T
    stddev = np.vstack([
        np.hstack([
            np.sqrt(mean_error) / delta_param
            for monitor in monitors
            for _, delta_param, mean_error in [
                    measured.responses.get((monitor, knob))]
        ])
        for knob in knobs
    ]).T if fit_args.get('stddev', False) else 1

    errors = create_errors_from_spec(fit_args)

    # NOTE: multiple iterations don't work with `Ealign` or # `Efcomp`!
    # (because they always set the full error currently)
    for i in range(fit_args.get('iterations', 1)):
        print("ITERATION", i)
        numerics.set_operating_point()

        results, chisq = numerics.fit_model(
            measured_orm, errors,
            monitor_errors=fit_args.get('monitor_errors'),
            steerer_errors=fit_args.get('steerer_errors'),
            stddev=stddev)
        print("ΔX     =", results)
        print("red χ² =", chisq)

        for param, value in zip(errors, results.flatten()):
            param.apply(numerics.madx, value)
        print()
        print()
