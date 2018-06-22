import os
from math import sqrt, isnan
from collections import namedtuple
from itertools import accumulate
import logging

import numpy as np

from madgui.qt import Qt, QtGui, load_ui
from madgui.core.unit import ui_units
from madgui.util import yaml
from madgui.util.layout import VBoxLayout
from madgui.util.collections import List
from madgui.widget.tableview import ColumnInfo


class MonitorWidget(QtGui.QDialog):

    def __init__(self, control, model, frame):
        super().__init__(frame)
        self.tabs = QtGui.QTabWidget()
        self.tabs.addTab(PlotMonitorWidget(control, model, frame), "Plot")
        self.tabs.addTab(OrbitWidget(control, model, frame), "Orbit")
        self.tabs.addTab(EmittanceDialog(control, model, frame), "Optics")
        self.setLayout(VBoxLayout([self.tabs], tight=True))
        self.setSizeGripEnabled(True)


class MonitorItem:

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


ResultItem = namedtuple('ResultItem', ['name', 'fit', 'model'])


def get_monitor_name(cell):
    return cell.data.name

def get_monitor_show(cell):
    monitor, mgr = cell.data, cell.context
    return mgr.selected(monitor)

def set_monitor_show(cell, show):
    i, monitor, mgr = cell.row, cell.data, cell.context
    shown = mgr.selected(monitor)
    if show and not shown:
        mgr.select(i)
    elif not show and shown:
        mgr.deselect(i)


def get_monitor_valid(cell):
    return cell.data.valid


def get_monitor_textcolor(cell):
    return QtGui.QColor(Qt.black if cell.data.valid else Qt.darkGray)


class MonitorWidgetBase(QtGui.QWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    title = 'Set values in DVM from current sequence'
    headline = "Select for which monitors to plot measurements:"
    folder = None

    def __init__(self, control, model, frame):
        super().__init__(frame)
        load_ui(self, __package__, self.ui_file)

        self.control = control
        self.model = model
        self.frame = frame
        # TODO: we should eventually load this from model-specific session
        # file, but it's fine like this for now:
        self._shown = frame.config['online_control']['monitors']
        self._offsets = frame.config['online_control']['offsets']
        self._selected = self._shown.copy()

        self.mtab.set_columns(self.monitor_columns, context=self)
        self.mtab.header().setHighlightSections(False)
        self.mtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.mtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)

        Buttons = QtGui.QDialogButtonBox
        self.std_buttons.button(Buttons.Ok).clicked.connect(self.close)
        self.std_buttons.button(Buttons.Save).clicked.connect(self.export)
        self.btn_update.clicked.connect(self.update)

    def accept(self):
        self.window().accept()

    def selected(self, monitor):
        return self._selected.setdefault(monitor.name, monitor.valid)

    def select(self, index):
        self._selected[self.monitors[index].name] = True
        self.on_update()
        self.draw()

    def deselect(self, index):
        self._selected[self.monitors[index].name] = False
        self.on_update()
        self.draw()

    def update(self):
        self.mtab.rows = self.monitors = [
            MonitorItem(el.node_name, self.control.read_monitor(el.node_name))
            for el in self.model.elements
            if el.base_name.lower().endswith('monitor')
            or el.base_name.lower() == 'instrument']
        self.on_update()
        self.draw()

    def remove(self):
        self.frame.del_curve("monitors")

    def draw(self):

        # FIXME: Our way of adding ourselves to existing and to-be-opened
        # figures is tedious and error-prone. We should really rework the
        # plotting system to separate the artist from the scene element. We
        # could then simply register a generic artist to plot the content into
        # all potential scenes.

        for mon in self.monitors:
            mon.s = self.model.elements[mon.name].position
            dx, dy = self._offsets.get(mon.name.lower(), (0, 0))
            mon.x = (mon.posx + dx) if mon.posx is not None else None
            mon.y = (mon.posy + dy) if mon.posy is not None else None

        name = "monitors"

        data = {
            name: np.array([getattr(mon, name)
                            for mon in self.monitors
                            if self.selected(mon)
                            or self._shown.get(mon.name, mon.valid)])
            for name in ['s', 'envx', 'envy', 'x', 'y']
        }
        style = self.frame.config['line_view']['monitor_style']

        self.frame.add_curve(name, data, style)

    def export(self):
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self.window(), 'Export values', self.folder,
            self.exportFilters)
        if filename:
            self.export_to(filename)
            self.folder, _ = os.path.split(filename)


