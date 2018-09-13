
from contextlib import contextmanager

import numpy as np


class Param:

    """Variable parameter."""

    def __init__(self, knob, step=1e-4):
        self.knob = knob
        self.step = step

    @contextmanager
    def vary(self, model):
        knob = self.knob
        step = self.step
        madx = model.madx
        madx.globals[knob] += step
        try:
            yield step
        except:
            raise
        else:
            madx.globals[knob] -= step


class _BaseORM:

    """Helper for ORM calculations."""

    def __init__(self, madx, sequ, twiss_args, monitors, steerers, knobs):
        self.madx = madx
        self.sequ = sequ = madx.sequence[sequ]
        self.elms = elms = sequ.elements
        self.monitors = [elms[el] for el in monitors]
        self.steerers = [elms[el] for el in steerers]
        self.knobs = knobs
        self.twiss_args = twiss_args
        self.base_tw = None
        self.base_orm = None

    def set_base(self, table='base'):
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
            self.set_base('base_deriv')
            try:
                return (self.get_orm() - self.backup_orm) / step
            finally:
                self.base_tw = backup_tw
                self.base_orm = backup_orm

    def fit_model(self, measured_orm, params, rcond=1e-8):
        """
        Fit model to the measured ORM via the given params
        (:class:`Param`). Return the best-fit solutions X for the parameters
        and the squared sum of residuals.

        ``measured_orm`` must be a numpy array with the same
        layout as returned our ``get_orm``.
        """
        Y = measured_orm - self.base_orm
        A = [self.get_orm_deriv(param) for param in params]
        X = np.linalg.lstsq(A, Y, rcond=rcond)[0]
        return X, chisq(A, X, Y)


class NumericalORM(_BaseORM):

    def get_orm(self) -> np.array:
        """Get the orbit response matrix ``R_ij`` of monitors ``j`` as a
        function of knob ``i``."""
        return np.vstack([
            self.calc(self, knob)
            for knob in self.knobs
        ])

    def _get_orm_row(self, knob):
        """Calculate row ``R_i`` of the orbit response matrix corresponding to
        the knob ``i`` (specified by name) by performing a second twiss pass
        with a slightly varied parameter."""
        tw0 = self.base_tw
        with Param(knob) as step:
            tw1 = self.twiss('vary')
            idx = [mon.index for mon in self.monitors]
            return np.vstack((
                (tw1.x-tw0.x),
                (tw1.y-tw0.y),
            )).T[idx] / step


class AnalyticalORM(_BaseORM):

    def get_orm(self) -> np.array:
        """Calculate the orbit response matrix ``R_ij`` of monitors ``j`` as a
        function of knob ``i`` from  the analytical formula. Altough this
        returns all combinations, only the uncoupled compenents x(hkick),
        y(vkick) are valid."""
        I = [elem.index for elem in self.steerers]
        J = [elem.index for elem in self.monitors]
        tw = self.base_tw
        rx = np.sqrt(tw.betx[I,None] * tw.betx[None,J] *
                     np.sin(2*np.pi*(tw.mux[None,J] - tw.mux[I,None])))
        ry = np.sqrt(tw.bety[I,None] * tw.bety[None,J] *
                     np.sin(2*np.pi*(tw.muy[None,J] - tw.muy[I,None])))
        # FIXME: this packing is inconsistent with the numerical case…
        return np.hstack((rx, ry))


def chisq(A, X, Y):
    residuals = np.dot(A, X) - Y
    return np.dot(residuals, residuals)
