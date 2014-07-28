"""
Popup view component for displaying table data.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx


class AutoSizedTextCtrl(wx.TextCtrl):

    """
    Text control that adapts its minimum size to fit the text.
    """

    def SetValue(self, value):
        """Set text and update minimum size."""
        # Convert to `str` (so this works with SymbolicValue, Unum, etc)
        value = str(value)
        # FIXME: the factor 1.2 is just a wild guess
        minwidth = self.GetCharWidth() * len(value) * 1.2
        self.SetMinSize(wx.Size(int(minwidth), -1))
        return super(AutoSizedTextCtrl, self).SetValue(value)


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
        # Create a two-column grid, with auto sized width
        self.grid = wx.FlexGridSizer(rows=0, cols=2, vgap=5, hgap=5)
        self.grid.SetFlexibleDirection(wx.HORIZONTAL)
        self.grid.AddGrowableCol(1, proportion=1)
        # Don't grow height:
        self.grid.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_NONE)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.grid, flag=wx.ALL|wx.EXPAND, border=5)
        self.SetSizer(outer)
        self.Centre()

    @property
    def rows(self):
        """Iterate over currently shown (key, value) pairs as strings."""
        grid = self.grid
        num_rows = grid.CalcRowsCols()[0]
        for row in range(num_rows):
            if grid.GetItem(2*row):
                static = grid.GetItem(2*row).Window
                edit = grid.GetItem(2*row+1).Window
                yield static.LabelText, edit.Value

    @rows.setter
    def rows(self, rows):
        """Update/set (key, value) pairs."""
        grid = self.grid
        num_rows = grid.CalcRowsCols()[0]
        if len(rows) == num_rows:
            # update grid
            for row, (key, val) in enumerate(rows):
                grid.GetItem(2*row+0).Window.Value = key
                # remember this is an AutoSizedTextCtrl, we need `SetValue`
                # to properly convert and display an arbitrary value:
                grid.GetItem(2*row+1).Window.SetValue(val)
        else:
            # (re-)generate grid
            grid.Clear(deleteWindows=True)
            for key, val in rows:
                style = wx.TE_READONLY|wx.TE_RIGHT|wx.NO_BORDER
                label = wx.StaticText(self, label=key)
                text = AutoSizedTextCtrl(self, style=style)
                text.SetValue(val)
                grid.Add(label, flag=wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
                grid.Add(text, flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
        self.Fit()
