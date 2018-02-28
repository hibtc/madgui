"""
Dialog for managing shown curves.
"""

import os
from pkg_resources import resource_filename

from madgui.qt import Qt, QtGui, uic
from madgui.widget.tableview import ExtColumnInfo, StringValue
from madgui.widget.filedialog import getOpenFileName


class CheckedStringValue(StringValue):

    """String value with checkbox."""

    default = False

    def __init__(self, mgr, _, idx):
        self.mgr = mgr
        self.idx = idx
        super().__init__(get_curve_name(mgr, mgr.available[idx], idx),
                         editable=True)

    def checked(self):
        return get_curve_show(self.mgr, self.mgr.available[self.idx], self.idx)

    def flags(self):
        base_flags = super().flags()
        return base_flags | Qt.ItemIsEditable | Qt.ItemIsUserCheckable

    def setData(self, value, role):
        mgr = self.mgr
        idx = self.idx
        val = self.mgr.available[idx]
        if role == Qt.CheckStateRole:
            set_curve_show(mgr, val, idx, value == Qt.Checked)
            return True
        elif role == Qt.EditRole:
            set_curve_name(mgr, val, idx, value)
            return True
        return super().setData(value, role)


def get_curve_name(mgr, curve, i):
    name, data = curve
    return name

def set_curve_name(mgr, curve, i, name):
    _, data = curve
    mgr.available[i] = (name, data)

def get_curve_show(mgr, curve, i):
    return i in mgr.selected

def set_curve_show(mgr, curve, i, show):
    shown = i in mgr.selected
    if show and not shown:
        mgr.selected.append(i)
    elif not show and shown:
        mgr.selected.remove(i)


class CurveManager(QtGui.QWidget):

    ui_file = 'curvemanager.ui'

    columns = [
        ExtColumnInfo("curves", CheckedStringValue,
                      resize=QtGui.QHeaderView.Stretch),
    ]

    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self.available = scene.loaded_curves
        self.selected = scene.shown_curves
        self.folder = scene.model.repo.path
        # UI
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.init_controls()
        self.connect_signals()

    def init_controls(self):
        self.tab.horizontalHeader().setHighlightSections(False)
        self.tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.tab.set_columns(self.columns, self.available, self)

    def connect_signals(self):
        self.btn_save.clicked.connect(self.on_btn_save)
        self.btn_load.clicked.connect(self.on_btn_load)
        self.tab.connectButtons(self.btn_remove)

    @property
    def data(self):
        return self.tab.rows

    def on_btn_save(self):
        data = {
            curve.y_name: curve.get_ydata()
            for curve in self.scene.twiss_curves.items
        }
        curve = next(iter(self.scene.twiss_curves.items))
        data[curve.x_name] = curve.get_xdata()
        self.scene.snapshot_num += 1
        name = "snapshot {}".format(self.scene.snapshot_num)
        self.available.append((name, data))
        self.tab.edit(self.tab.model().index(len(self.available)-1, 0))

    def on_btn_load(self):
        filename = getOpenFileName(
            self.window(), 'Open data file for comparison',
            self.folder, self.dataFileFilters)
        if filename:
            self.folder, basename = os.path.split(filename)
            data = self.load_file(filename)
            self.available.append((basename, data))

    dataFileFilters = [
        ("Text files", "*.txt", "*.dat"),
        ("TFS tables", "*.tfs", "*.twiss"),
    ]

    def load_file(self, filename):
        from madgui.util.table import read_table, read_tfsfile
        if filename.lower().rsplit('.')[-1] not in ('tfs', 'twiss'):
            return read_table(filename)
        model = self.scene.model
        utool = model.utool
        table = read_tfsfile(filename)
        data = table.copy()
        # TODO: this should be properly encapsulated:
        if 'sig11' in data:
            data['envx'] = data['sig11'] ** 0.5
        elif 'betx' in data:
            # FIXME TODO: use position-dependent emittances…
            try:
                ex = table.summary['ex']
            except ValueError:
                ex = utool.strip_unit('ex', model.ex())
            data['envx'] = (data['betx'] * ex) ** 0.5
        if 'sig33' in data:
            data['envy'] = data['sig33']**0.5
        elif 'bety' in data:
            try:
                ey = table.summary['ey']
            except ValueError:
                ey = utool.strip_unit('ey', model.ey())
            data['envy'] = (data['bety'] * ey) ** 0.5
        return utool.dict_add_unit(data)
