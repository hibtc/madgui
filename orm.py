
from contextlib import contextmanager

import numpy as np


class Param:

    def __init__(self, para, step=1e-4):
        self.para = para
        self.step = step

    @contextmanager
    def vary(self, model):
        para = self.para
        step = self.step
        madx = model.madx
        madx.globals[para] += step
        try:
            yield step
        except:
            raise
        else:
            madx.globals[para] -= step


class Model:

    def __init__(self, madx, sequ, calc_orm_coefs, steerers, monitors=None):
        self.madx = madx
        self.calc = calc_orm_coefs
        self.sequ = sequ = madx.sequence[sequ]
        self.elms = elms = sequ.elements
        self.steerers = [elms[el] for el in steerers]
        self.monitors = [elms[el] for el in monitors]
        self.base_orm = None
        self.base_twiss = None
        self.init_twiss = init_twiss

    def set_base(self):
        """Set the base model, and calculate the model ORM. Must be called
        before other methods."""
        self.base_twiss = self.twiss('base')
        self.base_orm = self.get_orm()

    def twiss(self, table):
        return self.madx.twiss(table=self.table, **self.init_twiss)

    def get_orm(self):
        return np.vstack([
            self.get_orm_row(r)
            for r in self.steerers
        ])

    def get_orm_deriv(self, param):
        return np.vstack([
            self.get_orm_row_deriv(r)
            for r in self.steerers
        ])

    def get_orm_row(self, steerer):
        return self.calc(self, steerer)

    def get_orm_row_deriv(self, steerer, param):
        with param.vary(self) as step:
            base_backup = self.base_twiss
            self.base_twiss = self.twiss('base2')
            try:
                return (self.get_orm() - self.base_orm) / step
            finally:
                self.base_twiss = base_backup

    def fit_params(self, lin_fit, params, measured):
        model = self.base_orm
        Y = (measured - model)
        A = [self.get_orm_deriv(param) for param in params]
        X = lin_fit(A, Y)
        return X, chisq(A, X, Y)


def lin_fit_svd(A, Y, eps_cutoff=1e-8):
    B = np.dot(A.T, A)
    U, S, V = np.linalg.svd(B)
    S_pseudo_inverse = np.diag([1/c if c >= eps_cutoff else 0 for c in S])
    B_pseudo_inverse = V.dot(S_pseudo_inverse).dot(U.T)
    return B_pseudo_inverse.dot(A).dot(Y)

    N = S >= eps_cutoff
    S = S[N]
    U = U[...,None]

    B_pseudo_inverse = V[:,N,:].dot(S[N]).dot(U[:,N,:].T)
    return B_pseudo_inverse.dot(A).dot(Y)




def lin_fit_lsq(A, Y, rcond=1e-8):
    return np.linalg.lstsq(A, Y, rcond=rcond)[0]


def chisq(A, X, Y):
    residuals = np.dot(A, X) - Y
    return np.dot(residuals, residuals)


def calc_orm_numerical(model, elem):
    """Calculate orbit response matrix from a second twiss pass with varied
    parameter."""
    tw0 = model.base_twiss
    with Param(elem.kick) as step:
        tw1 = model.twiss('vary')
        idx = [mon.index for mon in model.monitors]
        return np.vstack((
            (tw1.x-tw0.x),
            (tw1.y-tw0.y),
        )).T[idx] / step


def calc_orm_analytical(model, elem):
    """Calculate orbit response matrix from the analytical formula. Altough
    this returns all combinations, only the uncoupled compenents x(hkick),
    y(vkick) are valid."""
    # TODO: we could return the full matrix with a single np broadcast
    # np.sqrt( betx[I] * betx[J] * np.sin(2*pi*(mux[J]-mux[I])) )
    tw = model.base_twiss
    return np.array([
        [sqrt(tw.betx[i]*tw.betx[j]) * sin(2*pi*(tw.mux[j]-tw.mux[i])),
         sqrt(tw.bety[i]*tw.bety[j]) * sin(2*pi*(tw.muy[j]-tw.muy[i]))]
        for m in model.monitors
        for j in [m.index]
    ])
