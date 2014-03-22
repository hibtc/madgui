# GUI components
import wx
import wx.aui
from wx.py.crust import Crust
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar

# project internal
from .plugin import hookcollection


#----------------------------------------
# GUI classes
#----------------------------------------

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

        self.view = view

        # couple figure to backend
        self.canvas = Canvas(self, -1, view.figure)
        view.canvas = self.canvas

        # create a toolbar
        self.toolbar = Toolbar(self.canvas)
        self.hook.init(self)
        self.toolbar.Realize()

        # put element into sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        sizer.Add(self.toolbar, 0 , wx.LEFT | wx.EXPAND)
        self.SetSizer(sizer)

        self.capturing = False
        self.hook.capture_mouse.connect(self.on_capture_mouse)

        self.toolbar.Bind(wx.EVT_TOOL,
                          self.on_zoom_or_pan,
                          id=self.toolbar.wx_ids['Zoom'])
        self.toolbar.Bind(wx.EVT_TOOL,
                          self.on_zoom_or_pan,
                          id=self.toolbar.wx_ids['Pan'])

    def on_zoom_or_pan(self, event):
        if event.IsChecked():
            self.capturing = True
            self.hook.capture_mouse()
            self.capturing = False
        event.Skip()

    def on_capture_mouse(self):
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

    @classmethod
    def create(cls, app):
        frame = cls(app.logfolder)
        frame.Show(True)
        return frame

    def __init__(self, logfolder):

        """
        Create notebook frame.

        Extends wx.Frame.__init__.
        """

        super(Frame, self).__init__(
            parent=None,
            title='MadGUI',
            size=wx.Size(800, 600))

        self.logfolder = logfolder

        # create and listen to events:
        self.SetMenuBar(self._CreateMenu())

        # main panel
        self.panel = wx.Panel(self)

        # create notebook
        self.notebook = wx.aui.AuiNotebook(self.panel)
        sizer = wx.BoxSizer()
        sizer.Add(self.notebook, 1, wx.EXPAND)
        self.panel.SetSizer(sizer)

        self.notebook.Bind(
            wx.aui.EVT_AUINOTEBOOK_PAGE_CLOSED,
            self.OnPageClosed,
            source=self.notebook)

        # Create a command tab
        self.NewCommandTab()

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
        panel = ViewPanel(self.notebook, view)
        self.notebook.AddPage(panel, title, select=True)
        view.plot()
        return panel

    def OnPageClosed(self, event):
        """A page has been closed. If it was the last, close the frame."""
        if self.notebook.GetPageCount() == 0:
            self.Close()

    def OnQuit(self, event):
        self.Close()

    def OnNewShell(self, event):
        self.NewCommandTab()

    def NewCommandTab(self):
        # TODO: create a toolbar for this tab as well
        # TODO: prevent this tab from being closed (?)
        self.notebook.AddPage(Crust(self.notebook), "Command", select=True)
