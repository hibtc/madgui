"""
UI for matching.
"""

from pkg_resources import resource_filename
from collections import namedtuple
from math import sqrt

import numpy as np

from madgui.qt import QtGui, uic
from madgui.widget.tableview import ColumnInfo, ExtColumnInfo

from madgui.util.collections import List
from madgui.util.enum import make_enum


MonitorItem = namedtuple('MonitorItem', ['name', 'envx', 'envy'])
ResultItem = namedtuple('ResultItem', ['name', 'measured', 'model'])


def get_monitor_elem(widget, m, i):
    return widget.monitor_enum(m.name)

def set_monitor_elem(widget, m, i, name):
    if name is not None:
        n = str(name)
        v = widget.control.read_monitor(n)
        widget.cached_tms = None
        widget.monitors[i] = MonitorItem(n, v.get('envx'), v.get('envy'))


def accumulate(iterable, func):
    """Return running totals."""
    # Stolen from:
    # https://docs.python.org/3/library/itertools.html#itertools.accumulate
    it = iter(iterable)
    total = next(it)
    yield total
    for element in it:
        total = func(total, element)
        yield total


def choose_after(available, enabled):
    indices = map(available.index, enabled)
    last = max(list(indices) or [-1])
    return next(v for v in available[last+1::-1] if v not in enabled)


