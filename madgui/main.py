"""
Lightweight GUI application for a MAD model.
"""

from __future__ import absolute_import

# wxpython
import wxversion
wxversion.ensureMinimal('2.8')
import wx
import wx.aui

# scipy
import matplotlib as mpl

# use wxAgg as backend:
mpl.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar
from matplotlib.backends.backend_wx import _load_bitmap

# standard library
import json
import os

# 3rdparty libraries
from cern import cpymad
from obsub import event

# app components
from .model import MadModel
from .view import MadView
from .controller import MadCtrl


def _open_resource(filename, module=__name__, path="."):
    try:
        return open(os.path.join(path, filename))
    except IOError:
        import pkg_resources
        return pkg_resources.resource_stream(module, filename)

def _load_resource(filename, module=__name__, path="."):
    with _open_resource(filename, module, path) as f:
        return f.read()

def _loadJSON(filename, module=__name__, path="."):
    """Load json file into dictionary."""
    with _open_resource(filename) as f:
        return json.load(f)


#----------------------------------------
# GUI classes
#----------------------------------------

assert issubclass(wx.Panel, object)  # we want new style classes!
class ViewPanel(wx.Panel):
    """
    Display panel view for a MadView figure.
    """
    ON_MATCH = wx.NewId()

    def __init__(self, parent, view, **kwargs):
        """Initialize panel and connect the view."""
        super(ViewPanel, self).__init__(parent, **kwargs)

        self.view = view

        # couple figure to backend
        self.canvas = Canvas(self, -1, view.figure)
        view.canvas = self.canvas

        self.toolbar = Toolbar(self.canvas)

        with _open_resource(os.path.join('resource', 'cursor.xpm')) as xpm:
            img = wx.ImageFromStream(xpm, wx.BITMAP_TYPE_XPM)
        bmp = wx.BitmapFromImage(img)
        self.toolbar.AddCheckTool(
                self.ON_MATCH,
                bitmap=bmp,
                shortHelp='Beam matching',
                longHelp='Match by specifying constraints for envelope x(s), y(s).')
        wx.EVT_TOOL(self, self.ON_MATCH, self.OnMatchClick)
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

    def AddView(self, view, title):
        """Add new notebook tab for the view."""
        panel = ViewPanel(self.notebook, view)
        self.notebook.AddPage(panel, title)
        view.plot()
        return panel


assert issubclass(wx.App, object)  # we want new style classes!
class App(wx.App):
    """
    Highest level application logic.
    """
    def load_model(self, name, **kwargs):
        """Instanciate a new MadModel."""
        path=os.path.join('models', 'resdata', name)
        return MadModel(
            name=name,
            model=cpymad.model(name, **kwargs),
            sequence=_loadJSON(os.path.join(path, 'sequence.json')),
            variables=_loadJSON(os.path.join(path, 'vary.json')),
            beam=_loadJSON(os.path.join(path, 'beam.json')))

    def OnInit(self):
        """Create the main window and insert the custom frame."""
        # add subfolder to model pathes and create model
        cpymad.listModels.modelpaths.append(os.path.join('models'))
        self.model = self.load_model('hht3', histfile="log/hist.madx")

        # setup view
        self.frame = Frame()
        view = MadView(self.model)
        panel = self.frame.AddView(view, "x, y")

        # create controller
        self.ctrl = MadCtrl(self.model, panel)

        # show frame and enter main loop
        self.frame.Show(True)
        return True

def main():
    """Invoke GUI application."""
    app = App()
    app.MainLoop()

