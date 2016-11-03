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
from madqt.widget.tableview import TableView, ColumnInfo


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


def _format_param(item):
    param, dvm_value, mad_value = item
    return param.name

def _format_dvm_value(item):
    param, dvm_value, mad_value = item
    return tounit(dvm_value, param.ui_unit)

def _format_madx_value(item):
    param, dvm_value, mad_value = item
    return tounit(mad_value, param.ui_unit)


class SyncParamWidget(ListSelectWidget):

    """
    Dialog for selecting DVM parameters to be synchronized.
    """

    columns = [
        ColumnInfo("Param", _format_param),
        ColumnInfo("DVM value", _format_dvm_value),
        ColumnInfo("MAD-X value", _format_madx_value),
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


def _format_monitor_name(item):
    el_name, values = item
    return el_name


def _format_sd_value(name, item):
    el_name, values = item
    return values.get(name)


class MonitorWidget(ListSelectWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    title = 'Set values in DVM from current sequence'
    headline = "Import selected monitor measurements:"

    columns = [
        ColumnInfo("Monitor", _format_monitor_name),
        ColumnInfo("x", partial(_format_sd_value, 'posx')),
        ColumnInfo("y", partial(_format_sd_value, 'posy')),
        ColumnInfo("x width", partial(_format_sd_value, 'widthx')),
        ColumnInfo("y width", partial(_format_sd_value, 'widthy')),
    ]

    def __init__(self):
        super(MonitorWidget, self).__init__(self.columns, self.headline)
