"""
Main window component for MadGUI.
"""

# Force new style imports
from __future__ import absolute_import

# GUI components
import wx
import wx.aui
from wx.py.crust import Crust
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar

# internal
from .plugin import hookcollection


class ViewPanel(wx.Panel):

    """
    Display panel for a matplotlib figure.
    """

    hook = hookcollection(
        'madgui.viewpanel', [
            'init',
            'capture_mouse'
        ])

    def __init__(self, parent, view, **kwargs):

        """
        Initialize panel and connect the view.

        Extends wx.App.__init__.
        """

        super(ViewPanel, self).__init__(parent, **kwargs)

        self.capturing = False
        self.view = view

        # couple figure to canvas
        self.canvas = Canvas(self, -1, view.figure)
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

    def OnPaint(self, event):
        """Handle redraw by painting canvas."""
        self.canvas.draw()


class Frame(wx.Frame):

    """
    Main window.
    """

    hook = hookcollection(
        'madgui.frame', [
            'init',
            'term',
            'menu'
        ])

    def __init__(self, app, show=True):

        """
        Create notebook frame.

        Extends wx.Frame.__init__.
        """

        super(Frame, self).__init__(
            parent=None,
            title='MadGUI',
            size=wx.Size(800, 600))

        self.logfolder = app.logfolder

        # create notebook
        self.panel = wx.Panel(self)
        self.notebook = wx.aui.AuiNotebook(self.panel)
        sizer = wx.BoxSizer()
        sizer.Add(self.notebook, 1, wx.EXPAND)
        self.panel.SetSizer(sizer)
        self.notebook.Bind(
            wx.aui.EVT_AUINOTEBOOK_PAGE_CLOSED,
            self.OnPageClosed,
            source=self.notebook)

        # create menubar and listen to events:
        self.SetMenuBar(self._CreateMenu())

        # Create a command tab
        self.NewCommandTab()

        # show the frame
        self.Show(show)

    def _CreateMenu(self):
        """Create a menubar."""
        # TODO: this needs to be done more dynamically. E.g. use resource
        # files and/or a plugin system to add/enable/disable menu elements.
        menubar = wx.MenuBar()
        appmenu = wx.Menu()
        menubar.Append(appmenu, '&App')
        # Create menu items
        shellitem = appmenu.Append(wx.ID_ANY,
                                   '&New prompt\tCtrl+N',
                                   'Open a new tab with a command prompt')
        self.Bind(wx.EVT_MENU, self.OnNewShell, shellitem)
        self.hook.menu(self, menubar)
        appmenu.AppendSeparator()
        appmenu.Append(wx.ID_EXIT, '&Quit', 'Quit application')
        self.Bind(wx.EVT_MENU, self.OnQuit, id=wx.ID_EXIT)
        return menubar

    def AddView(self, view, title):
        """Add new notebook tab for the view."""
        # TODO: remove this method in favor of a event based approach?
        panel = ViewPanel(self.notebook, view)
        self.notebook.AddPage(panel, title, select=True)
        view.plot()
        return panel

    def OnPageClosed(self, event):
        """A page has been closed. If it was the last, close the frame."""
        if self.notebook.GetPageCount() == 0:
            self.Close()

    def OnQuit(self, event):
        """Close the window."""
        self.Close()

    def OnNewShell(self, event):
        """Open a new command tab."""
        self.NewCommandTab()

    def NewCommandTab(self):
        """Open a new command tab."""
        # TODO: create a toolbar for this tab as well
        # TODO: prevent the first command tab from being closed (?)
        # TODO: redirect output?
        self.notebook.AddPage(Crust(self.notebook), "Command", select=True)
