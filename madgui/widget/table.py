"""
Popup view component for displaying table data.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx
from madgui.util import unit
from madgui.widget import listview

# exported symbols
__all__ = [
    'TableDialog',
]


def _format_key(item):
    return item[0]


def _format_val(item):
    val = item[1]
    if isinstance(val, list):
        return '[ {} ]'.format(
            ",".join(_format_val((None, v)) for v in val)
        )
    elif isinstance(val, (float, unit.units.Quantity)):
        return unit.format_quantity(val, '.3f')
    elif isinstance(val, basestring):
        return val
    else:
        return str(val)


class TableDialog(wx.Dialog):

    """
    Read-only dialog to show key-value pairs.

    The values are automatically rendered according to their type. There is no
    need for a {name: type} mapping.
    """

    column_info = [
        listview.ColumnInfo('Parameter', _format_key),
        listview.ColumnInfo('Value', _format_val, wx.LIST_FORMAT_RIGHT),
    ]

    def __init__(self, parent):
        """
        Create an empty popup window.

        Extends wx.Dialog.__init__.
        """
        super(TableDialog, self).__init__(
            parent=parent,
            style=wx.DEFAULT_DIALOG_STYLE|wx.SIMPLE_BORDER)
        # Create a two-column grid, with auto sized width
        grid = listview.ListCtrl(self, columns=self.column_info)
        grid.SetMinSize(wx.Size(400, 200))
        self.grid = grid
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.grid, flag=wx.ALL|wx.EXPAND, border=5)
        self.SetSizer(outer)
        self.Layout()
        self.Fit()
        self.Centre()

    @property
    def rows(self):
        return self.grid.items

    @rows.setter
    def rows(self, rows):
        """Update/set (key, value) pairs."""
        self.grid.items = rows[:]
