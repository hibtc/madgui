#! /usr/bin/env python2

# language features
from __future__ import print_function

# standard library
import copy
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

from matplotlib.backends.backend_wx import _load_bitmap


# add local lib pathes
_file = inspect.getfile(inspect.currentframe())
_path = os.path.realpath(os.path.abspath(os.path.dirname(_file)))
for lib in ['event']:
    _subm = os.path.join(_path, 'lib', lib)
    if _subm not in sys.path:
        sys.path.insert(0, _subm)

# pymad
from cern import cpymad
from cern import madx

# other
from event import event


def loadJSON(filename):
    with open(filename) as f:
        return json.load(f)


class MadModel:
    """
    """

    def __init__(self, name, path=''):
        self.constraints = []
        self.name = name

        self.model = cpymad.model(name)
        self.sequence = loadJSON(os.path.join(path, name, 'sequence.json'))
        self.variables = loadJSON(os.path.join(path, name, 'vary.json'))

        # load the input file
        import hht3
        self.angle = hht3.rot_angle
        self.ex = hht3.beam_ex
        self.ey = hht3.beam_ey

        self.update()

    def element_by_position(self, pos):
        for elem in self.sequence:
            if 'at' not in elem:
                continue
            at = float(elem['at'])
            L = float(elem.get('L', 0))
            if pos >= at-L/2 and pos <= at+L/2:
                return elem
        return None

    def update(self):
        # data post processing
        self.twiss, self.summary = self.model.twiss(
                columns=['name','s', 'l','betx','bety'])

        self.s = self.twiss.s
        self.dx = np.array([math.sqrt(betx*self.ex) for betx in self.twiss.betx])
        self.dy = np.array([math.sqrt(bety*self.ey) for bety in self.twiss.bety])

    @event
    def match(self):
        # select variables: one for each constraint
        vary = []
        allvars = copy.copy(self.variables)
        for axis,elem,envelope in self.constraints:
            at = float(elem['at'])
            allowed = (v for v in allvars if float(v['at']) < at)
            try:
                v = max(allowed, key=lambda v: float(v['at']))
                vary.append(v['vary'])
                allvars.remove(v)
            except ValueError:
                # No variable in range found! Ok.
                pass

        # select constraints
        constraints = []
        for axis,elem,envelope in self.constraints:
            name = 'betx' if axis == 0 else 'bety'
            emittance = self.ex if axis == 0 else self.ey
            if isinstance(envelope, tuple):
                lower, upper = envelope
                constraints.append([
                    ('range', elem['name']),
                    (name, '>', lower*lower/emittance),
                    (name, '<', upper*upper/emittance) ])
            else:
                constraints.append({
                    'range': elem['name'],
                    name: envelope*envelope/emittance})

        r,i = self.model.match(vary=vary, constraints=constraints)
        self.update()

    def _AddConstraint(self, axis, elem, envelope):
        # TODO: two constraints on same element represent upper/lower bounds
        #lines = self._DrawConstraint(axis, elem, envelope)##EVENT
        #self.view.figure.canvas.draw()
        self.constraints.append( (axis, elem, envelope) )
        self.match()

    def _ClearConstraints(self):
        self.model.constraints = []



class MadCtrl:
    """
    """

    def __init__(self, model, panel):
        self.cid = None
        self.model = model
        self.panel = panel
        self.view = panel.view

        def toggleMatch(panel, event):
            if event.IsChecked():
                self.startMatch()
            else:
                self.stopMatch()
        panel.OnMatchClick += toggleMatch

    def startMatch(self):
        def onclick(event):
            elem = self.model.element_by_position(event.xdata)
            if elem is None or 'name' not in elem:
                return

            if event.button == 1: # left mouse
                axis = 0
            elif event.button == 3: # right mouse
                axis = 1
            elif even.button == 2:
                # delete constraint
                pass
            else:
                return
            envelope = event.ydata*self.view.yunit['scale']
            self.model._AddConstraint(axis, elem, envelope)

        self.cid = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                onclick)
        self.constraints = []

    def stopMatch(self):
        self.view.figure.canvas.mpl_disconnect(self.cid)
        self.cid = None
        self.model._ClearConstraints()


