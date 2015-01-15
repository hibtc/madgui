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
from madgui.widget.listview import ListView, EditListCtrl


__all__ = [
    'Bool',
    'String',
    'Float',
    'Matrix',
    'ParamDialog',
]


class BaseControl(object):

    """
    Base for accessor classes for typed GUI-controls.

    The following interface must be implemented:

    :meth:`__init__` arguments (parent, stripper)
    :ivar:`Value` property to access the value of the GUI element
    :ivar:`Control` the actual GUI element (can be used to bind events)
    """

    def Destroy(self):
        self.Control.Destroy()
        self.Control = None


class BoolControl(BaseControl):

    def __init__(self, parent, col_style):
        """Create a new wx.Choice control."""
        # Use a Choice control instead of a simple CheckBox to allow logical
        # parameters to be handled just like other types of parameters
        self.Control = wx.Choice(parent, choices=["True", "False"])

    @property
    def IsValid(self):
        return True

    @property
    def Value(self):
        """Get the value of the control."""
        return self.Control.GetStringSelection() == "True"

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.Control.SetStringSelection("True" if value else "False")

    def Select(self):
        """Not used for this type of control."""
        pass


class StringControl(BaseControl):

    def __init__(self, parent, col_style):
        """Create a new wx.TextCtrl."""
        style = wx.TE_PROCESS_ENTER | wx.TE_PROCESS_TAB | wx.TE_RICH2
        style |= {wx.LIST_FORMAT_LEFT: wx.TE_LEFT,
                  wx.LIST_FORMAT_RIGHT: wx.TE_RIGHT,
                  wx.LIST_FORMAT_CENTRE : wx.TE_CENTRE}[col_style]
        self.Control = wx.TextCtrl(parent, style=style)

    @property
    def IsValid(self):
        return True

    @property
    def Value(self):
        """Get the value of the control."""
        return self.Control.GetValue()

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.Control.SetValue(str(value))

    def Select(self):
        """Select all text."""
        self.Control.SetSelection(-1,-1)


class FloatControl(StringControl):

    @property
    def IsValid(self):
        return isinstance(self.Value, float)

    @property
    def Value(self):
        """Get the value of the control."""
        value = self.Control.GetValue()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return value

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.Control.SetValue(str(value))


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

    def FormatValue(self, value):
        if value is None:
            return ''
        return str(value)


class Bool(ParamGroup):

    CreateControl = BoolControl


class String(ParamGroup):

    CreateControl = StringControl


class Float(ParamGroup):

    CreateControl = FloatControl


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


class ListCtrl(EditListCtrl):

    def __init__(self, parent, *args, **kwargs):
        EditListCtrl.__init__(self, parent, *args, **kwargs)
        self.InsertColumn(0, "Parameter", width=wx.LIST_AUTOSIZE)
        self.InsertColumn(1, "Value", width=wx.LIST_AUTOSIZE,
                          format=wx.LIST_FORMAT_RIGHT)
        self.InsertColumn(2, "Unit")
        self.data = {}

    def _GetValue(self, row, col):
        if col == 0:
            return self.GetName(row)
        if col == 1:
            value = self.GetValue(row)
            if value is None:
                return self._GetGroup(row).default(self.GetName(row))
            return value

    def _SetValue(self, row, col, value):
        if col == 0:
            self.SetName(row, value)
        if col == 1:
            self.SetValue(row, value)

    def GetName(self, row):
        return self.GetItem(row, 0).GetText()

    def GetValue(self, row):
        return self.data[self.GetName(row)]

    @property
    def utool(self):
        return self.GetParent().utool

    def GetQuantity(self, row):
        name = self.GetName(row)
        value = self.GetValue(row)
        return self.utool.add_unit(name, value)

    def SetName(self, row, value):
        old_name = self.GetName(row)
        self.SetStringItem(row, 0, str(value))
        self.SetStringItem(row, 2, self.utool.get_unit_label(value) or '')
        try:
            self.data[value] = self.data.pop(old_name)
        except KeyError:
            pass

    def SetValue(self, row, value):
        self.SetStringItem(row, 1, self._GetGroup(row).FormatValue(value))
        self.data[self.GetName(row)] = value

    def _GetGroup(self, row):
        return self.GetParent().params[self.GetName(row)]

    def _CreateEditor(self, row, col, col_style):
        if col == 0:
            # TODO: create readonly editor?
            pass
        elif col == 1:
            return self._GetGroup(row).CreateControl(self, col_style)
        elif col == 2:
            # unit can not be editted atm
            pass

    def Touch(self, row, col):
        if col == 1:
            if isinstance(self._GetGroup(row), Bool):
                self.SetValue(row, not self.GetValue(row))
                return
        super(ListCtrl, self).Touch(row, col)


class ParamDialog(ModalDialog):

    """
    Modal dialog to show and edit key-value pairs.

    :ivar UnitConverter utool: tool to add/remove units from input values
    :ivar list params: all possible ParamGroups
    :ivar dict data: initial/final parameter values
    :ivar bool readonly: read-only dialog (TODO)

    Private GUI members:

    :ivar wx.GridBagSizer _grid: sizer that contains all parameters
    """

    @classmethod
    def show_modal(cls, parent, utool, data=None, readonly=False):
        dlg = cls(parent=parent,
                  title=cls.title,
                  utool=utool,
                  params=cls.params,
                  data=data,
                  readonly=readonly)
        if dlg.ShowModal() == wx.ID_OK:
            return dlg.data
        else:
            return None

    def SetData(self, utool, params, data, readonly=False):
        """Implements ModalDialog.SetData."""
        self.utool = utool
        self.params = OrderedDict(
            (param, group)
            for group in params
            for param in group.names()
        )
        self.data = data or {}
        self.readonly = readonly

    def CreateContentArea(self):
        """Create sizer with content area, i.e. input fields."""
        content = wx.BoxSizer(wx.VERTICAL)
        self._grid = grid = ListCtrl(self, style=wx.LC_REPORT)
        grid.SetMinSize(wx.Size(400, 200))
        content.Add(grid, flag=wx.ALL|wx.EXPAND, border=5)
        return content

    def TransferDataToWindow(self):
        """
        Update dialog with initial values.

        Implements ParamDialog.TransferDataToWindow.
        """
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        data = self.data
        for param_name in self.params:
            self.SetValue(param_name, data.get(param_name))
        self._grid.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self._grid.SetColumnWidth(1, wx.LIST_AUTOSIZE)

    def TransferDataFromWindow(self):
        """
        Get dictionary with all input values from dialog.

        Implements ParamDialog.TransferDataFromWindow.
        """
        grid = self._grid
        self.data = {grid.GetName(row): grid.GetQuantity(row)
                     for row in range(grid.GetItemCount())}

    def SetValue(self, name, value):
        """
        Set a single parameter value.

        Add the parameter group if necessary.

        :param str name: parameter name
        :param value: parameter value
        :raises KeyError: if the parameter name is invalid
        """
        grid = self._grid
        item = grid.FindItem(0, name, partial=False)
        if item == -1:
            group = self.params[name]
            item = grid.GetItemCount()
            grid.InsertStringItem(item, name)
            grid.SetName(item, name)
        if value is None:
            grid.SetValue(item, None)
        else:
            grid.SetValue(item, self.utool.strip_unit(name, value))
