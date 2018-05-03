import os

import numpy as np

from madgui.qt import QtGui, load_ui
from madgui.util import yaml
from madgui.util.layout import VBoxLayout
from madgui.widget.tableview import ColumnInfo, ExtColumnInfo
from madgui.online.emittance import EmittanceDialog


class MonitorWidget(QtGui.QDialog):

    def __init__(self, control, model, frame):
        super().__init__(frame)
        self.tabs = QtGui.QTabWidget()
        self.tabs.addTab(PlotMonitorWidget(control, model, frame), "Plot")
        self.tabs.addTab(EmittanceDialog(control), "Optics")
        self.setLayout(VBoxLayout([self.tabs], tight=True))
        self.setSizeGripEnabled(True)


class MonitorItem:

    def __init__(self, el_name, values):
        self.name = el_name
        self.posx = values.get('posx')
        self.posy = values.get('posy')
        self.envx = values.get('envx')
        self.envy = values.get('envy')
        self.show = (self.envx is not None and self.envx > 0 and
                     self.envy is not None and self.envy > 0 and
                     not np.isclose(self.posx, -9.999) and
                     not np.isclose(self.posy, -9.999))


def get_monitor_name(mgr, monitor, i):
    return monitor.name

def get_monitor_show(cell):
    monitor, mgr = cell.item, cell.model.context
    return mgr.selected(monitor)

def set_monitor_show(cell, show):
    i, monitor, mgr = cell.row, cell.item, cell.model.context
    shown = mgr.selected(monitor)
    if show and not shown:
        mgr.select(i)
    elif not show and shown:
        mgr.deselect(i)


