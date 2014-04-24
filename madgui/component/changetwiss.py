"""
Dialog to set TWISS parameters.
"""

# force new style imports
from __future__ import absolute_import

# standard library
from collections import OrderedDict

# internal
from madgui.core import wx


__all__ = ['TwissDialog']


# TWISS parameters are organized in 'groups': if the user accesses any one
# parameter, all parameters of the corresponding group will be shown in a
# defined layout.
# This is IMHO the easiest and somewhat convenient way to make all parameters
# optional but retain a semantic grouping.


def truncate(s, w):
    return (s[:w-2] + '..') if len(s) > w else s


class BoolControl(object):

    def __init__(self, parent):
        """Create a new wx.Choice control."""
        # Use a Choice control instead of a simple CheckBox to allow logical
        # parameters to be handled just like other types of parameters
        self.control = wx.Choice(parent, choices=["Yes", "No"])

    @property
    def Value(self):
        """Get the value of the control."""
        return self.control.GetStringSelection() == "Yes"

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.control.SetStringSelection("Yes" if value else "No")


class StringControl(object):

    def __init__(self, parent):
        """Create a new wx.TextCtrl."""
        self.control = wx.TextCtrl(parent)

    @property
    def Value(self):
        """Get the value of the control."""
        return self.control.GetValue()

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.control.SetValue(str(value))


class FloatControl(StringControl):

    @property
    def Value(self):
        """Get the value of the control."""
        value = self.control.GetValue()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return value

    @Value.setter
    def Value(self, value):
        """Set the value of the control."""
        self.control.SetValue(str(value))


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

    control = BoolControl


class String(ParamGroup):

    control = StringControl


class Float(ParamGroup):

    control = FloatControl


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


