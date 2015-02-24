"""
Popup view component for displaying table data.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx
from madgui.widget.listview import ListView


class TableDialog(wx.Dialog):

    """
    Dialog to show key-value pairs.

    The keys are displayed by :class:`wx.StaticText`, the values are
    represented in :class:`AutoSizedTextCtrl`.
    """

    def __init__(self, parent):
        """
        Create an empty popup window.

        Extends wx.Dialog.__init__.
        """
        super(TableDialog, self).__init__(
            parent=parent,
            style=wx.DEFAULT_DIALOG_STYLE|wx.SIMPLE_BORDER)
        self._rows = []
        # Create a two-column grid, with auto sized width
        grid = ListView(self, style=wx.LC_REPORT)
        grid.SetMinSize(wx.Size(400, 200))
        self.grid = grid
        grid.InsertColumn(0, "Parameter", width=wx.LIST_AUTOSIZE)
        grid.InsertColumn(1, "Value", width=wx.LIST_AUTOSIZE,
                          format=wx.LIST_FORMAT_RIGHT)
        grid.InsertColumn(2, "Unit")
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.grid, flag=wx.ALL|wx.EXPAND, border=5)
        self.SetSizer(outer)
        self.Layout()
        self.Fit()
        self.Centre()

    @property
    def rows(self):
        return self._rows

    @rows.setter
    def rows(self, rows):
        """Update/set (key, value) pairs."""
        grid = self.grid
        num_rows = grid.GetItemCount()
        if len(rows) == num_rows:
            # update grid
            for row, (key, val) in enumerate(rows):
                value, unit = _split_value(val)
                grid.SetStringItem(row, 0, key)
                grid.SetStringItem(row, 1, value)
                grid.SetStringItem(row, 2, unit)
        else:
            # (re-)generate grid
            grid.DeleteAllItems()
            for row, (key, val) in enumerate(rows):
                value, unit = _split_value(val)
                grid.InsertStringItem(row, key)
                grid.SetStringItem(row, 1, value)
                grid.SetStringItem(row, 2, unit)
        grid.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        grid.SetColumnWidth(1, wx.LIST_AUTOSIZE)

def _split_value(value):
    from madgui.util.unit import strip_unit, get_unit_label
    try:
        return str(strip_unit(value)), get_unit_label(value)
    except AttributeError:
        return str(value), ""
