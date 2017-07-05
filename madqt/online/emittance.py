# encoding: utf-8
"""
UI for matching.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from pkg_resources import resource_filename
from collections import namedtuple
from math import sqrt

import numpy as np

from madqt.qt import QtGui, uic
from madqt.widget.tableview import ColumnInfo, ExtColumnInfo

import madqt.online.elements as elements
from madqt.util.collections import List
from madqt.util.enum import make_enum


MonitorItem = namedtuple('MonitorItem', ['proxy', 'envx', 'envy'])
ResultItem = namedtuple('ResultItem', ['name', 'measured', 'model'])


def get_monitor_elem(widget, m):
    return widget.monitor_enum(m.proxy.name)

def set_monitor_elem(widget, m, i, name):
    if name is not None:
        p = widget.monitor_map[str(name)]
        v = p.dvm_backend.get()
        widget.cached_tms = None
        widget.monitors[i] = MonitorItem(p, v.get('widthx'), v.get('widthy'))


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
        super(EmittanceDialog, self).__init__()
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.control = control

        monitors = list(control.iter_elements(elements.Monitor))
        self.monitor_map = {m.name: m for m in monitors}
        self.monitor_enum = make_enum('Monitor', [m.name for m in monitors])
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
        self.mtab.selectionChangedSignal.connect(self.selection_changed_monitor)
        self.monitors.update_after.connect(self.on_monitor_changed)
        # TODO: update UI: ok/export buttons
        # monitor actions
        self.button_remove_monitor.clicked.connect(self.mtab.removeSelectedRows)
        self.button_clear_monitor.clicked.connect(self.monitors.clear)
        self.button_add_monitor.clicked.connect(self.add_monitor)
        self.button_update_monitor.clicked.connect(self.update_monitor)
        # result actions
        self.button_ok.clicked.connect(self.accept)
        self.button_cancel.clicked.connect(self.reject)
        self.button_export.clicked.connect(self.export)
        self.check_matchstart.clicked.connect(self.match_values)

    def selection_changed_monitor(self):
        self.button_remove_monitor.setEnabled(bool(self.mtab.selectedIndexes()))

    def on_monitor_changed(self):
        self.button_clear_monitor.setEnabled(bool(self.monitors))
        self.button_update_monitor.setEnabled(bool(self.monitors))
        self.match_values()

    def export(self):
        pass

    def add_monitor(self):
        self.cached_tms = None
        used = {m.proxy.name for m in self.monitors}
        name = choose_after(self.monitor_enum._values, used)
        prox = self.monitor_map[name]
        vals = prox.dvm_backend.get()
        self.monitors.append(MonitorItem(
            prox, vals.get('widthx'), vals.get('widthy')))

    def update_monitor(self):
        # reload values for all the monitors
        self.monitors[:] = [
            MonitorItem(m.proxy, v.get('widthx'), v.get('widthy'))
            for m in self.monitors
            for v in [m.proxy.dvm_backend.get()]
        ]

    def match_values(self):

        if len(self.monitors) < 3:
            self.results[:] = []
            return

        seg = self.control._segment
        strip = seg.utool.strip_unit

        monitors = sorted(
            self.monitors, key=lambda m: seg.elements.index(m.proxy.name))

        # second case can happen when `removing` a monitor
        if self.cached_tms is None or len(self.cached_tms) != len(monitors):
            self.cached_tms = seg.get_transfer_maps([m.proxy.name for m in monitors])

        tms = list(self.cached_tms)
        if not self.check_matchstart.isChecked():
            tms[0] = np.eye(7)
        tms = list(accumulate(tms, lambda a, b: np.dot(b, a)))

        # TODO: button for "resync model"

        # TODO: when 'interpolate' is on -> choose correct element...?
        # -> not important for l=0 monitors

        envx = [strip('envx', m.envx) for m in monitors]
        envy = [strip('envy', m.envy) for m in monitors]

        decoupled = all(np.allclose(tm[0:2,2:4], 0) and
                        np.allclose(tm[2:4,0:2], 0)
                        for tm in tms)

        # TODO: assert no dispersion / or use 6 monitors...
        if decoupled:
            tmx = [tm[0:2,0:2] for tm in tms]
            tmy = [tm[2:4,2:4] for tm in tms]
            ex, betx, alfx = self.calc_emit_one_plane(tmx, envx)
            ey, bety, alfy = self.calc_emit_one_plane(tmy, envy)

        else:
            print("Warning: coupled")
            tms = [tm[0:4,0:4] for tm in tms]
            xcs = [[(0, cx**2), (2, cy**2)]
                   for cx, cy in zip(envx, envy)]
            sigma, residuals, singular = solve_emit_sys(tms, xcs)
            ex, betx, alfx = twiss_from_sigma(sigma[0:2,0:2])
            ey, bety, alfy = twiss_from_sigma(sigma[2:4,2:4])

        beam = seg.sequence.beam
        twiss_args = seg.utool.dict_strip_unit(seg.twiss_args)

        results = [
            ResultItem('betx', betx, twiss_args.get('betx')),
            ResultItem('bety', bety, twiss_args.get('bety')),
            ResultItem('alfx', alfx, twiss_args.get('alfx')),
            ResultItem('alfy', alfy, twiss_args.get('alfy')),
        ] if self.check_matchstart.isChecked() else []

        self.results[:] = [
            ResultItem('ex',   ex,   beam['ex']),
            ResultItem('ey',   ey,   beam['ey']),
        ] + results

    def calc_emit_one_plane(self, transfer_matrices, constraints):
        xcs = [[(0, c**2)] for c in constraints]
        sigma, residuals, singular = solve_emit_sys(transfer_matrices, xcs)
        return twiss_from_sigma(sigma)


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
    dim = Ms[0].shape[0]
    # construct linear system of equations
    T = np.vstack([
        ([M[x,i]**2          for i in range(dim)] +       # diagonal elements
         [2*M[x,i-1]*M[x,i]  for i in range(1, dim, 2)])  # off-diag elements
        for M, xc in zip(Ms, XCs)
        for x, _ in xc
    ])
    X = np.array([v for xc in XCs for _, v in xc])
    x0, residuals, rank, singular = np.linalg.lstsq(T, X)
    # construct result matrix
    res = np.diag(x0[:dim])
    for k, x in enumerate(x0[dim:]):
        i, j = 2*k, 2*k+1
        res[i,j] = res[j,i] = x
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
