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
from wx.lib.mixins import listctrl as listmix

# internal
from madgui.widget.input import ModalDialog
from madgui.widget.listview import ListView


__all__ = [
    'Bool',
    'String',
    'Float',
    'Matrix',
    'ParamDialog',
]


class EditListCtrl(wx.ListCtrl, listmix.TextEditMixin):

    def __init__(self, *args, **kwargs):
        wx.ListCtrl.__init__(self, *args, **kwargs)
        listmix.TextEditMixin.__init__(self)


# wx.wxEVT_COMMAND_LIST_BEGIN_LABEL_EDIT
# wx.wxEVT_COMMAND_LIST_END_LABEL_EDIT


class BaseControl(object):

    """
    Base for accessor classes for typed GUI-controls.

    The following interface must be implemented:

    :meth:`__init__` arguments (parent, stripper)
    :ivar:`Value` property to access the value of the GUI element
    :ivar:`Control` the actual GUI element (can be used to bind events)
    """


class BoolControl(BaseControl):

    def __init__(self, parent):
        """Create a new wx.Choice control."""
        # Use a Choice control instead of a simple CheckBox to allow logical
        # parameters to be handled just like other types of parameters
        self.Control = wx.Choice(parent, choices=["Yes", "No"])

    @property
    def Value(self):
        """Get the value of the control."""
        return self.Control.GetStringSelection() == "Yes"

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.Control.SetStringSelection("Yes" if value else "No")


class StringControl(BaseControl):

    def __init__(self, parent):
        """Create a new wx.TextCtrl."""
        self.Control = wx.TextCtrl(parent)

    @property
    def Value(self):
        """Get the value of the control."""
        return self.Control.GetValue()

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.Control.SetValue(str(value))


class FloatControl(StringControl):

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


class ParamDialog(ModalDialog):

    """
    Modal dialog to show and edit key-value pairs.

    :ivar UnitConverter utool: tool to add/remove units from input values
    :ivar list params: all possible ParamGroups
    :ivar dict data: initial/final parameter values
    :ivar bool readonly: read-only dialog (TODO)

    Private members:

    :ivar list added_params: param groups that are added to the dialog

    Private GUI members:

    :ivar wx.GridBagSizer _grid: sizer that contains all parameters
    :ivar wx.Choice _ctrl_add: choice box to add new groups
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
        self.InsertInputArea(content)
        self.InsertAddFieldArea(content)
        return content

    def InsertInputArea(self, outer):
        """Create a two-column input grid, with auto sized width."""
        self.added_params = []
        self._grid = grid = EditListCtrl(self, style=wx.LC_REPORT)
        grid.SetMinSize(wx.Size(400, 200))
        grid.InsertColumn(0, "Parameter", width=wx.LIST_AUTOSIZE)
        grid.InsertColumn(1, "Value", width=wx.LIST_AUTOSIZE,
                          format=wx.LIST_FORMAT_RIGHT)
        grid.InsertColumn(2, "Unit")
        self.Bind(wx.EVT_LIST_BEGIN_LABEL_EDIT, self.OnBeginEdit, source=grid)
        self.Bind(wx.EVT_LIST_END_LABEL_EDIT, self.OnEndEdit, source=grid)
        outer.Add(grid, flag=wx.ALL|wx.EXPAND, border=5)

    def OnBeginEdit(self, event):
        pass

    def OnEndEdit(self, event):
        pass

    def InsertAddFieldArea(self, outer):
        """Create 'Add parameter' control."""
        sizer_add = wx.BoxSizer(wx.HORIZONTAL)
        self._ctrl_add = wx.Choice(self)
        self._ctrl_add.SetItems(list(self.params))
        self._ctrl_add.SetSelection(0)

        button_add = wx.Button(self, wx.ID_ADD)
        self.Bind(wx.EVT_BUTTON, self.OnButtonAdd, source=button_add)
        self.Bind(wx.EVT_UPDATE_UI, self.OnButtonAddUpdate, source=button_add)
        sizer_add.Add(self._ctrl_add)
        sizer_add.Add(button_add)
        outer.Add(sizer_add, flag=wx.ALIGN_CENTER_HORIZONTAL)

    def TransferDataToWindow(self):
        """
        Update dialog with initial values.

        Implements ParamDialog.TransferDataToWindow.
        """
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        data = self.data
        for param_name in self.params:
            try:
                self.SetValue(param_name, data.get(param_name))
            except KeyError:
                # log?
                pass
        self._grid.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self._grid.SetColumnWidth(1, wx.LIST_AUTOSIZE)

    def TransferDataFromWindow(self):
        """
        Get dictionary with all input values from dialog.

        Implements ParamDialog.TransferDataFromWindow.
        """
        self.data = {name: self.utool.add_unit(name, ctrl.Value)
                     for group in self.added_params
                     for name,ctrl in group.items()}

    def OnButtonAdd(self, event):
        """Add the selected group to the dialog."""
        self.AddParam(self._ctrl_add.GetStringSelection())
        self._grid.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self._grid.SetColumnWidth(1, wx.LIST_AUTOSIZE)
        self.Layout()
        self.Fit()

    def OnButtonAddUpdate(self, event):
        event.Enable(self._ctrl_add.GetCount() > 0)

    def SetValue(self, name, value):
        """
        Set a single parameter value.

        Add the parameter group if necessary.

        :param str name: parameter name
        :param value: parameter value
        :raises KeyError: if the parameter name is invalid
        """
        if value is None:
            return
        item = self.AddParam(name)
        grid = self._grid
        grid.SetStringItem(item, 1, str(self.utool.strip_unit(name, value)))

    def AddParam(self, param):
        """
        Add the parameter group to the dialog if not already existing.

        :param str param: parameter name
        :returns: the control that can be used to set/get values for the param
        :rtype: BaseControl
        :raises KeyError: if the parameter name is invalid
        """
        grid = self._grid
        item = grid.FindItem(0, param, partial=False)
        if item != -1:
            return item
        group = self.params[param]
        row = grid.GetItemCount()
        grid.InsertStringItem(row, param)
        grid.SetStringItem(row, 1, str(group.default(param)))
        grid.SetStringItem(row, 2, self.utool.get_unit_label(param) or '')
        # remove the choice from the 'Add' Control
        index = self._ctrl_add.FindString(param)
        self._ctrl_add.Delete(index)
        self._ctrl_add.SetSelection(0)
        return row
