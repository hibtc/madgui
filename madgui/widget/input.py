# encoding: utf-8
"""
Generic utilities for input dialogs.
"""

# TODO: instructions

# force new style imports
from __future__ import absolute_import

# standard library
import functools

# GUI components
from madgui.core import wx

# exported symbols
__all__ = [
    'CancelAction',
    'Cancellable',
    'Widget',
    'ShowModal',
    'Dialog',
]


class CancelAction(RuntimeError):
    """Raised when user pressed 'Cancel' in a dialog."""
    pass


def Cancellable(func):
    """
    Decorator for functions that represent actions cancellable by the user.

    Returns a wrapper that catches any :class:`CancelAction` exception.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CancelAction:
            return None
    return wrapper


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
        return self.widget.Validate()

    def TransferToWindow(self):
        """Initialize GUI elements input values."""
        pass

    def TransferFromWindow(self):
        """Read input values from GUI elements."""
        pass


class Widget(object):

    """
    Manage a group of related controls.

    This is an abstract base class. Subclasses should override the following
    members:

    - CreateControls
    - GetData / SetData
    - Validate (wx.Validator API)
    - Title (as attribute)
    """

    # TODO: change GetData/SetData data model; separate list of choices etc. from result state
    # TODO: allow to query dialog with single utility function
    # TODO: 'manage' defaults to True only for historical reasons. It should
    # be False by default.

    def __init__(self, parent, manage=True, embed=False):
        """Initialize widget and create controls."""
        try:
            self.Parent = parent.ContentArea
            embed = True
        except AttributeError:
            self.Parent = parent
        self.Create(self.Parent, manage=manage, embed=embed)

    # utility mixins

    @property
    def CanEmbed(self):
        return self.__class__.CreateControl == Widget.CreateControl

    @property
    def TopLevelWindow(self):
        """The top level window for this widget."""
        return self.Parent.GetTopLevelParent()

    def Query(self, *args, **kwargs):
        """
        Show modal dialog and return input data.

        :raises CancelAction: if the user cancelled the dialog.
        """
        self.SetData(*args, **kwargs)
        self.TopLevelWindow.SetTitle(self.Title)
        ShowModal(self.TopLevelWindow)
        return self.GetData()

    def ApplyDialog(self, event=None):
        """Confirm current selection and close dialog."""
        event = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK)
        wx.PostEvent(self.Parent, event)

    # overrides

    Title = 'MadGUI'

    def Create(self, parent, manage=True, embed=False):
        if embed and self.CanEmbed:
            self.Control = parent
            sizer = self.Sizer = self.CreateControls(self.Control)
        else:
            self.Control = self.CreateControl(parent)
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(self.Control, 1, wx.EXPAND)
        if manage:
            parent.SetSizer(sizer)
        self.Control.SetValidator(Validator(self))

    def CreateControl(self, parent):
        panel = wx.Panel(parent)
        sizer = self.Sizer = self.CreateControls(panel)
        panel.SetSizer(sizer)
        return panel

    def CreateControls(self, parent):
        """Create controls, return their container (panel or sizer)."""
        raise NotImplementedError()

    def Validate(self):
        """Check if the UI elements contain valid input."""
        return True

    def SetData(self, *args, **kwargs):
        """Initialize GUI elements input values."""
        raise NotImplementedError()

    def GetData(self):
        """Read input values from GUI elements."""
        raise NotImplementedError()


def ShowModal(dialog):
    """Show a modal dialog and destroy it when finished."""
    dialog.Layout()
    dialog.Fit()
    dialog.Centre()
    retcode = dialog.ShowModal()
    if retcode == wx.ID_CANCEL:
        raise CancelAction
    return retcode


class Dialog(wx.Dialog):

    """
    Simple generic input dialog showing a single :class:`Widget`.

    Class variables:

    :cvar int Style: dialog style
    """

    Style = wx.DEFAULT_DIALOG_STYLE|wx.SIMPLE_BORDER

    def __init__(self, parent, style=None):
        """Initialize dialog and create GUI elements."""
        if style is None:
            style = self.Style
        super(Dialog, self).__init__(
            parent=parent,
            style=style)
        self.CreateControls()

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
        # Nesting a panel is necessary since automatic validation uses only
        # the validators of *child* windows.
        self.ContentArea = wx.Panel(self)
        return self.ContentArea

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
