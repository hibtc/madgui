"""
Dialog for selecting DVM parameters to be synchronized.
"""

import numpy as np

from madgui.qt import Qt, QtGui, load_ui
from madgui.core.unit import to_ui, from_ui, ui_units
from madgui.util.layout import VBoxLayout
from madgui.widget.tableview import (TableView, ColumnInfo, ExtColumnInfo,
                                     StringValue)

class ListSelectWidget(QtGui.QWidget):

    """
    Widget for selecting from an immutable list of items.
    """

    _headline = 'Select desired items:'

    # TODO: allow to customize initial selection
    # FIXME: select-all looks ugly, check/uncheck-each is tedious...

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
        # TODO: replace SELECT(ALL) by SELECT(SELECTED)
        # TODO: the following was disabled for convenience. Currently, the
        # selection is not even used from the client code!
        #for idx in range(len(data)):
        #    self.grid.Select(idx)


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
        self.unit = ui_units.label('x')
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
    return monitor.show

def set_monitor_show(mgr, monitor, i, show):
    shown = monitor.show
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

    # TODO: disable/deselect monitors with invalid values?

    columns = [
        ExtColumnInfo("Monitor", CheckedStringValue),
        ColumnInfo("x", 'posx'),
        ColumnInfo("y", 'posy'),
        ColumnInfo("x width", 'envx'),
        ColumnInfo("y width", 'envy'),
        ColumnInfo("Unit", 'unit', resize=QtGui.QHeaderView.ResizeToContents),
    ]

    def __init__(self, control, model, frame):
        super().__init__()
        load_ui(self, __package__, self.ui_file)

        self.control = control
        self.model = model
        self.frame = frame

        self.grid.set_columns(self.columns, context=self)
        self.grid.horizontalHeader().setHighlightSections(False)
        self.grid.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.grid.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)

        Buttons = QtGui.QDialogButtonBox
        self.btn_update.clicked.connect(self.update)
        self.std_buttons.button(Buttons.Ok).clicked.connect(self.accept)
        self.std_buttons.button(Buttons.Cancel).clicked.connect(self.reject)

        if not frame.graphs('envelope'):
            frame.open_graph('orbit')

        self.update()

    def reject(self):
        self.remove()
        super().reject()

    def remove(self):
        for scene in self.frame.views:
            for i, (n, d, s) in enumerate(scene.loaded_curves):
                if n == "monitors":
                    del scene.loaded_curves[i]

    def draw(self):

        # TODO: Our way of adding ourselves to existing and to-be-opened
        # figures is tedious and error-prone. We should really rework the
        # plotting system to separate the artist from the scene element. We
        # could then simply register a generic artist to plot the content into
        # all potential scenes.

        for mon in self.monitors:
            mon.s = to_ui('s', self.model.elements[mon.name].At)
            mon.x = mon.posx
            mon.y = mon.posy

        name = "monitors"

        self.grid.horizontalHeader().setHighlightSections(False)
        self.grid.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.grid.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        data = from_ui({
            name: np.array([getattr(mon, name)
                            for mon in self.monitors
                            if mon.show])
            for name in ['s', 'envx', 'envy', 'x', 'y']
        })
        style = self.frame.config['line_view']['monitor_style']

        for scene in self.frame.views:
            show = True
            for i, (n, d, s) in enumerate(scene.loaded_curves):
                if n == name:
                    show = i in scene.shown_curves
                    del scene.loaded_curves[i]
                    break
            scene.loaded_curves.append((name, data, style))
            if not show:
                scene.shown_curves.remove(len(scene.shown_curves)-1)
            scene.user_curves.invalidate()

    def select(self, index):
        self.monitors[index].show = True
        self.draw()

    def deselect(self, index):
        self.monitors[index].show = False
        self.draw()

    def update(self):
        self.grid.rows = self.monitors = [
            MonitorItem(el.Name, self.control.read_monitor(el.Name))
            for el in self.model.elements
            if el.Type.lower().endswith('monitor')
            or el.Type.lower() == 'instrument']
        self.draw()
