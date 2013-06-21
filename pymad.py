#! /usr/bin/env python2

# language features
from __future__ import print_function

# standard library
import inspect
import math
import os
import sys
import json
from math import pi

# wxpython
import wxversion
wxversion.ensureMinimal('2.8')
import wx
import wx.aui

# scipy
import numpy as np
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

# use wxAgg as backend:
mpl.use('WXAgg')
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as Toolbar

# pymad
from cern import cpymad
from cern import madx



class MadFigure:
    """
    """

    def __init__(self, model, sequence):
        self.model = model
        self.sequence = sequence

        # load the input file
        import hht3
        self.angle = hht3.rot_angle
        self.ex = hht3.beam_ex
        self.ey = hht3.beam_ey

        # create figure
        self.figure = mpl.figure.Figure()
        self.axes = self.figure.add_subplot(111)

        # plot style
        self.color = ('#8b1a0e','#5e9c36')
        self.yunit = {'label': 'mm', 'scale': 1e-3}

        #
        self.elements = {
            'quadrupole': {'color': '#ff0000'},
            'multipole': {'color': '#00ff00'},
            'sbend': {'color': '#0000ff'} }

        # define onclick handler for graph
        def onclick(event):
            self.paint()
            # print('button=%d, x=%d, y=%d, xdata=%f, ydata=%f'%(
            #   event.button, event.x, event.y, event.xdata, event.ydata))

        # self.cid = self.figure.canvas.mpl_connect('button_press_event', onclick)


    def paint(self):
        """
        Recalculate TWISS paramaters and plot.
        """

        # data post processing
        tw, summary = self.model.twiss(
                columns=['name','s', 'l','betx','bety','x','dx','y','dy'])

        s = tw.s
        dx = np.array([math.sqrt(betx*self.ex) for betx in tw.betx])
        dy = np.array([math.sqrt(bety*self.ey) for bety in tw.bety])

        max_y = max(0, np.max(dx), np.max(dy))
        min_y = min(0, np.min(dx), np.min(dy))
        patch_y = 0.75 * min_y
        patch_h = 0.75 * (max_y - min_y)

        # plot
        self.axes.cla()

        for elem in self.sequence:
            if not ('type' in elem and "L" in elem and "at" in elem and
                    elem['type'].lower() in self.elements):
                continue
            elem_type = self.elements[elem['type'].lower()]

            patch_w = float(elem['L'])
            patch_x = float(elem['at']) - patch_w/2
            self.axes.add_patch(
                    mpl.patches.Rectangle(
                        (patch_x, patch_y/self.yunit['scale']),
                        patch_w, patch_h/self.yunit['scale'],
                        alpha=0.5, color=elem_type['color']))

        self.axes.plot(
                tw.s, dx/self.yunit['scale'],
                "o-", color=self.color[0], fillstyle='none',
                label="$\Delta x$")
        self.axes.plot(
                tw.s, dy/self.yunit['scale'],
                "o-", color=self.color[1], fillstyle='none',
                label="$\Delta y$")

        self.axes.grid(True)
        self.axes.legend(loc='upper left')
        self.axes.set_xlabel("position $s$ [m]")
        self.axes.set_ylabel("beam envelope [" + self.yunit['label'] + "]")
        self.axes.get_xaxis().set_minor_locator(
                MultipleLocator(2))
        self.axes.get_yaxis().set_minor_locator(
                MultipleLocator(0.002/self.yunit['scale']))
        self.axes.set_xlim(s[0], s[-1])


class PlotPanel(wx.Panel):
    def __init__(self, parent, figure, **kwargs):
        super(PlotPanel, self).__init__(parent, **kwargs)

        # couple figure to backend
        self.figure = figure
        self.canvas = Canvas(self, -1, self.figure)
        self.toolbar = Toolbar(self.canvas)
        self.toolbar.Realize()

        # put element into sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        sizer.Add(self.toolbar, 0 , wx.LEFT | wx.EXPAND)
        self.SetSizer(sizer)

    def OnPaint(self, event):
        self.canvas.draw()



class Frame(wx.Frame):
    """
    Main window.
    """

    def __init__(self):
        """Constructor."""

        super(Frame, self).__init__(parent=None, title='MadGUI')

        # add notebook
        self.panel = wx.Panel(self)
        self.notebook = wx.aui.AuiNotebook(self.panel)
        sizer = wx.BoxSizer()
        sizer.Add(self.notebook, 1, wx.EXPAND)
        self.panel.SetSizer(sizer)

    def AddFigure(self, figure, title):
        """Add plot as new page."""
        panel = PlotPanel(self.notebook, figure.figure)
        self.notebook.AddPage(panel, title)
        figure.paint()
        return panel


class App(wx.App):
    """
    Highest level application logic.
    """

    def OnInit(self):
        """Create the main window and insert the custom frame."""

        # here = absolute path of this file's directory
        here = os.path.realpath(os.path.abspath(os.path.dirname(inspect.getfile(inspect.currentframe()))))

        # add submodule folder for beam+twiss imports
        subm = os.path.join(here, 'models', 'resdata')
        if subm not in sys.path:
            sys.path.insert(0, subm)

        # add subfolder to model pathes and create model
        cpymad.listModels.modelpathes.append(os.path.join(here, 'models'))
        self.model = cpymad.model('hht3')
        with open(os.path.join(subm, 'hht3', 'sequence.json')) as f:
            self.sequence = json.load(f)
        self.mad = MadFigure(self.model, self.sequence)

        self.frame = Frame()
        self.frame.AddFigure(self.mad, "x, y")
        self.frame.Show(True)

        return True


# enter main business logic
if __name__ == '__main__':
    app = App(0)
    app.MainLoop()
