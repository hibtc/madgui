# encoding: utf-8
"""
Generic utilities for input dialogs.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx

# exported symbols
__all__ = [
    '',
    'Widget',
    'Dialog',
]


class Widget(wx.PyValidator):

    """
    Manage a group of related controls.

    This is an abstract base class. Subclasses must provide the following
    members:

    - CreateControls
    - Validate / TransferToWindow / TransferFromWindow (wx.Validator API)
    - title (as attribute)

    By keeping this functionality separate from an actual window class such as
    wx.Dialog or wx.Frame, a control group can easily be embedded into other
    windows or higher order control groups.
    """

    def __init__(self, **data):
        """Initialize myself."""
        super(Widget, self).__init__()
        self._data = data
        self.Init(**data)

    def Init(self, **data):
        """Initialize member variables."""
        for k, v in data.items():
            setattr(self, k, v)

    @classmethod
    def ShowModal(cls, parent, **data):
        """Show a modal dialog based on this Widget class."""
        title = data.pop('title', None)
        validator = cls(**data)
        dlg = Dialog(parent, validator, title=title)
        try:
            return dlg.ShowModal()
        finally:
            dlg.Destroy()

    def ApplyDialog(self, event=None):
        """Confirm current selection and close dialog."""
        event = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK)
        wx.PostEvent(self.GetWindow(), event)

    def CreateControls(self):
        """Create controls, return their container (panel or sizer)."""
        raise NotImplementedError()

    # wx.Validator interface

    def Clone(self):
        """Clone myself."""
        return self.__class__(**self._data)

    def Validate(self, parent):
        """Check if the UI elements contain valid input."""
        return True

    def TransferToWindow(self):
        """Initialize GUI elements input values."""
        raise NotImplementedError()

    def TransferFromWindow(self):
        """Read input values from GUI elements."""
        raise NotImplementedError()


class Dialog(wx.Dialog):

    """
    Simple generic input dialog showing a single :class:`Widget`.

    Class variables:

    :cvar int Style: dialog style
    """

    Style = wx.DEFAULT_DIALOG_STYLE|wx.SIMPLE_BORDER

    def __init__(self, parent, widget, title=None, style=None):
        """Initialize dialog and create GUI elements."""
        if title is None:
            title = widget.title
        if style is None:
            style = self.Style
        super(Dialog, self).__init__(
            parent=parent,
            title=title,
            style=style)
        self._widget = widget
        self.CreateControls()
        self.Layout()
        self.Fit()
        self.Centre()

    def CreateControls(self):
        """Create GUI elements."""
        outer = wx.BoxSizer(wx.VERTICAL)
        inner = wx.BoxSizer(wx.VERTICAL)
        outer.Add(inner, 1, flag=wx.ALL|wx.EXPAND, border=5)
        self.AddContentArea(inner)
        self.AddButtonArea(inner)
        self.SetSizer(outer)

    def AddContentArea(self, outer):
        """Create sizer with content area, i.e. input fields."""
        outer.Add(self.CreateContentArea(), 1,
                  flag=wx.ALL|wx.EXPAND,
                  border=5)

    def AddButtonArea(self, outer):
        """Add button area."""
        outer.Add(wx.StaticLine(self, style=wx.LI_HORIZONTAL),
                  flag=wx.ALL|wx.EXPAND,
                  border=5)
        outer.Add(self.CreateButtonArea(),
                  flag=wx.ALL|wx.ALIGN_CENTER_HORIZONTAL,
                  border=5)

    def CreateContentArea(self):
        """Create a sizer with the content area controls."""
        # Nesting a panel is necessary since TransferData[From/To]Window will
        # only use the validators of *child* windows
        panel = wx.Panel(self)
        panel.SetValidator(self._widget)
        # SetValidator stores a clone of the object passed to it, which must
        # be obtained via panel.GetValidator().
        sizer = panel.GetValidator().CreateControls()
        panel.SetSizer(sizer)
        # The corresponding C++ object is destroyed at this point. Let's make
        # this explicit:
        del self._widget
        return panel

    def CreateButtonArea(self):
        """Create 'Ok'/'Cancel' button sizer."""
        buttons = wx.StdDialogButtonSizer()
        ok_button = wx.Button(self, wx.ID_OK)
        ok_button.SetDefault()
        self.Bind(wx.EVT_UPDATE_UI, self.OnUpdateOk, ok_button)
        buttons.AddButton(ok_button)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL))
        buttons.Realize()
        return buttons

    def OnUpdateOk(self, event):
        """Disable OK button in case of invalid input."""
        event.Enable(self.Validate())
