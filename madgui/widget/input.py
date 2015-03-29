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
    'Validator',
    'Widget',
    'Dialog',
]


# Derive from wx.PyValidator (not wx.Validator) in order to overwrite the
# virtual methods:
class Validator(wx.PyValidator):

    """
    Validator for a Widget's window.

    Delegates Validator method calls directly to the associated Widget.

    The reason to have two separate objects for Widget and Validator is that
    window.SetValidator() clones and deletes the validator object and thereby
    renders it completely useless. By encapsulating this undesirable property
    in a small delegate object, the original Widget object remains accessible
    even after installing it as validator.
    """

    def __init__(self, widget):
        """Initialize myself."""
        super(Validator, self).__init__()
        self.widget = widget

    # wx.Validator interface

    def Clone(self):
        """Clone myself."""
        return self.__class__(self.widget)

    def Validate(self, parent):
        """Check if the UI elements contain valid input."""
        return self.widget.Validate(parent)

    def TransferToWindow(self):
        """Initialize GUI elements input values."""
        return self.widget.TransferToWindow()

    def TransferFromWindow(self):
        """Read input values from GUI elements."""
        return self.widget.TransferFromWindow()


class Widget(object):

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

    # NOTE: it is a deliberate choice not to implement an __init__ function in
    # this class, so subclasses don't need the super() call. In particular,
    # self.Window is not assigned in the __init__ function! Please, don't do
    # that in subclasses either! This ensures that self.GetWindow() fails with
    # an AttributeError if no window was set, which makes it easy to
    # reinitialize member variables based on different arguments without
    # losing the memory of the Window object.

    def GetWindow(self):
        """
        Get the associated container window.

        :raises AttributeError: if the window has not been set yet.
        """
        return self.Window

    def Embed(self, window):
        """
        Assign the container window and create the controls.

        :returns: controls sizer / window
        """
        self.Window = window
        return self.CreateControls()

    def EmbedPanel(self, parent):
        """
        Assign the container window and create a panel containing the
        controls.

        :returns: the panel
        """
        panel = wx.Panel(parent)
        ctrls = self.Embed(panel)
        if isinstance(ctrls, wx.Sizer):
            sizer = ctrls
        else:
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(ctrls, 1, flag=wx.EXPAND)
        panel.SetSizer(sizer)
        return panel

    @classmethod
    def ShowModal(cls, parent, **data):
        """Show a modal dialog based on this Widget class."""
        title = data.pop('title', None)
        widget = cls(**data)
        dlg = Dialog(parent, widget, title=title)
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
        panel = self._widget.EmbedPanel(self)
        panel.SetValidator(Validator(self._widget))
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