class TwissDialog(wx.Dialog):

    """
    Dialog to show key-value pairs.
    """

    # TODO:
    # - exclude more parameters (for most of these parameters, I actually
    #   don't know whether it makes sense to include them here)
    # - for excluded parameters show info string
    # - dynamically determine better default values
    params = [
        Float(betx=0, bety=0),
        Float(alfx=0, alfy=0),
        Float(mux=0, muy=0),
        Float(x=0, y=0),
        Float(t=0),
        Float(pt=0),
        Float(px=0, py=0),
        Float(dpx=0, dpy=0),
        Float(wx=0, wy=0),
        Float(phix=0, phiy=0),
        Float(dmux=0, dmuy=0),
        Float(ddx=0, ddy=0),
        Float(ddpx=0, ddpy=0),
        Matrix(r=[(0, 0),
                  (0, 0)]),
        Float(energy=0),
        Bool(chrom=True),
        String(file=""),
        String(save=""),
        String(table="twiss"),
        String(beta0=""),
        Matrix(re=[(1, 0, 0, 0, 0, 0),
                   (0, 1, 0, 0, 0, 0),
                   (0, 0, 1, 0, 0, 0),
                   (0, 0, 0, 1, 0, 0),
                   (0, 0, 0, 0, 1, 0),
                   (0, 0, 0, 0, 0, 1)]),
        Bool(centre=True),
        Bool(ripken=True),
        Bool(sectormap=True),
        String(sectortable=""),
        String(sectorfile="sectormap"),
        Bool(rmatrix=True),
        #String(sequence=""),   # line/sequence is passed by madgui
        #String(line=""),       # line/sequence is passed by madgui
        #String(range=""),      # range is passed by madgui
        String(useorbit=""),
        String(keeporbit=""),
        Float(tolerance=0),
        String(deltap=""),
        #Bool(notable=True),    # madgui always needs table
    ]

    @classmethod
    def connect_toolbar(cls, panel):
        model = panel.view.model
        bmp = wx.ArtProvider.GetBitmap(wx.ART_LIST_VIEW, wx.ART_TOOLBAR)
        tool = panel.toolbar.AddSimpleTool(
                wx.ID_ANY,
                bitmap=bmp,
                shortHelpString='Set TWISS initial conditions.',
                longHelpString='Set TWISS initial conditions.')
        def OnClick(event):
            dlg = cls(panel, model.twiss_args)
            if dlg.ShowModal() == wx.ID_OK:
                model.twiss_args = dlg.data
                model.twiss()
        panel.Bind(wx.EVT_TOOL, OnClick, tool)

    def __init__(self, parent, data, readonly=False):
        """
        Create an empty popup window.

        Extends wx.Dialog.__init__.
        """
        super(TwissDialog, self).__init__(
            parent=parent,
            style=wx.DEFAULT_DIALOG_STYLE|wx.SIMPLE_BORDER)
        self.data = data or {}
        self._readonly = readonly
        self.CreateControls()

    def CreateControls(self):

        outer = wx.BoxSizer(wx.VERTICAL)

        # Create a two-column grid, with auto sized width
        self._grid = grid = wx.GridBagSizer(vgap=5, hgap=5)
        grid.SetFlexibleDirection(wx.HORIZONTAL)
        grid.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_NONE)  # fixed height
        self._groups = []
        outer.Add(self._grid, flag=wx.ALL|wx.EXPAND, border=5)

        # Add parameter control
        sizer_add = wx.BoxSizer(wx.HORIZONTAL)
        self.ctrl_add = ctrl_add = wx.Choice(self)
        ctrl_add.SetItems([truncate(", ".join(group.names()), 20)
                           for group in self.params])
        for i, group in enumerate(self.params):
            ctrl_add.SetClientData(i, group)
        self.ctrl_add.SetSelection(0)

        button_add = wx.Button(self, wx.ID_ADD)
        sizer_add.Add(ctrl_add)
        sizer_add.Add(button_add)
        outer.Add(sizer_add, flag=wx.ALIGN_CENTER_HORIZONTAL)

        # buttons
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        button_ok = wx.Button(self, wx.ID_OK)
        button_cancel = wx.Button(self, wx.ID_CANCEL)
        buttons.Add(button_ok)
        buttons.Add(button_cancel)
        outer.Add(buttons, flag=wx.ALIGN_CENTER_HORIZONTAL)

        # insert values from initial data
        self.SetSizer(outer)
        self.TransferDataToWindow()

        # register for events
        self.Bind(wx.EVT_BUTTON, self.OnButtonAdd, source=button_add)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOk, source=button_ok)
        self.Bind(wx.EVT_BUTTON, self.OnButtonCancel, source=button_cancel)

        self.Layout()
        self.Fit()
        self.Centre()

    def TransferDataToWindow(self):
        """Update dialog with initial values."""
        # iterating over `params` (rather than `data`) enforces a particular
        # order in the GUI:
        data = self.data
        for param_group in self.params:
            for param_name in param_group.names():
                try:
                    self.SetValue(param_name, data.get(param_name))
                except KeyError:
                    #
                    pass

    def TransferDataFromWindow(self):
        """Get dictionary with all input values from dialog."""
        self.data = {name: ctrl.Value
                     for group in self._groups
                     for name,ctrl in group.items()}

    def OnButtonOk(self, event):
        """Confirm current selection and close dialog."""
        self.TransferDataFromWindow()
        self.EndModal(wx.ID_OK)

    def OnButtonCancel(self, event):
        """Cancel the dialog."""
        self.EndModal(wx.ID_CANCEL)

    def OnButtonAdd(self, event):
        """Add the selected group to the dialog."""
        index = self.ctrl_add.GetSelection()
        group = self.ctrl_add.GetClientData(index)
        self.AddGroup(group)
        self.Layout()
        self.Fit()

    def AddGroup(self, group):
        """Add a parameter group to the dialog using the default values."""
        rows, cols = group.layout()
        row_offs = self._grid.GetRows()
        # create and insert individual controls
        controls = {}
        self._groups.append(controls)
        for i, param in enumerate(group.names()):
            row = row_offs + i/cols
            col = 2*(i%cols)
            label = wx.StaticText(self, label=param+':')
            input = group.control(self)
            input.Value = group.default(param)
            self._grid.Add(label,
                           wx.GBPosition(row, col),
                           flag=wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
            self._grid.Add(input.control,
                           wx.GBPosition(row, col+1),
                           flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL)
            controls[param] = input
        # remove the choice from the 'Add' Control
        for i in range(self.ctrl_add.GetCount()):
            if group == self.ctrl_add.GetClientData(i):
                self.ctrl_add.Delete(i)
                # TODO: check if count == 0
                self.ctrl_add.SetSelection(0)
                break
        return controls

    def SetValue(self, name, value):
        """
        Set a single parameter value.

        Add the parameter group if necessary.
        """
        if value is not None:
            self.AddParam(name).Value = value

    def AddParam(self, param_name):
        for group in self._groups:
            if param_name in group:
                return group[param_name]
        for group in self.params:
            if param_name in group.names():
                return self.AddGroup(group)[param_name]
        raise KeyError(param_name)
