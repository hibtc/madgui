import os
from math import sqrt, isnan
from collections import namedtuple
from itertools import accumulate
import logging

import numpy as np

from madgui.qt import Qt, QtGui, load_ui
from madgui.util.unit import ui_units
from madgui.util import yaml
from madgui.util.layout import VBoxLayout
from madgui.util.collections import List
from madgui.widget.tableview import TableItem

from madgui.online.orbit import fit_particle_orbit


class MonitorWidget(QtGui.QDialog):

    def __init__(self, session):
        super().__init__(session.window())
        self.tabs = QtGui.QTabWidget()
        self.tabs.addTab(PlotMonitorWidget(session), "Plot")
        self.tabs.addTab(OrbitWidget(session), "Orbit")
        self.tabs.addTab(EmittanceDialog(session), "Optics")
        self.tabs.addTab(OffsetsWidget(session), "Offsets")
        self.setLayout(VBoxLayout([self.tabs], tight=True))
        self.setSizeGripEnabled(True)


ResultItem = namedtuple('ResultItem', ['name', 'fit', 'model'])


def get_monitor_textcolor(mon):
    return QtGui.QColor(Qt.black if mon.valid else Qt.darkGray)


class MonitorWidgetBase(QtGui.QWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    title = 'Set values in DVM from current sequence'
    headline = "Select for which monitors to plot measurements:"
    folder = None

    def __init__(self, session):
        super().__init__(session.window())
        load_ui(self, __package__, self.ui_file)

        self.session = session
        self.control = session.control
        self.model = session.model()
        self.frame = session.window()
        self.monitors = self.control.monitors.as_list()
        # TODO: we should eventually load this from model-specific session
        # file, but it's fine like this for now:
        self._monconf = session.config['online_control']['monitors']
        self._offsets = session.config['online_control']['offsets']

        self.mtab.set_viewmodel(self.get_monitor_row, self.monitors, unit=True)
        self.mtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.mtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)

        Buttons = QtGui.QDialogButtonBox
        self.std_buttons.button(Buttons.Ok).clicked.connect(self.accept)
        self.std_buttons.button(Buttons.Save).clicked.connect(self.export)
        self.btn_update.clicked.connect(self.update)

    def accept(self):
        self.window().accept()

    def selected(self, monitor):
        return self._selected.setdefault(monitor.name, False)

    def num_selected(self):
        return sum(map(self.selected, self.monitors))

    def select(self, index):
        self._selected[self.monitors[index].name] = True
        self.on_update()
        self.draw()

    def deselect(self, index):
        self._selected[self.monitors[index].name] = False
        self.on_update()
        self.draw()

    def update(self):
        self.control.monitors.invalidate()
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

        shown = self._monconf['show']
        data = {
            name: np.array([getattr(mon, name)
                            for mon in self.monitors
                            if self.selected(mon)
                            or shown.get(mon.name)])
            for name in ['s', 'envx', 'envy', 'x', 'y']
        }
        style = self.session.config['line_view']['monitor_style']

        self.frame.add_curve(name, data, style)

    exportFilters = [
        ("YAML file", "*.yml"),
    ]

    def export(self):
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self.window(), 'Export values', self.folder,
            self.exportFilters)
        if filename:
            self.export_to(filename)
            self.folder, _ = os.path.split(filename)

    def set_monitor_show(self, i, mon, show):
        shown = self.selected(mon)
        if show and not shown:
            self.select(i)
        elif not show and shown:
            self.deselect(i)

    def get_monitor_row(self, i, m) -> ("Monitor", "x", "y", "Δx", "Δy"):
        fg = get_monitor_textcolor(m)
        return [
            TableItem(m.name, checkable=True, foreground=fg,
                      checked=self.selected(m),
                      set_checked=self.set_monitor_show),
            TableItem(m.posx, name='posx', foreground=fg),
            TableItem(m.posy, name='posy', foreground=fg),
            TableItem(m.envx, name='envx', foreground=fg),
            TableItem(m.envy, name='envy', foreground=fg),
        ]


