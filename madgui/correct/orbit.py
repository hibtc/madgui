import numpy as np


class MonitorReadout:

    def __init__(self, el_name, values):
        self.name = el_name
        self.posx = values.get('posx')
        self.posy = values.get('posy')
        self.envx = values.get('envx')
        self.envy = values.get('envy')
        self.valid = (self.envx is not None and self.envx > 0 and
                      self.envy is not None and self.envy > 0 and
                      not np.isclose(self.posx, -9.999) and
                      not np.isclose(self.posy, -9.999))


def fit_initial_orbit(*records):
    """
    Compute initial beam position/momentum from multiple recorded monitor
    readouts + associated transfer maps.

    Call as follows:

        >>> fit_initial_orbit((T1, K1, Y1), (T2, K2, Y2), …)

    where

        T are the 4D/6D SECTORMAPs from start to the monitor.
        K are the 4D/6D KICKs of the map from the start to the monitor.
        Y are the 2D measurement vectors (x, y)

    This function solves the linear system:

            T1 X + K1 = Y1
            T2 X + K2 = Y2
            …

    for the 4D phase space vector X = (x, px, y, py).

    Returns:    [x,px,y,py],    chi_squared,    underdetermined
    """
    T_, K_, Y_ = zip(*records)
    T = np.vstack([T[[0,2]] for T in T_])[:,:4]
    K = np.hstack([K[[0,2]] for K in K_])
    Y = np.hstack(Y_)
    x, residuals, rank, singular = np.linalg.lstsq(T, Y-K, rcond=-1)
    return x, sum(residuals), (rank<len(x))
