# encoding: utf-8
"""
Dialog for selecting DVM parameters to be synchronized.
"""

from __future__ import absolute_import

from functools import partial

from madgui.core import wx
from madgui.widget.listview import ListCtrl, ColumnInfo
from madgui.widget.input import Widget
from madgui.util.unit import format_quantity, tounit


class ListSelectWidget(Widget):

    """
    Widget for selecting from an immutable list of items.
    """

    _min_size = wx.Size(400, 300)
    _headline = 'Select desired items:'

    # TODO: allow to customize initial selection
    # FIXME: select-all looks ugly, check/uncheck-each is tedious...

    def CreateControls(self, window):
        """Create sizer with content area, i.e. input fields."""
        grid = ListCtrl(window, self.GetColumns(), style=0)
        grid.SetMinSize(self._min_size)
        self._grid = grid
        # create columns
        # other layout
        headline = wx.StaticText(window, label=self._headline)
        inner = wx.BoxSizer(wx.HORIZONTAL)
        inner.Add(grid, 1, flag=wx.ALL|wx.EXPAND, border=5)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(headline, flag=wx.ALL|wx.ALIGN_LEFT, border=5)
        outer.Add(inner, 1, flag=wx.ALL|wx.EXPAND, border=5)
        return outer

    def SetData(self, data):
        self._grid.items = data
        # TODO: replace SELECT(ALL) by SELECT(SELECTED)
        # TODO: the following was disabled for convenience. Currently, the
        # selection is not even used from the client code!
        #for idx in range(len(data)):
        #    self._grid.Select(idx)

    def GetData(self):
        return list(self._grid.selected_items)


def format_dvm_value(param, value):
    value = tounit(value, param.ui_unit)
    fmt_code = '.{}f'.format(param.ui_prec)
    return format_quantity(value, fmt_code)


class SyncParamWidget(ListSelectWidget):

    """
    Dialog for selecting DVM parameters to be synchronized.
    """

    def GetColumns(self):
        return [
            ColumnInfo(
                "Param",
                self._format_param,
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "DVM value",
                self._format_dvm_value,
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "MAD-X value",
                self._format_madx_value,
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def _format_param(self, index, item):
        param, dvm_value, mad_value = item
        return param.name

    def _format_dvm_value(self, index, item):
        param, dvm_value, mad_value = item
        return format_dvm_value(param, dvm_value)

    def _format_madx_value(self, index, item):
        param, dvm_value, mad_value = item
        return format_dvm_value(param, mad_value)


class ImportParamWidget(SyncParamWidget):
    Title = 'Import parameters from DVM'
    headline = 'Import selected DVM parameters.'


class ExportParamWidget(SyncParamWidget):
    Title = 'Set values in DVM from current sequence'
    headline = 'Overwrite selected DVM parameters.'


class MonitorWidget(ListSelectWidget):

    """
    Dialog for selecting SD monitor values to be imported.
    """

    Title = 'Set values in DVM from current sequence'

    _headline = "Import selected monitor measurements:"

    def GetColumns(self):
        return [
            ColumnInfo(
                "Monitor",
                self._format_monitor_name,
                wx.LIST_FORMAT_LEFT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "x",
                partial(self._format_sd_value, 'posx'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "y",
                partial(self._format_sd_value, 'posy'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "x width",
                partial(self._format_sd_value, 'widthx'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
            ColumnInfo(
                "y width",
                partial(self._format_sd_value, 'widthy'),
                wx.LIST_FORMAT_RIGHT,
                wx.LIST_AUTOSIZE),
        ]

    def _format_monitor_name(self, index, item):
        el_name, values = item
        return el_name

    def _format_sd_value(self, name, index, item):
        el_name, values = item
        value = values.get(name)
        if value is None:
            return ''
        return format_quantity(value)