class PlotMonitorWidget(MonitorWidgetBase):

    ui_file = 'monitorwidget.ui'

    def __init__(self, session):
        super().__init__(session)
        self._selected = self._monconf.setdefault('show', {})

    def showEvent(self, event):
        if not self.frame.graphs('envelope'):
            self.frame.open_graph('orbit')
        self.update()

    exportFilters = [
        ("YAML file", "*.yml"),
        ("TEXT file (numpy compatible)", "*.txt"),
    ]

    def on_update(self):
        pass

    def export_to(self, filename):
        ext = os.path.splitext(filename)[1].lower()

        # TODO: add '.tfs' output format?
        if ext == '.yml':
            data = {'monitor': {
                m.name: {'x': m.posx, 'y': m.posy,
                         'envx': m.envx, 'envy': m.envy}
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


class OffsetsWidget(MonitorWidgetBase):

    ui_file = 'offsetswidget.ui'

    def get_monitor_row(self, i, m) -> ("Monitor", "Δx", "Δy"):
        fg = get_monitor_textcolor(m)
        dx, dy = self._offsets.get(m.name.lower(), (0, 0))
        return [
            TableItem(m.name, checkable=True, foreground=fg,
                      checked=self.selected(m),
                      set_checked=self.set_monitor_show),
            TableItem(dx, name='posx', foreground=fg),
            TableItem(dy, name='posy', foreground=fg),
        ]

    def __init__(self, *args):
        super().__init__(*args)
        self.btn_offsets.clicked.connect(self.save_offsets)
        self.btn_calibrate.clicked.connect(self.calibrate_offsets)
        Buttons = QtGui.QDialogButtonBox
        self.std_buttons.button(Buttons.Open).clicked.connect(self.load)
        self.std_buttons.button(Buttons.Discard).clicked.connect(self.discard)
        self._selected = self._monconf.setdefault('backtrack', {})

    def showEvent(self, event):
        self.frame.open_graph('orbit')
        self.update()

    def on_update(self):
        pass

    def discard(self):
        self._offsets.clear()
        self.update()

    def load(self):
        from madgui.widget.filedialog import getOpenFileName
        filename = getOpenFileName(
            self.window(), 'Load offsets', self.folder,
            self.exportFilters)
        if filename:
            self.load_from(filename)

    def load_from(self, filename):
        with open(filename) as f:
            data = f.read()
        offsets = yaml.safe_load(data)['offsets']
        self._offsets.clear()
        self._offsets.update(offsets)
        self.update()

    def export_to(self, filename):
        data = yaml.safe_dump({
            'offsets': self._offsets,
        }, default_flow_style=False)
        with open(filename, 'wt') as f:
            f.write(data)

    def save_offsets(self):
        self.model.twiss()
        for m in self.monitors:
            tw = self.model.get_elem_twiss(m.name)
            if self.selected(m):
                self._offsets[m.name.lower()] = (
                    tw.x - m.posx,
                    tw.y - m.posy)
        self.update()

    def calibrate_offsets(self):
        from .offcal import OffsetCalibrationWidget
        from madgui.widget.dialog import Dialog
        widget = OffsetCalibrationWidget(self, [
            m.name for m in self.monitors if self.selected(m)])
        dialog = Dialog(self)
        dialog.setWidget(widget)
        dialog.setWindowTitle("Offset calibration")
        dialog.show()


class _FitWidget(MonitorWidgetBase):

    ui_file = 'emittance.ui'

    def get_result_row(self, i, r) -> ("Name", "Model", "Fit", "Unit"):
        return [
            TableItem(r.name),
            TableItem(r.model, name=r.name),
            TableItem(r.fit, name=r.name),
            TableItem(ui_units.label(r.name)),
        ]

    def __init__(self, session):
        super().__init__(session)
        self.btn_apply.clicked.connect(self.apply)
        self.results = List()

        self.rtab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.rtab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.rtab.set_viewmodel(self.get_result_row, self.results)


class OrbitWidget(_FitWidget):

    def __init__(self, session):
        super().__init__(session)
        self.options_box.hide()
        self.mtab.hideColumn(3)
        self.mtab.hideColumn(4)
        self._selected = self._monconf.setdefault('backtrack', {})

    def showEvent(self, event):
        self.frame.open_graph('orbit')
        self.update()

    def export_to(self, filename):
        data = yaml.safe_dump({
            'twiss': self.init_orbit,
        }, default_flow_style=False)
        with open(filename, 'wt') as f:
            f.write(data)

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
        if self.num_selected() < 2:
            return {}, 0, False
        records = [m for m in self.monitors if self.selected(m)]
        secmaps = self.model.get_transfer_maps([0] + [r.name for r in records])
        secmaps[0] = np.eye(7)
        range_start = records[0].name
        ret, curve = fit_particle_orbit(
            self.model, self._offsets, records, secmaps, range_start)
        style = self.frame.config['line_view']['backtrack_style']
        self.frame.add_curve("backtrack", curve, style)
        return ret


class EmittanceDialog(_FitWidget):

    # The three steps of UI initialization

    def __init__(self, session):
        super().__init__(session)
        self.long_transfer.clicked.connect(self.match_values)
        self.use_dispersion.clicked.connect(self.match_values)
        self.respect_coupling.clicked.connect(self.match_values)
        self.mtab.hideColumn(1)
        self.mtab.hideColumn(2)
        self._selected = self._monconf.setdefault('optics', {})

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

    def export_to(self, filename):
        beam_params = ('ex', 'ey', 'et')
        results = [(r.name.lower(), r.fit)
                   for r in self.results
                   if not isnan(r.fit)]
        data = yaml.safe_dump({
            'twiss': {k: v for k, v in results if k not in beam_params},
            'beam': {k: v for k, v in results if k in beam_params},
        }, default_flow_style=False)
        with open(filename, 'wt') as f:
            f.write(data)

    def on_update(self):
        self.match_values()

    def match_values(self):

        long_transfer = self.long_transfer.isChecked()
        use_dispersion = self.use_dispersion.isChecked()
        respect_coupling = self.respect_coupling.isChecked()

        min_monitors = 6 if use_dispersion else 3
        if self.num_selected() < min_monitors:
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
        tms = np.array(tms)[:, [0, 1, 2, 3, 5], :][:, :, [0, 1, 2, 3, 5]]

        # TODO: button for "resync model"

        # TODO: when 'interpolate' is on -> choose correct element...?
        # -> not important for l=0 monitors

        coup_xy = not np.allclose(tms[:, 0:2, 2:4], 0)
        coup_yx = not np.allclose(tms[:, 2:4, 0:2], 0)
        coup_xt = not np.allclose(tms[:, 0:2, 4:5], 0)
        coup_yt = not np.allclose(tms[:, 2:4, 4:5], 0)

        coupled = coup_xy or coup_yx
        dispersive = coup_xt or coup_yt

        envx = [m.envx for m in monitors]
        envy = [m.envy for m in monitors]
        xcs = [[(0, cx**2), (2, cy**2)]
               for cx, cy in zip(envx, envy)]

        # TODO: do we need to add dpt*D to sig11 in online control?

        def calc_sigma(tms, xcs, dispersive):
            if dispersive and not use_dispersion:
                logging.warning("Dispersive lattice!")
            if not use_dispersion:
                tms = tms[:, :-1, :-1]
            sigma, residuals, singular = solve_emit_sys(tms, xcs)
            return sigma

        # TODO: assert no dispersion / or use 6 monitors...
        if not respect_coupling:
            if coupled:
                logging.warning("Coupled lattice!")
            tmx = np.delete(np.delete(tms, [2, 3], axis=1), [2, 3], axis=2)
            tmy = np.delete(np.delete(tms, [0, 1], axis=1), [0, 1], axis=2)
            xcx = [[(0, cx[1])] for cx, cy in xcs]
            xcy = [[(0, cy[1])] for cx, cy in xcs]
            sigmax = calc_sigma(tmx, xcx, coup_xt)
            sigmay = calc_sigma(tmy, xcy, coup_yt)
            ex, betx, alfx = twiss_from_sigma(sigmax[0:2, 0:2])
            ey, bety, alfy = twiss_from_sigma(sigmay[0:2, 0:2])
            pt = sigmax[-1, -1]

        else:
            sigma = calc_sigma(tms, xcs, dispersive)
            ex, betx, alfx = twiss_from_sigma(sigma[0:2, 0:2])
            ey, bety, alfy = twiss_from_sigma(sigma[2:4, 2:4])
            pt = sigma[-1, -1]

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

    sq_matrix_basis = np.eye(d*d, d*d).reshape((d*d, d, d))
    is_upper_triang = [i for i, m in enumerate(sq_matrix_basis)
                       if np.allclose(np.triu(m), m)
                       and (d < 4 or np.allclose(m[0:2, 2:4], 0))]

    lhs = np.vstack([
        con_func(2*u-np.tril(u))
        for u in sq_matrix_basis[is_upper_triang]
    ]).T
    rhs = [c for xc in XCs for _, c in xc]

    x0, residuals, rank, singular = np.linalg.lstsq(lhs, rhs, rcond=-1)

    res = np.tensordot(x0, sq_matrix_basis[is_upper_triang], 1)
    res = res + res.T - np.tril(res)
    return res, sum(residuals), (rank < len(x0))


def twiss_from_sigma(sigma):
    """Compute 1D twiss parameters from 2x2 sigma matrix."""
    b = sigma[0, 0]
    a = sigma[0, 1]  # = sigma[1, 0] !
    c = sigma[1, 1]
    if b*c <= a*a:
        nan = float("nan")
        return nan, nan, nan
    emit = sqrt(b*c - a*a)
    beta = b/emit
    alfa = a/emit * (-1)
    return emit, beta, alfa
