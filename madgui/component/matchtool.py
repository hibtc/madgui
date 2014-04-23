# encoding: utf-8
"""
Matching tool for a :class:`LineView` instance.
"""

# force new style imports
from __future__ import absolute_import

# 3rd party
from cern.resource.package import PackageResource

# internal
from madgui.core import wx

# exported symbols
__all__ = ['MatchTool']


class MatchTool(object):

    """
    Controller that performs matching when clicking on an element.
    """

    def __init__(self, panel):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.cid = None
        self.model = panel.view.model
        self.panel = panel
        self.view = panel.view
        # toolbar tool
        res = PackageResource('madgui.resource')
        with res.open('cursor.xpm') as xpm:
            img = wx.ImageFromStream(xpm, wx.BITMAP_TYPE_XPM)
        bmp = wx.BitmapFromImage(img)
        self.toolbar = panel.toolbar
        self.tool = panel.toolbar.AddCheckTool(
                wx.ID_ANY,
                bitmap=bmp,
                shortHelp='Beam matching',
                longHelp='Match by specifying constraints for envelope x(s), y(s).')
        panel.Bind(wx.EVT_TOOL, self.OnMatchClick, self.tool)
        panel.Bind(wx.EVT_UPDATE_UI, self.UpdateTool, self.tool)
        # setup mouse capture
        panel.hook.capture_mouse.connect(self.stop_match)

    def UpdateTool(self, event):
        """Enable/disable toolbar tool."""
        self.tool.Enable(self.model.can_match)

    def OnMatchClick(self, event):
        """Invoked when user clicks Match-Button"""
        if event.IsChecked():
            self.start_match()
        else:
            self.stop_match()

    def start_match(self):
        """Start matching mode."""
        self.panel.hook.capture_mouse()
        self.cid = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_match)
        self.constraints = []

    def stop_match(self):
        """Stop matching mode."""
        if self.cid is not None:
            self.view.figure.canvas.mpl_disconnect(self.cid)
            self.cid = None
            self.toolbar.ToggleTool(self.tool.Id, False)
        self.model.clear_constraints()

    def on_match(self, event):

        """
        Draw new constraint and perform matching.

        Invoked after the user clicks in matching mode.
        """

        axes = event.inaxes
        if axes is None:
            return
        axis = 0 if axes is self.view.axes.x else 1

        elem = self.model.element_by_position(
            event.xdata * self.view.unit.x)
        if elem is None or 'name' not in elem:
            return

        if event.button == 2:
            self.model.remove_constraint(elem)
            return
        elif event.button != 1:
            return

        orig_cursor = self.panel.GetCursor()
        wait_cursor = wx.StockCursor(wx.CURSOR_WAIT)
        self.panel.SetCursor(wait_cursor)

        # add the clicked constraint
        envelope = event.ydata*self.view.unit.y
        self.model.add_constraint(axis, elem, envelope)

        # add another constraint to hold the orthogonal axis constant
        orth_axis = 1-axis
        orth_env = self.model.get_envelope_center(elem, orth_axis)
        self.model.add_constraint(orth_axis, elem, orth_env)

        self.model.match()
        self.panel.SetCursor(orig_cursor)

