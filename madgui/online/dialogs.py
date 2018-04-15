"""
Dialog for selecting DVM parameters to be synchronized.
"""

import os

import numpy as np

from madgui.qt import Qt, QtGui, load_ui
from madgui.core.unit import to_ui, from_ui, ui_units
from madgui.util.layout import VBoxLayout
from madgui.util import yaml
from madgui.widget.tableview import (TableView, ColumnInfo, ExtColumnInfo,
                                     StringValue)

class ListSelectWidget(QtGui.QWidget):

    """
    Widget for selecting from an immutable list of items.
    """

    # TODO: use CheckedStringValue to let user select which items to
    # import/export.

    _headline = 'Select desired items:'

    def __init__(self, columns, headline):
        """Create sizer with content area, i.e. input fields."""
        super().__init__()
        self.grid = grid = TableView(columns=columns, context=self)
        label = QtGui.QLabel(headline)
        self.setLayout(VBoxLayout([label, grid]))

    @property
    def data(self):
        return list(self.grid.rows)

    @data.setter
    def data(self, data):
        self.grid.rows = data


class SyncParamItem:

    def __init__(self, param, dvm_value, mad_value, attr):
        self.param = param
        self.name = param.name
        self.unit = ui_units.label(attr)
        self.dvm_value = to_ui(attr, dvm_value)
        self.mad_value = to_ui(attr, mad_value)


class SyncParamWidget(ListSelectWidget):

    """
    Dialog for selecting DVM parameters to be synchronized.
    """

    columns = [
        ColumnInfo("Param", 'name'),
        ColumnInfo("DVM value", 'dvm_value'),
        ColumnInfo("MAD-X value", 'mad_value'),
        ColumnInfo("Unit", 'unit',
                   resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, title, headline):
        super().__init__(self.columns, headline)
        self.title = title


def ImportParamWidget():
    return SyncParamWidget(
        'Import parameters from DVM',
        'Import selected DVM parameters.')


def ExportParamWidget():
    return SyncParamWidget(
        'Set values in DVM from current sequence',
        'Overwrite selected DVM parameters.')


class MonitorItem:

    def __init__(self, el_name, values):
        self.name = el_name
        self.posx = to_ui('x', values.get('posx'))
        self.posy = to_ui('x', values.get('posy'))
        self.envx = to_ui('x', values.get('envx'))
        self.envy = to_ui('x', values.get('envy'))
        self.show = (self.envx > 0 and
                     self.envy > 0 and
                     not np.isclose(self.posx, -9999) and
                     not np.isclose(self.posy, -9999))


# TODO: merge this with madgui.widget.curvemanager.CheckedStringValue
class CheckedStringValue(StringValue):

    """String value with checkbox."""

    default = False

    def __init__(self, mgr, _, idx):
        self.mgr = mgr
        self.idx = idx
        super().__init__(get_monitor_name(mgr, mgr.monitors[idx], idx),
                         editable=False)

    def checked(self):
        return get_monitor_show(self.mgr, self.mgr.monitors[self.idx], self.idx)

    def flags(self):
        base_flags = super().flags()
        return base_flags | Qt.ItemIsUserCheckable

    def setData(self, value, role):
        mgr = self.mgr
        idx = self.idx
        val = self.mgr.monitors[idx]
        if role == Qt.CheckStateRole:
            set_monitor_show(mgr, val, idx, value == Qt.Checked)
            return True
        return super().setData(value, role)


def get_monitor_name(mgr, monitor, i):
    return monitor.name

def get_monitor_show(mgr, monitor, i):
    return mgr.selected(monitor)

def set_monitor_show(mgr, monitor, i, show):
    shown = mgr.selected(monitor)
    if show and not shown:
        mgr.select(i)
    elif not show and shown:
        mgr.deselect(i)


class MonitorWidget(QtGui.QDialog):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    title = 'Set values in DVM from current sequence'
    headline = "Select for which monitors to plot measurements:"

    ui_file = 'monitorwidget.ui'

    columns = [
        ExtColumnInfo("Monitor", CheckedStringValue),
        ColumnInfo("x", 'posx'),
        ColumnInfo("y", 'posy'),
        ColumnInfo("Δx", 'envx'),
        ColumnInfo("Δy", 'envy'),
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

        for col in self.columns[1:]:
            col.title += '/' + ui_units.label(col.getter)

        self.grid.set_columns(self.columns, context=self)
        self.grid.horizontalHeader().setHighlightSections(False)
        self.grid.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.grid.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)

        Buttons = QtGui.QDialogButtonBox
        self.btn_update.clicked.connect(self.update)
        self.btn_backtrack.toggled.connect(self.toggle_backtrack)
        self.std_buttons.button(Buttons.Ok).clicked.connect(self.accept)
        self.std_buttons.button(Buttons.Cancel).clicked.connect(self.reject)
        self.std_buttons.button(Buttons.Save).clicked.connect(self.save)

        self.backup()

    def showEvent(self, event):
        if not self.frame.graphs('envelope'):
            self.frame.open_graph('orbit')
        self.update()

    def reject(self):
        self.remove()
        self.restore()
        super().reject()

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
            mon.s = to_ui('s', self.model.elements[mon.name].position)
            mon.x = mon.posx
            mon.y = mon.posy

        name = "monitors"

        self.grid.horizontalHeader().setHighlightSections(False)
        self.grid.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.grid.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        data = from_ui({
            name: np.array([getattr(mon, name)
                            for mon in self.monitors
                            if self.selected(mon)])
            for name in ['s', 'envx', 'envy', 'x', 'y']
        })
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
        if self.btn_backtrack.isChecked():
            self.backtrack()
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

    def toggle_backtrack(self, enabled):
        if enabled:
            self.backtrack()

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
        self.model.madx.command.select(flag='interpolate', clear=True)
        secmaps = self.model.get_transfer_maps([r.name for r in records])
        secmaps = list(itertools.accumulate(secmaps, lambda a, b: np.dot(b, a)))
        (x, px, y, py), chi_squared, singular = fit_initial_orbit(*[
            (secmap[:,:6], secmap[:,6], (record.posx/1000, record.posy/1000))
            for record, secmap in zip(records, secmaps)
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
