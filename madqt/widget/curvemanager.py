"""
Dialog for managing shown curves.
"""

# TODO:
# - buttons:
#       - load file
#       - remove

from pkg_resources import resource_filename
from collections import namedtuple

from madqt.qt import QtGui, uic
from madqt.widget.tableview import ExtColumnInfo


def get_curve_name(selected, curve, i):
    name, data = curve
    return name

def get_curve_show(selected, curve, i):
    return i in selected

def set_curve_show(selected, curve, i, show):
    shown = i in selected
    if show and not shown:
        selected.append(i)
    elif not show and shown:
        selected.remove(i)


class CurveManager(QtGui.QWidget):

    ui_file = 'curvemanager.ui'

    columns = [
        ExtColumnInfo("show", get_curve_show, set_curve_show),
        ExtColumnInfo("name", get_curve_name),
    ]

    def __init__(self, available, selected):
        super().__init__()
        self.available = available
        self.selected = selected
        uic.loadUi(resource_filename(__name__, self.ui_file), self)
        self.init_controls()
        self.set_initial_values()
        self.connect_signals()

    def init_controls(self):
        self.tab.horizontalHeader().setHighlightSections(False)
        self.tab.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tab.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
        self.tab.set_columns(self.columns, self.available, self.selected)

    def set_initial_values(self):
        pass

    def connect_signals(self):
        pass

    @property
    def data(self):
        return self.tab.rows
