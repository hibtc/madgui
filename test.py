
from math import sqrt, sin, pi

from cpymad.madx import Madx


def ORM_sin(tw, i, j):
    return (sqrt(tw.betx[i]*tw.betx[j]) * sin(2*pi*(tw.mux[j]-tw.mux[i])),
            sqrt(tw.bety[i]*tw.bety[j]) * sin(2*pi*(tw.muy[j]-tw.muy[i])))

def ORM_vary(delta_x, delta_theta):
    return delta_x / delta_theta


def main():

    # load gantry model
    m = Madx(stdout=False)
    m.call('../../hit_models/hht3/run.madx', True)
    seq = m.sequence.hht3
    els = seq.elements
    d_kick = 0.1e-3

    # define elements
    H = els.index('h1ms2h')
    V = els.index('h1ms1v')
    M = [
        el.index
        for el in els
        if el.index > max(H, V)
        and el.base_name == 'monitor'
    ]

    # run model in design configuration
    tw = dict(betx=1, bety=1, x=0.0001, y=0.0005)
    t0 = m.twiss(sequence='hht3', table='t0', **tw)

    # vary horizontal kicker
    els[H].kick += d_kick
    t1 = m.twiss(sequence='hht3', table='t1', **tw)
    els[H].kick -= d_kick

    # vary vertical kicker
    els[V].kick += d_kick
    t2 = m.twiss(sequence='hht3', table='t2', **tw)
    els[V].kick -= d_kick


    # analysis

    def orms(m):
        return (
            ORM_sin(t0, H, m)[0],
            ORM_sin(t0, V, m)[1],
            ORM_vary(t1.x[m]-t0.x[m], d_kick),
            ORM_vary(t2.y[m]-t0.y[m], d_kick),
        )

    orm_tab = [orms(m) for m in M]


    import numpy as np
    import matplotlib.pyplot as plt

    orm_tab = np.array(orm_tab)
    xlabel = [els[m].name for m in M]

    plt.plot(xlabel, orm_tab[:,0], label="sin x")
    plt.plot(xlabel, orm_tab[:,1], label="sin y")
    plt.plot(xlabel, orm_tab[:,2], label="var x")
    plt.plot(xlabel, orm_tab[:,3], label="var y")
    plt.legend()
    plt.setp(plt.xticks()[1], rotation=50)
    plt.show()


if __name__ == '__main__':
    main()