class EmittanceDialog(QtGui.QDialog):

    ui_file = 'emittance.ui'

    monitor_columns = [
        ExtColumnInfo("Monitor", get_monitor_elem, set_monitor_elem,
                      resize=QtGui.QHeaderView.Stretch),
        ExtColumnInfo("Δx", 'envx'),
        ExtColumnInfo("Δy", 'envy'),
    ]

    result_columns = [
        ColumnInfo("Name", 'name', resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Measured", 'measured'),
        ColumnInfo("Model", 'model'),
    ]

    def __init__(self, control):
        super().__init__(control._frame)
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.control = control

        self.monitor_list = [el.Name
                             for el in control._model.elements
                             if el.Type.lower().endswith('monitor')
                             or el.Type.lower() == 'instrument']
        self.monitor_enum = make_enum('Monitor', self.monitor_list)
        self.monitors = List()
        self.results = List()

        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    # The three steps of UI initialization

    def init_controls(self):
        self.mtab.horizontalHeader().setHighlightSections(False)
        self.rtab.horizontalHeader().setHighlightSections(False)
        self.mtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.rtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.mtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.rtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.mtab.set_columns(self.monitor_columns, self.monitors, self)
        self.rtab.set_columns(self.result_columns, self.results, self)

    def set_initial_values(self):
        pass

    def connect_signals(self):
        # update UI
        self.mtab.connectButtons(self.button_remove_monitor, self.button_clear_monitor)
        self.monitors.update_after.connect(self.on_monitor_changed)
        # TODO: update UI: ok/export buttons
        # monitor actions
        self.button_add_monitor.clicked.connect(self.add_monitor)
        self.button_update_monitor.clicked.connect(self.update_monitor)
        # result actions
        self.button_ok.clicked.connect(self.accept)
        self.button_cancel.clicked.connect(self.reject)
        self.button_export.clicked.connect(self.export)
        self.long_transfer.clicked.connect(self.match_values)
        self.use_dispersion.clicked.connect(self.match_values)
        self.respect_coupling.clicked.connect(self.match_values)

    def on_monitor_changed(self):
        self.button_update_monitor.setEnabled(bool(self.monitors))
        self.match_values()

    def export(self):
        pass

    def add_monitor(self):
        self.cached_tms = None
        used = {m.name for m in self.monitors}
        name = choose_after(self.monitor_enum._values, used)
        vals = self.control.read_monitor(name)
        self.monitors.append(MonitorItem(
            name, vals.get('envx'), vals.get('envy')))

    def update_monitor(self):
        # reload values for all the monitors
        self.monitors[:] = [
            MonitorItem(m.name, v.get('envx'), v.get('envy'))
            for m in self.monitors
            for v in [self.control.read_monitor(m.name)]
        ]

    def match_values(self):

        long_transfer = self.long_transfer.isChecked()
        use_dispersion = self.use_dispersion.isChecked()
        respect_coupling = self.respect_coupling.isChecked()

        min_monitors = 6 if use_dispersion else 3
        if len(self.monitors) < min_monitors:
            self.results[:] = []
            return

        model = self.control._model
        strip = model.utool.strip_unit

        monitors = sorted(
            self.monitors, key=lambda m: model.elements.index(m.name))

        # second case can happen when `removing` a monitor
        if self.cached_tms is None or len(self.cached_tms) != len(monitors):
            self.cached_tms = model.get_transfer_maps([m.name for m in monitors])

        tms = list(self.cached_tms)
        if not long_transfer:
            tms[0] = np.eye(7)
        tms = list(accumulate(tms, lambda a, b: np.dot(b, a)))
        # keep X,PX,Y,PY,PT:
        tms = np.array(tms)[:,[0,1,2,3,5],:][:,:,[0,1,2,3,5]]

        # TODO: button for "resync model"

        # TODO: when 'interpolate' is on -> choose correct element...?
        # -> not important for l=0 monitors

        coup_xy = not np.allclose(tms[:,0:2,2:4], 0)
        coup_yx = not np.allclose(tms[:,2:4,0:2], 0)
        coup_xt = not np.allclose(tms[:,0:2,4:5], 0)
        coup_yt = not np.allclose(tms[:,2:4,4:5], 0)

        coupled = coup_xy or coup_yx
        dispersive = coup_xt or coup_yt

        envx = [strip('envx', m.envx) for m in monitors]
        envy = [strip('envy', m.envy) for m in monitors]
        xcs = [[(0, cx**2), (2, cy**2)]
               for cx, cy in zip(envx, envy)]

        # TODO: do we need to add dpt*D to sig11 in online control?

        def calc_sigma(tms, xcs, dispersive):
            if dispersive and not use_dispersion:
                print("Warning: dispersive lattice")
            if not use_dispersion:
                tms = tms[:,:-1,:-1]
            sigma, residuals, singular = solve_emit_sys(tms, xcs)
            return sigma

        # TODO: assert no dispersion / or use 6 monitors...
        if not respect_coupling:
            if coupled:
                print("Warning: coupled lattice")
            tmx = np.delete(np.delete(tms, [2,3], axis=1), [2,3], axis=2)
            tmy = np.delete(np.delete(tms, [0,1], axis=1), [0,1], axis=2)
            xcx = [[(0, cx[1])] for cx, cy in xcs]
            xcy = [[(0, cy[1])] for cx, cy in xcs]
            sigmax = calc_sigma(tmx, xcx, coup_xt)
            sigmay = calc_sigma(tmy, xcy, coup_yt)
            ex, betx, alfx = twiss_from_sigma(sigmax[0:2,0:2])
            ey, bety, alfy = twiss_from_sigma(sigmay[0:2,0:2])
            pt = sigmax[-1,-1]

        else:
            sigma = calc_sigma(tms, xcs, dispersive)
            ex, betx, alfx = twiss_from_sigma(sigma[0:2,0:2])
            ey, bety, alfy = twiss_from_sigma(sigma[2:4,2:4])
            pt = sigma[-1,-1]


        beam = model.sequence.beam
        twiss_args = model.utool.dict_strip_unit(model.twiss_args)

        results = []
        results += [
            ResultItem('ex',   ex,   beam['ex']),
            ResultItem('ey',   ey,   beam['ey']),
        ]
        results += [
            ResultItem('pt',   pt,   beam['et']),
        ] if use_dispersion else []
        results += [
            ResultItem('betx', betx, twiss_args.get('betx')),
            ResultItem('bety', bety, twiss_args.get('bety')),
            ResultItem('alfx', alfx, twiss_args.get('alfx')),
            ResultItem('alfy', alfy, twiss_args.get('alfy')),
        ] if long_transfer else []

        self.results[:] = results


def solve_emit_sys(Ms, XCs):
    """
    Solve for S the linear system of equations:

        (M S Mᵀ)ₓₓ = C

    For some M, x and C.

    M can be coupled, but S is assumed to be block diagonal, i.e. decoupled:

        S = (X 0 0
             0 Y 0
             0 0 T)

    Returns S as numpy array.
    """
    d = Ms[0].shape[0]

    con_func = lambda u: [
        M[[x]].dot(u).dot(M[[x]].T).sum()   # linear beam transport!
        for M, xc in zip(Ms, XCs)           # for every given transfer matrix
        for x, _ in xc                      # and measured constraint
    ]

    sq_matrix_basis = np.eye(d*d,d*d).reshape((d*d,d,d))
    is_upper_triang = [i for i, m in enumerate(sq_matrix_basis)
                       if np.allclose(np.triu(m), m)
                       and (d < 4 or np.allclose(m[0:2,2:4], 0))]

    lhs = np.vstack([
        con_func(2*u-np.tril(u))
        for u in sq_matrix_basis[is_upper_triang]
    ]).T
    rhs = [c for xc in XCs for _, c in xc]

    x0, residuals, rank, singular = np.linalg.lstsq(lhs, rhs, rcond=-1)

    res = np.tensordot(x0, sq_matrix_basis[is_upper_triang], 1)
    res = res + res.T - np.tril(res)
    return res, sum(residuals), (rank<len(x0))


def twiss_from_sigma(sigma):
    """Compute 1D twiss parameters from 2x2 sigma matrix."""
    b = sigma[0,0]
    a = sigma[0,1]  # = sigma[1,0] !
    c = sigma[1,1]
    if b*c <= a*a:
        nan = float("nan")
        return nan, nan, nan
    emit = sqrt(b*c - a*a)
    beta = b/emit
    alfa = a/emit * (-1)
    return emit, beta, alfa
