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

        Abstract method.
        """
        raise NotImplementedError()

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

    def CreateButtonSizer(self):
        """
        Create 'Ok'/'Cancel' button sizer.

        Use this method from within :meth:`CreateControls`
        """
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = self.CreateOkButton()
        buttons.Add(ok_button)
        ok_button.SetDefault()
        buttons.Add(self.CreateCancelButton())
        return buttons

    def CreateOkButton(self):
        """Create 'Ok' button."""
        button = wx.Button(self, wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOk, source=button)
        return button

    def CreateCancelButton(self):
        """Create 'Cancel' button."""
        button = wx.Button(self, wx.ID_CANCEL)
        self.Bind(wx.EVT_BUTTON, self.OnButtonCancel, source=button)
        return button

    def OnButtonOk(self, event):
        """Confirm current selection and close dialog."""
        self.TransferDataFromWindow()
        self.EndModal(wx.ID_OK)

    def OnButtonCancel(self, event):
        """Cancel the dialog."""
        self.EndModal(wx.ID_CANCEL)
