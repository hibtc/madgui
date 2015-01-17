# encoding: utf-8
"""
Generic utilities for input dialogs.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx

# exported symbols
__all__ = ['ModalDialog']


class ModalDialog(wx.Dialog):

    """
    Simple base class for generic input dialogs.

    The following virtual functions need to be overriden:

    :meth:`SetData` initialize data member from outside
    :meth:`CreateControls` create GUI elements
    :meth:`TransferDataToWindow` set dialog values
    :meth:`TransferDataFromWindow` read 

    Class variables:

    :cvar int Style: dialog style
    """

    Style = wx.DEFAULT_DIALOG_STYLE|wx.SIMPLE_BORDER

    def __init__(self, parent, title, **kwargs):
        """Initialize dialog and create GUI elements."""
        super(ModalDialog, self).__init__(
            parent=parent,
            title=title,
            style=self.Style)
        self.SetData(**kwargs)
        self.CreateControls()
        self.TransferDataToWindow()
        self.Layout()
        self.Fit()
        self.Centre()

    def SetData(self, **kwargs):
        """
        Initialize the data member of the dialog.

        Abstract method.
        """
        raise NotImplementedError()

    def CreateControls(self):
        """
        Create GUI elements.
        """
        outer = wx.BoxSizer(wx.VERTICAL)
        inner = wx.BoxSizer(wx.VERTICAL)
        outer.Add(inner, 1, flag=wx.ALL|wx.EXPAND, border=5)
        self.AddContentArea(inner)
        self.AddButtonArea(inner)
        self.SetSizer(outer)

    def AddContentArea(self, outer):
        """
        Create sizer with content area, i.e. input fields.
        """
        outer.Add(self.CreateContentArea(), 1,
                  flag=wx.ALL|wx.EXPAND,
                  border=5)

    def AddButtonArea(self, outer):
        """
        Add button area.
        """
        outer.Add(wx.StaticLine(self, style=wx.LI_HORIZONTAL),
                  flag=wx.ALL|wx.EXPAND,
                  border=5)
        outer.Add(self.CreateButtonSizer(),
                  flag=wx.ALL|wx.ALIGN_CENTER_HORIZONTAL,
                  border=5)

    def TransferDataToWindow(self):
        """
        Initialize GUI elements input values.

        Abstract method.
        """
        raise NotImplementedError()

    def TransferDataFromWindow(self):
        """
        Read input values from GUI elements.

        Abstract method.
        """
        raise NotImplementedError()

    def CreateContentArea(self):
        """
        Create a sizer with the content area controls.

        Abstract method.
        """
        raise NotImplementedError()

    def CreateButtonSizer(self):
        """
        Create 'Ok'/'Cancel' button sizer.

        Use this method from within :meth:`CreateControls`
        """
        buttons = wx.StdDialogButtonSizer()
        ok_button = self.CreateOkButton()
        buttons.AddButton(ok_button)
        ok_button.SetDefault()
        buttons.AddButton(self.CreateCancelButton())
        buttons.Realize()
        return buttons

    def CreateOkButton(self):
        """Create 'Ok' button."""
        button = wx.Button(self, wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.ApplyDialog, source=button)
        return button

    def CreateCancelButton(self):
        """Create 'Cancel' button."""
        button = wx.Button(self, wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self.CancelDialog, source=button)
        return button

    def ApplyDialog(self, event=None):
        """Confirm current selection and close dialog."""
        self.TransferDataFromWindow()
        self.EndModal(wx.ID_OK)

    def CancelDialog(self, event=None):
        """Cancel the dialog."""
        self.EndModal(wx.ID_CANCEL)