class PlotMonitorWidget(MonitorWidgetBase):

    ui_file = 'monitorwidget.ui'

    monitor_columns = [
        ColumnInfo("Monitor", get_monitor_name, checkable=True,
                   foreground=get_monitor_textcolor,
                   checked=get_monitor_show, setChecked=set_monitor_show),
        ColumnInfo("x", 'posx', convert=True, foreground=get_monitor_textcolor),
        ColumnInfo("y", 'posy', convert=True, foreground=get_monitor_textcolor),
        ColumnInfo("Δx", 'envx', convert=True, foreground=get_monitor_textcolor),
        ColumnInfo("Δy", 'envy', convert=True, foreground=get_monitor_textcolor),
    ]

    def __init__(self, control, model, frame):
        super().__init__(control, model, frame)
        self._selected = self._shown

    def showEvent(self, event):
        if not self.frame.graphs('envelope'):
            self.frame.open_graph('orbit')
        self.update()

    exportFilters = [
        ("YAML file", ".yml"),
        ("TEXT file (numpy compatible)", ".txt"),
    ]

    def on_update(self):
        pass

    def export_to(self, filename):
        ext = os.path.splitext(filename)[1].lower()

        # TODO: add '.tfs' output format?
        if ext == '.yml':
            data = {'monitor': {
                m.name: {'x': m.posx, 'y': m.posy,
                         'envx': m.envx, 'envy': m.envy }
                for m in self.mtab.rows
                if self.selected(m)
            }}
            with open(filename, 'wt') as f:
                yaml.safe_dump(data, f, default_flow_style=False)
            return
        elif ext == '.txt':
            def pos(m):
                return self.model.elements[m.name].position
            data = np.array([
                [pos(m), m.posx, m.posy, m.envx, m.envy]
                for m in self.mtab.rows
                if m.selected(m)
            ])
            np.savetxt(filename, data, header='s x y envx envy')
            return

        raise NotImplementedError(
            "Don't know how to serialize to {!r} format."
            .format(ext))