class PlotMonitorWidget(QtGui.QWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    title = 'Set values in DVM from current sequence'
    headline = "Select for which monitors to plot measurements:"

    ui_file = 'monitorwidget.ui'

    columns = [
        ExtColumnInfo("Monitor", get_monitor_name, checkable=True,
                      checked=get_monitor_show, setChecked=set_monitor_show),
        ColumnInfo("x", 'posx', convert=True),
        ColumnInfo("y", 'posy', convert=True),
        ColumnInfo("Δx", 'envx', convert=True),
        ColumnInfo("Δy", 'envy', convert=True),
    ]

    def __init__(self, control, model, frame):
        super().__init__(frame)
        load_ui(self, __package__, self.ui_file)

        self.control = control
        self.model = model
        self.frame = frame

        # TODO: we should eventually load this from model-specific session
        # file, but it's fine like this for now:
        self._monitor_show = self.frame.config['online_control']['monitors']
        self._monitor_offs = self.frame.config['online_control']['offsets']

        self.grid.set_columns(self.columns, context=self)
        self.grid.horizontalHeader().setHighlightSections(False)
        self.grid.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.grid.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)

        Buttons = QtGui.QDialogButtonBox
        self.btn_update.clicked.connect(self.update)
        self.btn_backtrack.clicked.connect(self.backtrack)
        self.btn_offsets.clicked.connect(self.save_offsets)
        self.std_buttons.button(Buttons.Ok).clicked.connect(self.accept)
        self.std_buttons.button(Buttons.Cancel).clicked.connect(self.reject)
        self.std_buttons.button(Buttons.Save).clicked.connect(self.save)

        self.backup()

    def showEvent(self, event):
        if not self.frame.graphs('envelope'):
            self.frame.open_graph('orbit')
        self.update()

    def accept(self):
        self.window().accept()

    def reject(self):
        self.remove()
        self.restore()
        self.window().reject()

    def remove(self):
        for scene in self.frame.views:
            for i, (n, d, s) in enumerate(scene.loaded_curves):
                if n == "monitors":
                    del scene.loaded_curves[i]

    def draw(self):

        # FIXME: Our way of adding ourselves to existing and to-be-opened
        # figures is tedious and error-prone. We should really rework the
        # plotting system to separate the artist from the scene element. We
        # could then simply register a generic artist to plot the content into
        # all potential scenes.

        for mon in self.monitors:
            mon.s = self.model.elements[mon.name].position
            dx, dy = self._monitor_offs.get(mon.name.lower(), (0, 0))
            mon.x = (mon.posx + dx) if mon.posx is not None else None
            mon.y = (mon.posy + dy) if mon.posy is not None else None

        name = "monitors"

        self.grid.horizontalHeader().setHighlightSections(False)
        self.grid.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.grid.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        data = {
            name: np.array([getattr(mon, name)
                            for mon in self.monitors
                            if self.selected(mon)])
            for name in ['s', 'envx', 'envy', 'x', 'y']
        }
        style = self.frame.config['line_view']['monitor_style']

        for scene in self.frame.views:
            for i, (n, d, s) in enumerate(scene.loaded_curves):
                if n == name:
                    scene.loaded_curves[i][1].update(data)
                    if i in scene.shown_curves:
                        j = scene.shown_curves.index(i)
                        scene.user_curves.items[j].update()
                    break
            else:
                scene.loaded_curves.append((name, data, style))

    def selected(self, monitor):
        return self._monitor_show.setdefault(monitor.name, monitor.show)

    def select(self, index):
        self._monitor_show[self.monitors[index].name] = True
        self.draw()

    def deselect(self, index):
        self._monitor_show[self.monitors[index].name] = False
        self.draw()

    def update(self):
        self.grid.rows = self.monitors = [
            MonitorItem(el.node_name, self.control.read_monitor(el.node_name))
            for el in self.model.elements
            if el.base_name.lower().endswith('monitor')
            or el.base_name.lower() == 'instrument']
        self.draw()

    folder = None
    exportFilters = [
        ("YAML file", ".yml"),
        ("TEXT file (numpy compatible)", ".txt"),
    ]

    def save(self):
        from madgui.widget.filedialog import getSaveFileName
        filename = getSaveFileName(
            self.window(), 'Export values', self.folder,
            self.exportFilters)
        if filename:
            self.export_to(filename)
            self.folder, _ = os.path.split(filename)

    def export_to(self, filename):
        ext = os.path.splitext(filename)[1].lower()

        # TODO: add '.tfs' output format?
        if ext == '.yml':
            data = {'monitor': {
                m.name: {'x': m.posx, 'y': m.posy,
                         'envx': m.envx, 'envy': m.envy }
                for m in self.grid.rows
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
                for m in self.grid.rows
                if m.selected(m)
            ])
            np.savetxt(filename, data, header='s x y envx envy')
            return

        raise NotImplementedError(
            "Don't know how to serialize to {!r} format."
            .format(ext))

    def save_offsets(self):
        self.model.twiss()
        for m in self.monitors:
            tw = self.model.get_elem_twiss(m.name)
            if self.selected(m):
                self._monitor_offs[m.name.lower()] = (
                    tw.x - m.posx,
                    tw.y - m.posy)

    def backtrack(self):
        init_orbit, chi_squared, singular = \
            self.fit_particle_orbit()
        if not singular:
            self.model.twiss_args = dict(self.model.twiss_args, **init_orbit)
            self.model.twiss.invalidate()

    def fit_particle_orbit(self):
        from madgui.correct.orbit import fit_initial_orbit
        import itertools

        records = [m for m in self.monitors if self.selected(m)]
        self.restore()
        secmaps = self.model.get_transfer_maps([r.name for r in records])
        secmaps = list(itertools.accumulate(secmaps, lambda a, b: np.dot(b, a)))
        (x, px, y, py), chi_squared, singular = fit_initial_orbit(*[
            (secmap[:,:6], secmap[:,6], (record.posx+dx, record.posy+dy))
            for record, secmap in zip(records, secmaps)
            for dx, dy in [self._monitor_offs.get(record.name.lower(), (0, 0))]
        ])
        return {
            'x': x, 'px': px,
            'y': y, 'py': py,
        }, chi_squared, singular

    def backup(self):
        self.backup_twiss_args = self.model.twiss_args

    def restore(self):
        self.model.twiss_args = self.backup_twiss_args
        self.model.twiss.invalidate()
