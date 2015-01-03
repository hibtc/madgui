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


__all__ = ['truncate',
           'Bool',
           'String',
           'Float',
           'Matrix',
           'ParamDialog']


# TWISS parameters are organized in 'groups': if the user accesses any one
# parameter, all parameters of the corresponding group will be shown in a
# defined layout.
# This is IMHO the easiest and somewhat convenient way to make all parameters
# optional but retain a semantic grouping.


def truncate(s, w):
    return (s[:w-2] + '..') if len(s) > w else s


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

    def layout(self):
        """Get the layout as tuple (rows, columns)."""
        return (1, len(self._defaults))


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

    def layout(self):
        """Overrides ParamGroup.layout."""
        return self._layout


# TODO: class Vector(Float)
# unlike Matrix this represents a single MAD-X parameter of type ARRAY.


class ParamDialog(ModalDialog):

    """
    Modal dialog to show and edit key-value pairs.

    :ivar UnitConverter utool: tool to add/remove units from input values
    :ivar list params: all possible ParamGroups
    :ivar dict data: initial/final parameter values
    :ivar bool readonly: read-only dialog (TODO)

    Private members:

    :ivar list _groups: param groups that are added to the dialog

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
        self.params = params
        self.data = data or {}
        self.readonly = readonly

    def CreateControls(self):

        """Implements ModalDialog.CreateControls."""

        outer = wx.BoxSizer(wx.VERTICAL)

        # Create a two-column grid, with auto sized width
        self._grid = grid = wx.GridBagSizer(vgap=5, hgap=5)
        grid.SetFlexibleDirection(wx.HORIZONTAL)
        grid.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_NONE)  # fixed height
        self._groups = []
        outer.Add(self._grid, flag=wx.ALL|wx.EXPAND, border=5)

        # Add parameter control
        sizer_add = wx.BoxSizer(wx.HORIZONTAL)
        ctrl_add = self._ctrl_add = wx.Choice(self)
        ctrl_add.SetItems([truncate(", ".join(group.names()), 20)
                           for group in self.params])
        for i, group in enumerate(self.params):
            ctrl_add.SetClientData(i, group)
        ctrl_add.SetSelection(0)

        button_add = wx.Button(self, wx.ID_ADD)
        self.Bind(wx.EVT_BUTTON, self.OnButtonAdd, source=button_add)
        sizer_add.Add(ctrl_add)
        sizer_add.Add(button_add)
        outer.Add(sizer_add, flag=wx.ALIGN_CENTER_HORIZONTAL)

        # buttons
        outer.Add(self.CreateButtonSizer(), flag=wx.ALIGN_CENTER_HORIZONTAL)

        # insert values from initial data
        self.SetSizer(outer)
        self.TransferDataToWindow()

    def TransferDataToWindow(self):
        """
        Update dialog with initial values.

        Implements ParamDialog.TransferDataToWindow.
        """
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        data = self.data
        for param_group in self.params:
            for param_name in param_group.names():
                try:
                    self.SetValue(param_name, data.get(param_name))
                except KeyError:
                    # log?
                    pass

    def TransferDataFromWindow(self):
        """
        Get dictionary with all input values from dialog.

        Implements ParamDialog.TransferDataFromWindow.
        """
        self.data = {name: self.utool.add_unit(name, ctrl.Value)
                     for group in self._groups
                     for name,ctrl in group.items()}

    def OnButtonAdd(self, event):
        """Add the selected group to the dialog."""
        index = self._ctrl_add.GetSelection()
        group = self._ctrl_add.GetClientData(index)
        self.AddGroup(group)
        self.Layout()
        self.Fit()

    def AddGroup(self, group):
        """
        Add a parameter group to the dialog using the default values.

        :param ParamGroup group: parameter group metadata
        :returns: mapping of all parameter controls in the group
        :rtype: dict
        """
        rows, cols = group.layout()
        row_offs = self._grid.GetRows()
        # on windows, this doesn't happen automatically, when adding
        # new items to the grid:
        self._grid.SetRows(row_offs + rows)
        # create and insert individual controls
        controls = {}
        self._groups.append(controls)
        for i, param in enumerate(group.names()):
            row = row_offs + i/cols
            col = 2*(i%cols)
            unit_label = self.utool.get_unit_label(param)
            if unit_label:
                text = '{} {}: '.format(param, unit_label)
            else:
                text = '{}: '.format(param)
            label = wx.StaticText(self, label=text)
            input = group.CreateControl(self)
            input.Value = group.default(param)
            self._grid.Add(label,
                           wx.GBPosition(row, col),
                           flag=wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
            self._grid.Add(input.Control,
                           wx.GBPosition(row, col+1),
                           flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
            controls[param] = input
        # remove the choice from the 'Add' Control
        for i in range(self._ctrl_add.GetCount()):
            if group == self._ctrl_add.GetClientData(i):
                self._ctrl_add.Delete(i)
                # TODO: check if count == 0
                self._ctrl_add.SetSelection(0)
                break
        return controls

    def SetValue(self, name, value):
        """
        Set a single parameter value.

        Add the parameter group if necessary.

        :param str name: parameter name
        :param value: parameter value
        :raises KeyError: if the parameter name is invalid
        """
        if value is not None:
            self.AddParam(name).Value = self.utool.strip_unit(name, value)

    def AddParam(self, param_name):
        """
        Add the parameter group to the dialog if not already existing.

        :param str param_name: parameter name
        :returns: the control that can be used to set/get values for the param
        :rtype: BaseControl
        :raises KeyError: if the parameter name is invalid
        """
        for group in self._groups:
            if param_name in group:
                return group[param_name]
        for group in self.params:
            if param_name in group.names():
                return self.AddGroup(group)[param_name]
        raise KeyError(param_name)
