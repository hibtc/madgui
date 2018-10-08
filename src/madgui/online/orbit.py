import numpy as np


def fit_particle_orbit(model, offsets, records, secmaps, range_start=None):

    (x, px, y, py), chi_squared, singular = fit_initial_orbit([
        (secmap[:, :6], secmap[:, 6], (record.posx+dx, record.posy+dy))
        for record, secmap in zip(records, secmaps)
        for dx, dy in [offsets.get(record.name.lower(), (0, 0))]
    ])

    if range_start is None:
        range_start = records[0].name
    else:
        range_start = model.elements[range_start].name

    backtw = model.backtrack(
        range=range_start+'_reflected'+'/#e',
        x=-x, y=y, px=px, py=-py,
        # We care only about the orbit:
        betx=1, bety=1, table="backtrack")

    data = {'s': backtw.s[-1] - backtw.s,
            'x': -backtw.x,
            'y': backtw.y}

    tw0 = backtw[-1]
    x, y, px, py = tw0.x, tw0.y, tw0.px, tw0.py

    init_tw = {
        'x': -x, 'px': px,
        'y': y, 'py': -py,
    }, chi_squared, singular

    return init_tw, data


def fit_initial_orbit(records):
    """
    Compute initial beam position/momentum from multiple recorded monitor
    readouts + associated transfer maps.

    Call as follows:

        >>> fit_initial_orbit([(T1, K1, Y1), (T2, K2, Y2), …])

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
    T = np.vstack([T[[0, 2]] for T in T_])[:, :4]
    K = np.hstack([K[[0, 2]] for K in K_])
    Y = np.hstack(Y_)
    x, residuals, rank, singular = np.linalg.lstsq(T, Y-K, rcond=1e-6)
    return x, sum(residuals), (rank < len(x))
