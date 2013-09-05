#! /usr/bin/env python2
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
import inspect
import os
import sys

# add local lib pathes
_file = inspect.getfile(inspect.currentframe())
_path = os.path.realpath(os.path.abspath(os.path.dirname(_file)))
for lib in ['event']:
    _subm = os.path.join(_path, 'lib', lib)
    if _subm not in sys.path:
        sys.path.insert(0, _subm)

# pymad
from cern import cpymad

# app components
from model import MadModel
from view import MadView
from controller import MadCtrl

# other
from event import event


#----------------------------------------
# GUI classes
#----------------------------------------

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

        imgpath = os.path.join(_path, 'res', 'cursor.xpm')
        img = wx.Bitmap(imgpath, wx.BITMAP_TYPE_XPM)
        self.toolbar.AddCheckTool(
                self.ON_MATCH,
                bitmap=img,
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


class App(wx.App):
    """
    Highest level application logic.
    """

    def OnInit(self):
        """Create the main window and insert the custom frame."""
        # add subfolder to model pathes and create model
        cpymad.listModels.modelpaths.append(os.path.join(_path, 'models'))
        self.model = MadModel('hht3',
                path=os.path.join(_path, 'models', 'resdata'),
                histfile="hist.madx")

        # setup view
        self.frame = Frame()
        view = MadView(self.model)
        panel = self.frame.AddView(view, "x, y")

        # create controller
        self.ctrl = MadCtrl(self.model, panel)

        # show frame and enter main loop
        self.frame.Show(True)
        return True

# enter main business logic
if __name__ == '__main__':
    app = App()
    app.MainLoop()