class MadView:
    """
    """

    def __init__(self, model):
        self.model = model

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

        model.match += lambda model: self.plot()


    def _DrawConstraint(self, axis, elem, envelope):
        return self.axes.plot(
                elem['at'], envelope/self.yunit['scale'], 's',
                color=self.color[axis],
                fillstyle='full', markersize=7)

    def _UpdateConstraints(self):
        # UpdateConstraints
        for lines in self.lines:
            for l in lines:
                l.remove()
        for axis,elem,envelope in self.model.constraints:
            lines = self._DrawConstraint(axis, elem, envelope)
            self.lines.append(lines)
        # self.figure.canvas.draw()


    def plot(self):
        """
        Recalculate TWISS paramaters and plot.
        """

        # data post processing
        s = self.model.s
        dx = self.model.dx
        dy = self.model.dy

        max_y = max(0, np.max(dx), np.max(dy))
        min_y = min(0, np.min(dx), np.min(dy))
        patch_y = 0.75 * min_y
        patch_h = 0.75 * (max_y - min_y)

        # plot
        self.axes.cla()

        for elem in self.model.sequence:
            if not ('type' in elem and 'at' in elem and
                    elem['type'].lower() in self.elements):
                continue
            elem_type = self.elements[elem['type'].lower()]

            if 'L' in elem and float(elem['L']) != 0:
                patch_w = float(elem['L'])
                patch_x = float(elem['at']) - patch_w/2
                self.axes.add_patch(
                        mpl.patches.Rectangle(
                            (patch_x, patch_y/self.yunit['scale']),
                            patch_w, patch_h/self.yunit['scale'],
                            alpha=0.25, color=elem_type['color']))
            else:
                patch_x = float(elem['at'])
                self.axes.vlines(
                        patch_x,
                        patch_y/self.yunit['scale'],
                        (patch_y+patch_h)/self.yunit['scale'],
                        alpha=0.5, color=elem_type['color'])

        self.axes.plot(
                s, dx/self.yunit['scale'],
                "o-", color=self.color[0], fillstyle='none',
                label="$\Delta x$")
        self.axes.plot(
                s, dy/self.yunit['scale'],
                "o-", color=self.color[1], fillstyle='none',
                label="$\Delta y$")

        self.lines = []
        self._UpdateConstraints()

        self.axes.grid(True)
        self.axes.legend(loc='upper left')
        self.axes.set_xlabel("position $s$ [m]")
        self.axes.set_ylabel("beam envelope [" + self.yunit['label'] + "]")
        self.axes.get_xaxis().set_minor_locator(
                MultipleLocator(2))
        self.axes.get_yaxis().set_minor_locator(
                MultipleLocator(0.002/self.yunit['scale']))
        self.axes.set_xlim(s[0], s[-1])

        self.figure.canvas.draw()



class ViewPanel(wx.Panel):
    """
    Container panel for a beamline plot.
    """

    ON_MATCH = wx.NewId()

    def __init__(self, parent, view, **kwargs):
        super(ViewPanel, self).__init__(parent, **kwargs)

        self.view = view

        # couple figure to backend
        self.canvas = Canvas(self, -1, view.figure)
        view.canvas = self.canvas

        self.toolbar = Toolbar(self.canvas)
        self.toolbar.Realize()

        imgpath = os.path.join(os.path.dirname(__file__), 'res', 'cursor.xpm')
        img = wx.Bitmap(imgpath)
        self.toolbar.AddCheckTool(
                self.ON_MATCH,
                img, wx.NullBitmap,
                'Beam matching',
                'Match by specifying constraints for envelope x(s), y(s).')
        wx.EVT_TOOL(self, self.ON_MATCH, self.OnMatchClick)

        # put element into sizer
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.canvas, 1, wx.EXPAND)
        sizer.Add(self.toolbar, 0 , wx.LEFT | wx.EXPAND)
        self.SetSizer(sizer)

    @event
    def OnMatchClick(self, event):
        pass

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

    def AddView(self, view, title):
        """Add plot as new page."""
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

        # path = absolute path of this file's directory
        _file = inspect.getfile(inspect.currentframe())
        self.path = os.path.realpath(os.path.abspath(os.path.dirname(_file)))

        # add submodule folder for beam+twiss imports
        subm = os.path.join(self.path, 'models', 'resdata')
        if subm not in sys.path:
            sys.path.insert(0, subm)

        # add subfolder to model pathes and create model
        cpymad.listModels.modelpaths.append(os.path.join(self.path, 'models'))

        self.frame = Frame()

        self.model = MadModel('hht3', path=subm)
        self.view = MadView(self.model)
        self.panel = self.frame.AddView(self.view, "x, y")
        self.ctrl = MadCtrl(self.model, self.panel)

        self.frame.Show(True)

        return True


# enter main business logic
if __name__ == '__main__':
    app = App()
    app.MainLoop()

