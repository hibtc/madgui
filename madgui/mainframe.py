# standard library
import os

# wxwidgets
import wx
import wx.aui
from wx.py.crust import Crust

# matplotlib
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar
from matplotlib.backends.backend_wx import _load_bitmap

# 3rd party
from obsub import event
from cern import cpymad
from cern.resource.package import PackageResource

# project internal
from .model import MadModel, Vector
from .line_view import MadLineView, MirkoView
from .controller import MadCtrl


#----------------------------------------
# GUI classes
#----------------------------------------

class ViewPanel(wx.Panel):
    """
    Display panel view for a MadLineView figure.
    """
    ON_MATCH = wx.NewId()
    ON_MIRKO = wx.NewId()
    ON_OPEN = wx.NewId()
    ON_SELECT = wx.NewId()

    def __init__(self, parent, view, **kwargs):
        """Initialize panel and connect the view."""
        super(ViewPanel, self).__init__(parent, **kwargs)

        self.view = view

        # couple figure to backend
        self.canvas = Canvas(self, -1, view.figure)
        view.canvas = self.canvas

        self.toolbar = Toolbar(self.canvas)

        res = PackageResource(__package__)

        with res.open(['resource', 'cursor.xpm']) as xpm:
            img = wx.ImageFromStream(xpm, wx.BITMAP_TYPE_XPM)
        bmp = wx.BitmapFromImage(img)
        self.toolbar.AddCheckTool(
                self.ON_MATCH,
                bitmap=bmp,
                shortHelp='Beam matching',
                longHelp='Match by specifying constraints for envelope x(s), y(s).')
        wx.EVT_TOOL(self, self.ON_MATCH, self.OnMatchClick)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR)
        self.toolbar.AddCheckTool(
                self.ON_SELECT,
                bitmap=bmp,
                shortHelp='Show info for individual elements',
                longHelp='Show info for individual elements')
        wx.EVT_TOOL(self, self.ON_SELECT, self.OnSelectClick)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_HOME, wx.ART_TOOLBAR)
        self.toolbar.AddCheckTool(
                self.ON_MIRKO,
                bitmap=bmp,
                shortHelp='Show MIRKO envelope',
                longHelp='Show MIRKO envelope for comparison. The envelope is computed for the default parameters.')
        wx.EVT_TOOL(self, self.ON_MIRKO, self.OnMirkoClick)

        # TODO: this should not be within the notebook page:
        bmp = wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR)
        self.toolbar.AddSimpleTool(
            self.ON_OPEN,
            bitmap=bmp,
            shortHelpString='Open another model',
            longHelpString='Open another model')
        wx.EVT_TOOL(self, self.ON_OPEN, self.OnOpenClick)

        self.toolbar.Realize()

        # put element into sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        sizer.Add(self.toolbar, 0 , wx.LEFT | wx.EXPAND)
        self.SetSizer(sizer)

    @event
    def OnMatchClick(self, event):
        """Invoked when user clicks Match-Button"""
        pass

    @event
    def OnMirkoClick(self, event):
        """Invoked when user clicks Mirko-Button"""
        pass

    @event
    def OnSelectClick(self, event):
        """Invoked when user clicks Mirko-Button"""
        pass

    @event
    def OnOpenClick(self, event):
        """Invoked when user clicks Open-Model Button."""
        wx.GetApp().open_model(self.GetParent())

    def OnPaint(self, event):
        """Handle redraw by painting canvas."""
        self.canvas.draw()


class Frame(wx.Frame):
    """
    Main window.
    """

    ID_SHELL = wx.NewId()
    ID_MODEL = wx.NewId()

    @classmethod
    def create(cls, app):
        frame = cls(app.logfolder)
        frame.Show(True)
        return frame

    def __init__(self, logfolder):
        """Create notebook frame."""
        super(Frame, self).__init__(
            parent=None,
            title='MadGUI',
            size=wx.Size(800,600))

        self.logfolder = logfolder

        # create and listen to events:
        self.SetMenuBar(self._CreateMenu())
        self.Bind(wx.EVT_MENU, self.OnOpenModel, id=self.ID_MODEL)
        self.Bind(wx.EVT_MENU, self.OnNewShell, id=self.ID_SHELL)
        self.Bind(wx.EVT_MENU, self.OnQuit, id=wx.ID_EXIT)

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
        appmenu.Append(self.ID_SHELL, '&New prompt\tCtrl+N', 'Open a new tab with a command prompt')
        appmenu.Append(self.ID_MODEL, '&Open model\tCtrl+O', 'Open another model in a new tab')
        appmenu.AppendSeparator()
        appmenu.Append(wx.ID_EXIT, '&Quit', 'Quit application')
        menubar.Append(appmenu, '&App')
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

    #----------------------------------------
    # New command tab
    #----------------------------------------
    def OnNewShell(self, event):
        self.NewCommandTab()

    def NewCommandTab(self):
        # TODO: create a toolbar for this tab as well
        # TODO: prevent this tab from being closed (?)
        self.notebook.AddPage(Crust(self.notebook), "Command", select=True)


    #----------------------------------------
    # Open new model:
    #----------------------------------------
    def load_model(self, mdata, **kwargs):
        """Instanciate a new MadModel."""
        res = mdata.repository.get()
        model = MadModel(
            name=mdata.name,
            model=cpymad.model(mdata, **kwargs),
            sequence=res.yaml('sequence.yml'))
        return model

    def show_model(self, madmodel):
        view = MadLineView(madmodel)
        panel = self.AddView(view, madmodel.name)
        mirko = MirkoView(madmodel, view)

        # create controller
        MadCtrl(madmodel, panel, mirko)

    def open_model(self):
        from .openmodel import OpenModelDlg
        dlg = OpenModelDlg(self)
        success = dlg.ShowModal() == wx.ID_OK
        if success:
            model = dlg.data
            h = os.path.join(self.logfolder, "%s.madx" % model.name)
            self.show_model(self.load_model(model, histfile=h))
        dlg.Destroy()
        return success

    def OnOpenModel(self, event):
        self.open_model()

