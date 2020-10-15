"""
Contains functions to deduce initial particle coordinates from given
measurements.
"""

__all__ = [
    'Readout',
    'add_offsets',
    'fit_particle_readouts',
    'fit_particle_orbit',
    'fit_initial_orbit',
]

import numpy as np


class Readout:
    def __init__(self, name, posx, posy):
        self.name = name
        self.posx = posx
        self.posy = posy


def add_offsets(readouts, offsets):
    return [
        Readout(r.name, r.posx + dx, r.posy + dy)
        for r in readouts
        for dx, dy in [offsets.get(r.name.lower(), (0, 0))]
    ] if offsets else readouts


def fit_particle_readouts(model, readouts, to='#s'):
    index = model.elements.index
    readouts = [
        r if hasattr(r, 'name') else Readout(*r)
        for r in readouts
    ]
    readouts = sorted(readouts, key=lambda r: index(r.name))
    from_ = readouts[0].name
    return fit_particle_orbit(model, readouts, [
        model.sectormap(from_, r.name)
        for r in readouts
    ], to=to)


def fit_particle_orbit(model, records, secmaps, from_=None, to='#s'):

    (x, px, y, py), chi_squared, singular = fit_initial_orbit([
        (secmap[:, :6], secmap[:, 6], (record.posx, record.posy))
        for record, secmap in zip(records, secmaps)
    ])

    if from_ is None:
        from_ = records[0].name
    else:
        from_ = model.elements[from_].name

    data = model.track_one(x=x, px=px, y=y, py=py, range=(from_, to))
    orbit = {'x': data.x[-1], 'px': data.px[-1],
             'y': data.y[-1], 'py': data.py[-1]}

    return (orbit, chi_squared, singular), data


def fit_initial_orbit(records, rcond=1e-6):
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
    x, residuals, rank, singular = np.linalg.lstsq(T, Y-K, rcond=rcond)
    return x, sum(residuals), (rank < len(x))


def fit_particle_orbit_opticVar(readouts, optics, optic_elements,
                                model, monitor, targets):
    """
    Compute initial beam position/momentum from multiple recorded monitor
    readouts. The tracking goes just to the begining of the first optic
    element, expected to be a quadrupole.

      @param readouts Measured positions at one monitor
      @param optics structure containing the optics
                  (See procedure.py Corrector opticVariation)
      @param array containing the optic elements that were varied
      @param model is the MADX model
      @param monitor is the monitor at which it was measured
      @param targets are the elements in the beamline where we want to optimize

    Returns:    { (element, axis) : fit orbit }
    Element is the target element, axis x or y
    """
    initElem = optic_elements[0]
    x = [mi.readout.posx for mi in readouts]
    y = [mi.readout.posy for mi in readouts]

    records = []
    optN = len(optics)
    nReads = len(x)
    opti = 0

    for o in optics:
        model.write_params(o.items())
        tMap_i = model.sectormap(initElem, monitor[0])
        for i in range(int(nReads/optN)):
            count = int(opti*nReads/optN)
            records.append((tMap_i[:, :6], tMap_i[:, 6],
                            (x[i+count], y[i+count])))
        opti += 1

    xFit, chi_squared, singular = fit_initial_orbit(records)

    measuredT = []
    for o in optics:
        model.write_params(o.items())
        measuredT.append(
            {t.elem: [track.x[-1], track.y[-1]]
             for t in targets
             for track in
             [model.track_one(x=xFit[0], px=xFit[1],
                              y=xFit[2], py=xFit[3],
                              range='{}/{}'.format(initElem,
                                                   t.elem))]})

    measured = [
        {(t.elem.lower(), ax): val
         for t in targets
         for ax, val in zip('xy', (o[t.elem][0], o[t.elem][1]))}
        for o in measuredT
    ]
    return measured
