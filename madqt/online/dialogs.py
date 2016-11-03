# encoding: utf-8
"""
Dialog for selecting DVM parameters to be synchronized.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from functools import partial

from madqt.qt import QtCore, QtGui
from madqt.core.unit import format_quantity, tounit
from madqt.util.layout import VBoxLayout
from madqt.widget.tableview import TableView, ColumnInfo, makeValue


# TODO: use UI units


class ListSelectWidget(QtGui.QWidget):

    """
    Widget for selecting from an immutable list of items.
    """

    _headline = 'Select desired items:'

    # TODO: allow to customize initial selection
    # FIXME: select-all looks ugly, check/uncheck-each is tedious...

    def __init__(self, columns, headline):
        """Create sizer with content area, i.e. input fields."""
        super(ListSelectWidget, self).__init__()
        self.grid = grid = TableView(columns)
        grid._setColumnResizeMode(0, QtGui.QHeaderView.ResizeToContents)
        for idx in range(1, len(columns)):
            grid._setColumnResizeMode(idx, QtGui.QHeaderView.Stretch)
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


class SyncParamItem(object):

    def __init__(self, param, dvm_value, mad_value):
        self.param = param
        self.name = param.name
        self.dvm_value = tounit(dvm_value, param.ui_unit)
        self.mad_value = tounit(mad_value, param.ui_unit)


class SyncParamWidget(ListSelectWidget):

    """
    Dialog for selecting DVM parameters to be synchronized.
    """

    columns = [
        ColumnInfo("Param", 'name'),
        ColumnInfo("DVM value", 'dvm_value'),
        ColumnInfo("MAD-X value", 'mad_value'),
    ]

    def __init__(self, title, headline):
        super(SyncParamWidget, self).__init__(self.columns, headline)
        self.title = title


def ImportParamWidget():
    return SyncParamWidget(
        'Import parameters from DVM',
        'Import selected DVM parameters.')


def ExportParamWidget():
    return SyncParamWidget(
        'Set values in DVM from current sequence',
        'Overwrite selected DVM parameters.')


class MonitorItem(object):

    def __init__(self, el_name, values):
        self.name = el_name
        self.posx = values.get('posx')
        self.posy = values.get('posy')
        self.widthx = values.get('widthx')
        self.widthy = values.get('widthy')


class MonitorWidget(ListSelectWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    title = 'Set values in DVM from current sequence'
    headline = "Import selected monitor measurements:"

    columns = [
        ColumnInfo("Monitor", 'name'),
        ColumnInfo("x", 'posx'),
        ColumnInfo("y", 'posy'),
        ColumnInfo("x width", 'widthx'),
        ColumnInfo("y width", 'widthy'),
    ]

    def __init__(self):
        super(MonitorWidget, self).__init__(self.columns, self.headline)
