"""
Utilities for fitting objective functions.
"""

from itertools import count
from functools import partial

import numpy as np
import scipy.optimize as sciopt


def reduced_chisq(residuals, ddof=0):
    """Compute reduced chi-squared."""
    residuals = residuals.flatten()
    return np.dot(residuals.T, residuals) / (len(residuals) - ddof)


def fit_basinhopping(
        f, x0, y=0, sig=1, iterations=20, T=1.0, stepsize=0.01, **kwargs):
    """Global optimization of ``f(x) = y`` based on
    :func:`scipy.optimize.basinhopping`."""
    def minimize(f, x0, callback=None, **kwargs):
        return sciopt.basinhopping(
            f, x0, niter=iterations, T=T, stepsize=stepsize,
            minimizer_kwargs=kwargs, callback=callback)
    return _scipy_minimize(minimize, f, x0, y, sig, **kwargs)


def fit_diffevo(
        f, x0, y=0, sig=1, delta=1e-3, bounds=None,
        iterations=20, method='best1bin', **kwargs):
    """Global optimization of ``f(x) = y`` based on
    :func:`scipy.optimize.differential_evolution`."""
    if bounds is None:
        bounds = [(x - 10*delta, x + 10*delta) for x in x0]

    def minimize(f, x0, jac=None, **kwargs):
        return sciopt.differential_evolution(
            f, bounds, strategy=method, maxiter=iterations, **kwargs)
    return _scipy_minimize(minimize, f, x0, y, sig, **kwargs)


def fit_minimize(f, x0, y=0, sig=1, iterations=None, **kwargs):
    """Fit objective function ``f(x) = y`` using least-squares fit via
    ``scipy.optimize.minimize``."""
    def minimize(f, x0, **kwargs):
        options = {'maxiter': iterations}
        return sciopt.minimize(f, x0, options=options, **kwargs)
    return _scipy_minimize(minimize, f, x0, y, sig, **kwargs)


def _scipy_minimize(
        minimizer, f, x0, y=0, sig=1,
        delta=None, jac=None,
        callback=None, **kwargs):
    state = sciopt.OptimizeResult(
        x=x0, fun=None, chisq=None, nit=0,
        success=False, message="In progress.")

    def callback_wrapper(x, *_):
        state.nit += 1
        state.dx = x - state.x
        state.x = x
        state.fun = f(x)
        state.chisq = objective(state.fun)
        callback(state)

    def objective(y0):
        return reduced_chisq((y - y0) / sig)

    def obj_fun(x):
        return objective(f(x))

    if jac is None and delta is not None:
        jac = partial(jac_twopoint, obj_fun, delta=delta)

    result = minimizer(
        obj_fun, x0, jac=jac,
        callback=callback and callback_wrapper,
        **kwargs)
    result.fun = f(result.x)
    result.chisq = objective(result.fun)
    return result


def fit_lstsq(f, x0, y=0, sig=1, jac=None, tol=1e-8, delta=None,
              iterations=None, callback=None):
    """Fit objective function ``f(x) = y`` using a naive repeated linear
    least-squares fit."""
    dx = 0
    for nit in count():
        y0 = f(x0)
        if callback is not None:
            chisq = reduced_chisq((y - y0) / sig)
            callback(sciopt.OptimizeResult(
                x=x0, fun=y0, chisq=chisq, nit=nit, dx=dx,
                success=False, message="In progress."))
        if nit > 0 and np.allclose(dx, 0, atol=tol):
            message = "Reached convergence"
            success = True
            break
        if iterations is not None and nit > iterations:
            message = "Reached max number of iterations"
            success = False
            break
        dx, dy = fit_lstsq_oneshot(
            f, x0, y, sig, y0=y0, jac=jac, delta=delta, rcond=tol)
        x0 += dx
    chisq = reduced_chisq((y - y0) / sig)
    return sciopt.OptimizeResult(
        x=x0, fun=y0, chisq=chisq, nit=nit,
        success=success, message=message)


def fit_lstsq_oneshot(f, x0, y=0, sig=1, y0=None,
                      delta=None, jac=None, rcond=1e-8):
    """Single least squares fit for ``f(x) = y`` around ``x0``.
    Returns ``(Δx, Δy)``, where ``Δy`` is the linear hypothesis for how much
    ``y`` will change due to change in ``x``."""
    if y0 is None:
        y0 = f(x0)
    if jac is None:
        jac = partial(jac_twopoint, f, y0=y0, delta=delta)
    A = jac(x0)
    Y = y - y0
    S = np.broadcast_to(sig, Y.shape)
    n = Y.size
    A = A.reshape((-1, n)).T
    Y = Y.reshape((-1, 1))
    S = S.reshape((-1, 1))
    X = np.linalg.lstsq(A/S, Y/S, rcond=rcond)[0]
    return X.flatten(), np.dot(A, X).reshape(y0.shape)


def jac_twopoint(f, x0, y0=None, delta=1e-3):
    """Compute jacobian ``df/dx_i`` using two point-finite differencing."""
    if y0 is None:
        y0 = f(x0)
    return np.array([
        (f(x0 + dx) - y0) / np.linalg.norm(dx)
        for dx in np.eye(len(x0)) * delta
    ])


supported_optimizers = {
    'lstsq': fit_lstsq,
    'minimize': fit_minimize,
    'basinhopping': fit_basinhopping,
    'diffevo': fit_diffevo,
}


def fit(f, x0, y=0, sig=1, algorithm='minimize',
        **kwargs) -> sciopt.OptimizeResult:
    """Fit objective function ``f(x) = y``, start from ``x0``. Returns
    ``scipy.optimize.OptimizeResult``."""
    try:
        fun = supported_optimizers[algorithm]
    except KeyError:
        raise ValueError("Unknown optimizer: {!r}".format(algorithm))
    return fun(f, x0, y, sig, **kwargs)