# encoding: utf-8
"""
Selection tool for a :class:`LineView` instance.
"""

# force new style imports
from __future__ import absolute_import

# internal
from madgui.core import wx
from madgui.component.elementview import ElementView
from madgui.widget.table import TableDialog

# exported symbols
__all__ = ['SelectTool']


class SelectTool(object):

    """
    Controller that opens detail popups when clicking on an element.
    """

    def __init__(self, panel):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.cid = None
        self.model = panel.view.model
        self.panel = panel
        self.view = panel.view
        # toolbar tool
        bmp = wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR)
        self.toolbar = panel.toolbar
        self.tool = panel.toolbar.AddCheckTool(
            wx.ID_ANY,
            bitmap=bmp,
            shortHelp='Show info for individual elements',
            longHelp='Show info for individual elements')
        panel.Bind(wx.EVT_TOOL, self.OnSelectClick, self.tool)
        panel.Bind(wx.EVT_UPDATE_UI, self.UpdateTool, self.tool)
        # setup mouse capture
        panel.hook.capture_mouse.connect(self.stop_select)
        self._last_view = None

    def UpdateTool(self, event):
        """Enable/disable toolbar tool."""
        self.tool.Enable(self.model.can_select)

    def OnSelectClick(self, event):
        """Invoked when user clicks Mirko-Button"""
        if event.IsChecked():
            self.start_select()
        else:
            self.stop_select()

    def start_select(self):
        """Start select mode."""
        self.panel.hook.capture_mouse()
        self.cid = self.view.figure.canvas.mpl_connect(
            'button_press_event',
            self.on_select)
        self._cid_key = self.view.figure.canvas.mpl_connect(
            'key_press_event',
            self.on_key)

    def stop_select(self):
        """Stop select mode."""
        if self.cid is not None:
            self.view.figure.canvas.mpl_disconnect(self.cid)
            self.view.figure.canvas.mpl_disconnect(self._cid_key)
            self.cid = None
            self.toolbar.ToggleTool(self.tool.Id, False)

    def on_select(self, event):
        """Display a popup window with info about the selected element."""
        if event.inaxes is None:
            return
        elem = self.model.element_by_position(
            event.xdata * self.view.unit['s'])
        if elem is None or 'name' not in elem:
            return

        # By default, show info in an existing dialog. The shift/ctrl keys
        # are used to open more dialogs:
        view = self._last_view
        if view:
            pressed_keys = event.key or ''
            add_keys = ['shift', 'control']
            if any(add_key in pressed_keys for add_key in add_keys):
                view = None
            else:
                view.element_name = elem['name']
                view.update()

        if not view:
            dialog = TableDialog(self.frame)
            view = ElementView(dialog, self.model, elem['name'])
            dialog.Show()
            self._last_view = view

    def on_key(self, event):
        view = self._last_view
        if not view:
            return
        if 'left' in event.key:
            move_step = -1
        elif 'right' in event.key:
            move_step = 1
        else:
            return
        old_index = self.model.element_index_by_name(view.element_name)
        new_index = old_index + move_step
        elements = self.model.elements
        new_elem = elements[new_index % len(elements)]
        view.element_name = new_elem['name']
        view.update()

    @property
    def frame(self):
        """Return the frame this controller is associated to."""
        wnd = self.panel
        while wnd.GetParent():
            wnd = wnd.GetParent()
        return wnd
