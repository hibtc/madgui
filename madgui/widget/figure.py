# encoding: utf-8
"""
Matplotlib figure panel component.
"""

# force new style imports
from __future__ import absolute_import

# GUI components
from madgui.core import wx
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar

# internal
from madgui.core.plugin import HookCollection
from madgui.util.common import ivar

# exported symbols
__all__ = ['FigurePanel']


class FigurePanel(wx.Panel):

    """
    Display panel for a matplotlib figure.
    """

    hook = ivar(HookCollection,
                init='madgui.widget.figure.init',
                capture_mouse=None)

    def __init__(self, parent, view, **kwargs):

        """
        Initialize panel and connect the view.

        Extends wx.App.__init__.
        """

        super(FigurePanel, self).__init__(parent, **kwargs)

        self.capturing = False
        self.view = view

        # couple figure to canvas
        self.canvas = Canvas(self, -1, view.figure.figure)
        view.canvas = self.canvas

        # create a toolbar
        self.toolbar = Toolbar(self.canvas)
        self.hook.init(self)
        self.toolbar.Realize()

        # put elements into sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        sizer.Add(self.toolbar, 0 , wx.LEFT | wx.EXPAND)
        self.SetSizer(sizer)

        # setup mouse capturing
        self.hook.capture_mouse.connect(self.on_capture_mouse)
        self.toolbar.Bind(wx.EVT_TOOL,
                          self.on_zoom_or_pan,
                          id=self.toolbar.wx_ids['Zoom'])
        self.toolbar.Bind(wx.EVT_TOOL,
                          self.on_zoom_or_pan,
                          id=self.toolbar.wx_ids['Pan'])

    def on_zoom_or_pan(self, event):
        """Capture mouse, after Zoom/Pan tools were clicked."""
        if event.IsChecked():
            self.capturing = True
            self.hook.capture_mouse()
            self.capturing = False
        event.Skip()

    def on_capture_mouse(self):
        """Disable Zoom/Pan tools when someone captures the mouse."""
        if self.capturing:
            return
        zoom_id = self.toolbar.wx_ids['Zoom']
        if self.toolbar.GetToolState(zoom_id):
            self.toolbar.zoom()
            self.toolbar.ToggleTool(zoom_id, False)
        pan_id = self.toolbar.wx_ids['Pan']
        if self.toolbar.GetToolState(pan_id):
            self.toolbar.pan()
            self.toolbar.ToggleTool(pan_id, False)