class _FitWidget(MonitorWidgetBase):

    ui_file = 'emittance.ui'

    result_columns = [
        ColumnInfo("Name", 'name', resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Model", 'model', convert='name'),
        ColumnInfo("Fit", 'fit', convert='name'),
        ColumnInfo("Unit", lambda cell: ui_units.label(cell.data.name),
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, control, model, frame):
        super().__init__(control, model, frame)
        self.btn_apply.clicked.connect(self.apply)
        #self.btn_offsets.clicked.connect(self.save_offsets)
        self.results = List()

        self.rtab.header().setHighlightSections(False)
        self.rtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.rtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.rtab.set_columns(self.result_columns, self.results, self)


class OrbitWidget(_FitWidget):

    monitor_columns = [
        ColumnInfo("Monitor", get_monitor_name, checkable=True,
                   foreground=get_monitor_textcolor,
                   checked=get_monitor_show, setChecked=set_monitor_show),
        ColumnInfo("x", 'posx', convert=True, foreground=get_monitor_textcolor),
        ColumnInfo("y", 'posy', convert=True, foreground=get_monitor_textcolor),
    ]

    def __init__(self, control, model, frame):
        super().__init__(control, model, frame)
        self.options_box.hide()

    def showEvent(self, event):
        self.frame.open_graph('orbit')
        self.update()

    def save_offsets(self):
        self.model.twiss()
        for m in self.monitors:
            tw = self.model.get_elem_twiss(m.name)
            if self.selected(m):
                self._offsets[m.name.lower()] = (
                    tw.x - m.posx,
                    tw.y - m.posy)

    exportFilters = [
        ("YAML file", ".yml"),
    ]

    def export_to(self, filename):
        pass

    def apply(self):
        if not self.singular:
            self.model.update_twiss_args(self.init_orbit)

    def on_update(self):
        self.init_orbit, chi_squared, self.singular = \
            self.fit_particle_orbit()
        if not self.singular:
            initial = self.model.twiss_args
            self.results[:] = [
                ResultItem(k, v, initial.get(k, 0))
                for k, v in self.init_orbit.items()
            ]

    def fit_particle_orbit(self):
        from madgui.correct.orbit import fit_initial_orbit

        records = [m for m in self.monitors if self.selected(m)]
        secmaps = self.model.get_transfer_maps([0] + [r.name for r in records])
        secmaps = list(accumulate(secmaps, lambda a, b: np.dot(b, a)))
        (x, px, y, py), chi_squared, singular = fit_initial_orbit(*[
            (secmap[:,:6], secmap[:,6], (record.posx+dx, record.posy+dy))
            for record, secmap in zip(records, secmaps)
            for dx, dy in [self._offsets.get(record.name.lower(), (0, 0))]
        ])
        return {
            'x': x, 'px': px,
            'y': y, 'py': py,
        }, chi_squared, singular


class EmittanceDialog(_FitWidget):

    monitor_columns = [
        ColumnInfo("Monitor", 'name', checkable=get_monitor_valid,
                   foreground=get_monitor_textcolor,
                   checked=get_monitor_show,
                   setChecked=set_monitor_show,
                   resize=QtGui.QHeaderView.Stretch),
        ColumnInfo("Δx", 'envx', convert=True, foreground=get_monitor_textcolor),
        ColumnInfo("Δy", 'envy', convert=True, foreground=get_monitor_textcolor),
    ]

    # The three steps of UI initialization

    def __init__(self, control, model, frame):
        super().__init__(control, model, frame)
        self.long_transfer.clicked.connect(self.match_values)
        self.use_dispersion.clicked.connect(self.match_values)
        self.respect_coupling.clicked.connect(self.match_values)

    def showEvent(self, event):
        self.frame.open_graph('envelope')
        self.update()

    def apply(self):
        results = {r.name: r.fit
                   for r in self.results
                   if not isnan(r.fit)}
        if results:
            model = self.model
            model.update_beam({
                'ex': results.pop('ex', model.ex()),
                'ey': results.pop('ey', model.ey()),
            })
            model.update_twiss_args(results)

    exportFilters = [
        ("YAML file", ".yml"),
    ]

    def export_to(self, filename):
        pass

    def on_update(self):
        self.match_values()

    def match_values(self):

        long_transfer = self.long_transfer.isChecked()
        use_dispersion = self.use_dispersion.isChecked()
        respect_coupling = self.respect_coupling.isChecked()

        min_monitors = 6 if use_dispersion else 3
        if len(self._selected) < min_monitors:
            self.results[:] = []
            return

        model = self.control.model()

        monitors = [m for m in self.monitors if self.selected(m)]
        monitors = sorted(monitors, key=lambda m: model.elements.index(m.name))

        tms = model.get_transfer_maps([0] + [m.name for m in monitors])
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

        envx = [m.envx for m in monitors]
        envy = [m.envy for m in monitors]
        xcs = [[(0, cx**2), (2, cy**2)]
               for cx, cy in zip(envx, envy)]

        # TODO: do we need to add dpt*D to sig11 in online control?

        def calc_sigma(tms, xcs, dispersive):
            if dispersive and not use_dispersion:
                logging.warn("Dispersive lattice!")
            if not use_dispersion:
                tms = tms[:,:-1,:-1]
            sigma, residuals, singular = solve_emit_sys(tms, xcs)
            return sigma

        # TODO: assert no dispersion / or use 6 monitors...
        if not respect_coupling:
            if coupled:
                logging.warn("Coupled lattice!")
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
        twiss_args = model.twiss_args

        results = []
        results += [
            ResultItem('ex',   ex,   beam.ex),
            ResultItem('ey',   ey,   beam.ey),
        ]
        results += [
            ResultItem('pt',   pt,   beam.et),
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
