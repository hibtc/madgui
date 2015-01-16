# encoding: utf-8
"""
Parameter input dialog as used for :class:`TwissDlg` and :class:`BeamDlg`.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from collections import OrderedDict

# GUI components
from madgui.core import wx

# internal
from madgui.widget.input import ModalDialog
from madgui.widget import listview


__all__ = [
    'Bool',
    'String',
    'Float',
    'Matrix',
    'ParamDialog',
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


def _split_value(utool, value):
    try:
        return str(utool.strip_unit(value)), utool.get_unit_label(value)
    except AttributeError:
        return str(value), ""


class ParamDialog(ModalDialog):

    """
    Modal dialog to show and edit key-value pairs.

    The parameters are displayed in 3 columns: name / value / unit.

    :ivar UnitConverter utool: tool to add/remove units from input values
    :ivar list params: all possible ParamGroups
    :ivar dict data: initial/final parameter values

    Private GUI members:

    :ivar wx.GridBagSizer _grid: sizer that contains all parameters
    """

    @classmethod
    def show_modal(cls, parent, utool, data=None):
        """Show modal dialog."""
        dlg = cls(parent=parent,
                  title=cls.title,
                  utool=utool,
                  params=cls.params,
                  data=data)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.data
        else:
            return None

    def SetData(self, utool, params, data):
        """Implements ModalDialog.SetData."""
        self.utool = utool
        self.params = OrderedDict(
            (param, group)
            for group in params
            for param in group.names()
        )
        self.data = data or {}

    def CreateContentArea(self):
        """Create sizer with content area, i.e. input fields."""
        content = wx.BoxSizer(wx.VERTICAL)
        self._grid = grid = listview.EditListCtrl(self, style=wx.LC_REPORT)
        grid.InsertColumn(0, "Parameter", width=wx.LIST_AUTOSIZE)
        grid.InsertColumn(1, "Value", width=wx.LIST_AUTOSIZE,
                          format=wx.LIST_FORMAT_RIGHT)
        grid.InsertColumn(2, "Unit")
        grid.SetMinSize(wx.Size(400, 200))
        grid.Bind(wx.EVT_CHAR, self.OnChar)
        content.Add(grid, flag=wx.ALL|wx.EXPAND, border=5)
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

    def TransferDataToWindow(self):
        """
        Update dialog with initial values.

        Implements ParamDialog.TransferDataToWindow.
        """
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        data = self.data
        for param_name in self.params:
            self.SetParamValue(param_name, data.get(param_name))
        self._grid.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self._grid.SetColumnWidth(1, wx.LIST_AUTOSIZE)

    def TransferDataFromWindow(self):
        """
        Get dictionary with all input values from dialog.

        Implements ParamDialog.TransferDataFromWindow.
        """
        grid = self._grid
        self.data = {self.GetRowName(row): self.GetRowQuantity(row)
                     for row in range(grid.GetItemCount())
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
            group = self.params[name]
            item = grid.GetItemCount()
            grid.InsertRow(item)
            self.SetRowName(item, name)
        if value is None:
            self.SetRowValue(item, None)
        else:
            self.SetRowValue(item, self.utool.strip_unit(name, value))

    def GetRowName(self, row):
        """Get the name of the parameter in the specified row."""
        return self._grid.GetItemValue(row, 0)

    def GetRowValue(self, row):
        """Get the value of the parameter in the specified row."""
        return self._grid.GetItemValue(row, 1)

    def GetRowQuantity(self, row):
        """Get the value (with unit) of the parameter in the specified row."""
        name = self.GetRowName(row)
        value = self.GetRowValue(row)
        return self.utool.add_unit(name, value)

    def SetRowName(self, row, value):
        """Set the name of the parameter in the specified row."""
        self._grid.SetItemValue(row, 0, value)
        self._grid.SetItemValue(row, 2, self.utool.get_unit_label(value) or '')

    def SetRowValue(self, row, value):
        """Set the value of the parameter in the specified row."""
        name = self.GetRowName(row)
        group = self.params[name]
        value = group.ValueType(value, group.default(name))
        self._grid.SetItemValue(row, 1, value)
