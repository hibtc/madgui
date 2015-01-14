"""
List view widget.
"""

from madgui.core import wx

from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin


class ListView(wx.ListView, ListCtrlAutoWidthMixin):

    def __init__(self, *args, **kwargs):
        wx.ListView.__init__(self, *args, **kwargs)
        ListCtrlAutoWidthMixin.__init__(self)
        self.setResizeColumn(0)
