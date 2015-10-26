# encoding: utf-8
"""
Parameter input dialog as used for :class:`TwissWidget` and
:class:`BeamWidget`.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from collections import OrderedDict

import yaml

# GUI components
from madgui.core import wx

# internal
from madgui.widget.input import Widget, ShowModal, Cancellable
from madgui.widget import listview
from madgui.widget.filedialog import OpenDialog, SaveDialog, path_with_ext

# exported symbols
__all__ = [
    'Bool',
    'String',
    'Float',
    'Matrix',
    'ParamTable',
]


class ParamGroup(object):

    """Group of corresponding parameters."""

    def __init__(self, **kwargs):
        """Initialize with names and defaults."""
        self._defaults = OrderedDict((k, kwargs[k]) for k in sorted(kwargs))

    def names(self):
        """Get all parameter names in this group."""
        return self._defaults.keys()

    def default(self, param):
        """Get the default value for a specific parameter name."""
        return self._defaults[param]


class Bool(ParamGroup):

    ValueType = listview.BoolValue


class String(ParamGroup):

    ValueType = listview.QuotedStringValue


class Float(ParamGroup):

    ValueType = listview.FloatValue


class Matrix(Float):

    def __init__(self, **kwargs):
        """
        Initialize from the given matrix definition.

        Implicitly assumes that len(kwargs) == 1 and the value is a
        consistent non-empty matrix.
        """
        key, val = next(iter(kwargs.items()))
        rows = len(val)
        cols = len(val[0])
        self._layout = (rows, cols)
        params = dict((key + str(row) + str(col), val[row][col])
                       for col in range(cols)
                       for row in range(rows))
        super(Matrix, self).__init__(**params)


# TODO: class Vector(Float)
# unlike Matrix this represents a single MAD-X parameter of type ARRAY.


class ParamTable(Widget):

    """
    Input controls to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.

    :ivar UnitConverter utool: tool to add/remove units from input values
    :ivar list params: all possible ParamGroups
    :ivar dict data: initial/final parameter values

    Private GUI members:

    :ivar wx.GridBagSizer _grid: sizer that contains all parameters
    """

    def __init__(self, window, utool, **kw):
        """Initialize data."""
        self.utool = utool
        self._params = OrderedDict(
            (param, group)
            for group in self.params
            for param in group.names()
        )
        super(ParamTable, self).__init__(window, **kw)

    def CreateControls(self, window):
        """Create sizer with content area, i.e. input fields."""
        style = wx.LC_REPORT | wx.LC_SINGLE_SEL
        self._grid = grid = listview.EditListCtrl(window, style=style,
                                                  autosize_columns=[0, 1, 3])
        grid.InsertColumn(0, "Parameter", width=wx.LIST_AUTOSIZE)
        grid.InsertColumn(1, "Value", width=wx.LIST_AUTOSIZE,
                          format=wx.LIST_FORMAT_RIGHT)
        grid.InsertColumn(2, "Unit")
        grid.SetMinSize(wx.Size(400, 200))
        grid.Bind(wx.EVT_CHAR, self.OnChar)

        button_open = wx.Button(window, wx.ID_OPEN)
        button_save = wx.Button(window, wx.ID_SAVE)

        buttons = wx.BoxSizer(wx.VERTICAL)
        buttons.Add(button_open, flag=wx.ALL|wx.EXPAND, border=5)
        buttons.Add(button_save, flag=wx.ALL|wx.EXPAND, border=5)
        window.Bind(wx.EVT_BUTTON, self.OnImport, button_open)
        window.Bind(wx.EVT_BUTTON, self.OnExport, button_save)

        content = wx.BoxSizer(wx.HORIZONTAL)
        content.Add(grid, 1, flag=wx.ALL|wx.EXPAND, border=5)
        content.Add(buttons, flag=wx.ALL|wx.ALIGN_TOP, border=5)
        return content

    def OnChar(self, event):
        """Return: open editor; Delete/Backspace: remove value."""
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_DELETE or keycode == wx.WXK_BACK:
            self.SetRowValue(self._grid.curRow, None)
        elif keycode == wx.WXK_RETURN:
            self._grid.OpenEditor(self._grid.curRow, 1)
        else:
            event.Skip()

    @Cancellable
    def OnImport(self, event):
        """Import parameters from file."""
        wildcards = [("YAML file", "*.yml", "*.yaml"),
                     ("JSON file", "*.json")]
        dlg = OpenDialog(self.TopLevelWindow, "Import values", wildcards)
        with dlg:
            ShowModal(dlg)
        with open(dlg.GetPath(), 'rt') as f:
            # Since JSON is a subset of YAML there is no need to invoke a
            # different parser (unless we want validate the file):
            raw_data = yaml.safe_load(f)
        data = self.utool.dict_add_unit(raw_data)
        self.SetData(data)

    @Cancellable
    def OnExport(self, event):
        """Export parameters to file."""
        wildcards = [("YAML file", "*.yml", "*.yaml")]
        dlg = SaveDialog(self.TopLevelWindow, "Import values", wildcards)
        with dlg:
            ShowModal(dlg)
        data = self.GetData()
        raw_data = self.utool.dict_strip_unit(data)
        file_path = path_with_ext(dlg, wildcards)
        with open(file_path, 'wt') as f:
            yaml.safe_dump(raw_data, f, default_flow_style=False)

    def SetData(self, data):
        """Update dialog with initial values."""
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        for param_name in self._params:
            self.SetParamValue(param_name, data.get(param_name))
        self._grid._doResize()

    def GetData(self):
        """Get dictionary with all input values from dialog."""
        return {self.GetRowName(row): self.GetRowQuantity(row)
                for row in range(self._grid.GetItemCount())
                if self.GetRowValue(row) is not None}

    def SetParamValue(self, name, value):
        """
        Set a single parameter value.

        Add the parameter to the list if necessary.

        :param str name: parameter name
        :param value: parameter value
        :raises KeyError: if the parameter name is invalid
        """
        grid = self._grid
        item = grid.FindItem(0, name, partial=False)
        if item == -1:
            item = grid.GetItemCount()
            grid.InsertRow(item)
            self.SetRowName(item, name)
        if value is None:
            self.SetRowValue(item, None)
        else:
            self.SetRowValue(item, self.utool.strip_unit(name, value))

    def GetRowCount(self):
        """Get number of rows."""
        return self._grid.GetItemCount()

    def FindRow(self, name):
        """Get the index showing the row with the specified name."""
        for row in range(self.GetRowCount()):
            if self.GetRowName(row) == name:
                return row
        raise ValueError("Row not found: {}".format(name))

    def ToIndex(self, row):
        """Convert row name to row index, leave indices as is."""
        if isinstance(row, int):
            return row
        return self.FindRow(row)

    def GetRowName(self, row):
        """Get the name of the parameter in the specified row."""
        return self._grid.GetItemValue(row, 0)

    def GetRowValue(self, row):
        """Get the value of the parameter in the specified row."""
        row = self.ToIndex(row)
        return self._grid.GetItemValue(row, 1)

    def GetRowQuantity(self, row):
        """Get the value (with unit) of the parameter in the specified row."""
        row = self.ToIndex(row)
        name = self.GetRowName(row)
        value = self.GetRowValue(row)
        return self.utool.add_unit(name, value)

    def SetRowName(self, row, value):
        """Set the name of the parameter in the specified row."""
        self._grid.SetItemValue(row, 0, value)
        self._grid.SetItemValue(row, 2, self.utool.get_unit_label(value) or '')

    def SetRowValue(self, row, value):
        """Set the value of the parameter in the specified row."""
        row = self.ToIndex(row)
        name = self.GetRowName(row)
        group = self._params[name]
        value = group.ValueType(value, group.default(name))
        self._grid.SetItemValue(row, 1, value)
