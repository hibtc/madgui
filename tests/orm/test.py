
from math import sqrt, sin, pi
from itertools import accumulate

from cpymad.madx import Madx

import numpy as np
import matplotlib.pyplot as plt


def ORM_sin(tw, i, j):
    return (sqrt(tw.betx[i]*tw.betx[j]) * sin(2*pi*(tw.mux[j]-tw.mux[i])),
            sqrt(tw.bety[i]*tw.bety[j]) * sin(2*pi*(tw.muy[j]-tw.muy[i])))


def ORM_vary(delta_x, delta_theta):
    return delta_x / delta_theta


def calc_orms(m, H, V, M, d_kick):

    els = m.sequence.hht3.expanded_elements

    m.select(flag='sectormap', clear=True)
    m.select(flag='sectormap', range=els[H].name)
    m.select(flag='sectormap', range=els[V].name)
    for mon in M:
        m.select(flag='sectormap', range=els[mon].name)

    # run model in design configuration
    tw = dict(betx=1, bety=1, alfx=-1.0, alfy=3, x=0.001, y=-0.005)
    t0 = m.twiss(sequence='hht3', table='t0', sectormap=True, **tw)

    sm = m.sectortable()
    vm = np.array(list(accumulate(sm[2:], lambda a, b: np.dot(b, a))))
    hm = np.array([np.dot(x, sm[1]) for x in vm])

    # vary horizontal kicker
    els[H].kick += d_kick
    t1 = m.twiss(sequence='hht3', table='t1', **tw)
    els[H].kick -= d_kick

    # vary vertical kicker
    els[V].kick += d_kick
    t2 = m.twiss(sequence='hht3', table='t2', **tw)
    els[V].kick -= d_kick

    # analysis

    def orms(i, m):
        return (
            ORM_sin(t0, H, m)[0],
            ORM_sin(t0, V, m)[1],
            ORM_vary(t1.x[m]-t0.x[m], d_kick),
            ORM_vary(t2.y[m]-t0.y[m], d_kick),
            hm[i, 0, 1],
            vm[i, 2, 3],
        )

    return np.array([orms(i, m) for i, m in enumerate(M)])


def calc_orm_diff(op):
    pass


def main():

    np.set_printoptions(**{
        'precision': 5,
        'suppress': True,       # no scientific notation
        'linewidth': 120,
    })

    # load gantry model
    m = Madx(stdout=False)
    m.call('../hit_models/hht3/run.madx', True)
    d_kick = 0.1e-3

    # define elements
    els = m.sequence.hht3.expanded_elements
    H = els.index('h1ms2h')
    V = els.index('h1ms1v')
    M = [
        el.index
        for el in els
        if el.index > max(H, V)
        and el.base_name == 'monitor'
    ]

    orm_tab_1 = calc_orms(m, H, V, M, d_kick)

    m.globals.kl_b3qd12 += 1e-7
    orm_tab_2 = calc_orms(m, H, V, M, d_kick)
    m.globals.kl_b3qd12 -= 1e-7

    orm_tab = (orm_tab_2 - orm_tab_1) / 1e-7
    orm_tab = orm_tab_2

    xlabel = [els[m].name for m in M]

    plt.plot(xlabel, orm_tab[:, 0], 'o', label="sin x")
    plt.plot(xlabel, orm_tab[:, 2], label="var x")
    plt.plot(xlabel, orm_tab[:, 4], label="sec x")
    plt.legend()
    plt.setp(plt.xticks()[1], rotation=50)
    plt.show()

    plt.clf()
    plt.plot(xlabel, orm_tab[:, 1], 'o', label="sin y")
    plt.plot(xlabel, orm_tab[:, 3], label="var y")
    plt.plot(xlabel, orm_tab[:, 5], label="sec y")
    plt.legend()
    plt.setp(plt.xticks()[1], rotation=50)
    plt.show()


if __name__ == '__main__':
    main()
