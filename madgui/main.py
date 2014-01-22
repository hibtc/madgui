"""
Lightweight GUI application for a MAD model.
"""

from __future__ import absolute_import

# wxpython
import wxversion
wxversion.ensureMinimal('2.8')
import wx
import wx.aui
from wx.py.crust import Crust

# scipy
import matplotlib as mpl
import numpy as np

# use wxAgg as backend:
mpl.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar
from matplotlib.backends.backend_wx import _load_bitmap

# standard library
import os

# 3rdparty libraries
from cern import cpymad
from obsub import event
from cern.resource.package import PackageResource
from cern.cpymad.model_locator import MergedModelLocator

# app components
from .model import MadModel, Vector
from .line_view import MadLineView, MirkoView
from .controller import MadCtrl


logfolder = os.path.join(os.path.expanduser('~'), '.madgui')
try:
    os.makedirs(logfolder)
except OSError:
    # directory already exists. the exist_ok parameter exists not until
    # python3.2
    pass


#----------------------------------------
# GUI classes
#----------------------------------------

assert issubclass(wx.Panel, object)  # we want new style classes!
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


assert issubclass(wx.Frame, object)  # we want new style classes!
class Frame(wx.Frame):
    """
    Main window.
    """
    def __init__(self):
        """Create notebook frame."""
        super(Frame, self).__init__(parent=None, title='MadGUI', size=wx.Size(800,600))
        self.panel = wx.Panel(self)
        self.notebook = wx.aui.AuiNotebook(self.panel)
        sizer = wx.BoxSizer()
        sizer.Add(self.notebook, 1, wx.EXPAND)
        self.panel.SetSizer(sizer)

        self.notebook.Bind(
            wx.aui.EVT_AUINOTEBOOK_PAGE_CLOSED,
            self.OnPageClosed,
            source=self.notebook)

        # TODO: create a toolbar for this tab as well
        # TODO: prevent this tab from being closed (?)
        self.notebook.AddPage(Crust(self.notebook), "Command", select=True)

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


assert issubclass(wx.App, object)  # we want new style classes!
class App(wx.App):
    """
    Highest level application logic.
    """
    def load_model(self, mdata, **kwargs):
        """Instanciate a new MadModel."""
        res = mdata.repository.get()
        model = MadModel(
            name=mdata.name,
            model=cpymad.model(mdata, **kwargs),
            sequence=res.json('sequence.json'))
        return model

    def show_model(self, madmodel):
        view = MadLineView(madmodel)
        panel = self.frame.AddView(view, madmodel.name)
        mirko = MirkoView(madmodel, view)

        # create controller
        MadCtrl(madmodel, panel, mirko)

    def open_model(self, parent=None):
        from .openmodel import OpenModelDlg
        dlg = OpenModelDlg(parent)
        success = dlg.ShowModal() == wx.ID_OK
        if success:
            model = dlg.data
            h = os.path.join(logfolder, "%s.madx" % model.name)
            self.show_model(self.load_model(model, histfile=h))
        dlg.Destroy()
        return success

    def OnInit(self):
        """Create the main window and insert the custom frame."""
        # setup view
        self.frame = Frame()
        if not self.open_model():
            return False

        # show frame and enter main loop
        self.frame.Show(True)
        return True

def main():
    """Invoke GUI application."""
    # TODO: add command line options (via docopt!)
    app = App(
        redirect=False,
        filename=os.path.join(logfolder, 'error.log'))
    app.MainLoop()

if __name__ == '__main__':
    main()
