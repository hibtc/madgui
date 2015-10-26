from __future__ import absolute_import
from .input import Widget

import wx


class ChoiceWidget(Widget):

    """
    Simple widget class to show a label and choices.
    """

    def CreateControls(self, window):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ctrl_label = wx.StaticText(window)
        self.ctrl_choices = wx.Choice(window)
        sizer.Add(self.ctrl_label, 0, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5)
        sizer.Add(self.ctrl_choices, 1, wx.ALL|wx.ALIGN_CENTER_VERTICAL, 5)
        return sizer

    def SetData(self, title, choices, select=None):
        """Set state of GUI elements."""
        self.ctrl_label.SetLabel(title)
        self.ctrl_choices.SetItems(choices)
        if select is None:
            self.ctrl_choices.SetSelection(0)
        else:
            self.ctrl_choices.SetStringSelection(select)

    def GetData(self):
        """Return selected choice (string)."""
        return self.ctrl_choices.GetStringSelection()

    def Validate(self):
        """Check that something is selected."""
        return self.ctrl_choices.GetSelection() != wx.NOT_FOUND
