#! /usr/bin/env python2
"""
Lightweight GUI application for a MAD model.
"""

# language features
from __future__ import print_function

# standard library
import copy
import inspect
import math
import os
import sys
import json

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

# other
from event import event



def loadJSON(filename):
    """Load json file into dictionary."""
    with open(filename) as f:
        return json.load(f)


class MadModel:
    """
    Model class for cern.cpymad.model

    Improvements over cern.cpymad.model:

     - knows sequence
     - knows about variables => can perform matching

    """

    def __init__(self, name, path=''):
        """Load meta data and compute twiss variables."""
        self.constraints = []
        self.name = name
        self.model = cpymad.model(name)
        self.sequence = loadJSON(os.path.join(path, name, 'sequence.json'))
        self.variables = loadJSON(os.path.join(path, name, 'vary.json'))
        self.beam = loadJSON(os.path.join(path, name, 'beam.json'))
        self.twiss()

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        for elem in self.sequence:
            if 'at' not in elem:
                continue
            at = float(elem['at'])
            L = float(elem.get('L', 0))
            if pos >= at-L/2 and pos <= at+L/2:
                return elem
        return None

    def twiss(self):
        """Recalculate TWISS parameters."""
        self.tw, self.summary = self.model.twiss(
                columns=['name','s', 'l','betx','bety'])
        self.update()

    @event
    def update(self):
        """Perform post processing."""

        # data post processing
        self.pos = self.tw.s
        self.envx = np.array([math.sqrt(betx*self.beam['ex']) for betx in self.tw.betx])
        self.envy = np.array([math.sqrt(bety*self.beam['ey']) for bety in self.tw.bety])

    def match(self):
        """Perform matching according to current constraints."""
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
            emittance = self.beam['ex'] if axis == 0 else self.beam['ey']
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

        self.tw, self.summary = self.model.match(vary=vary, constraints=constraints)
        self.update()

    @event
    def add_constraint(self, axis, elem, envelope):
        """Add constraint and perform matching."""
        # TODO: two constraints on same element represent upper/lower bounds
        #lines = self.draw_constraint(axis, elem, envelope)##EVENT
        #self.view.figure.canvas.draw()
        self.constraints.append( (axis, elem, envelope) )
        self.match()

    @event
    def remove_constraint(self, elem):
        """Remove the constraint for elem."""
        self.constraints = [c for c in self.constraints if c[1] != elem]

    @event
    def clear_constraints(self):
        """Remove all constraints."""
        self.constraints = []



class MadCtrl:
    """
    Controller class for a ViewPanel and MadModel
    """

    def __init__(self, model, panel):
        """Initialize observer and Subscribe as observer for user events."""
        self.cid = None
        self.model = model
        self.panel = panel
        self.view = panel.view

        def toggle_match(panel, event):
            if event.IsChecked():
                self.start_match()
            else:
                self.stop_match()
        panel.OnMatchClick += toggle_match

    def start_match(self):
        """Start matching mode."""

        self.cid = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_match)
        self.constraints = []

    def on_match(self, event):
        elem = self.model.element_by_position(event.xdata)
        if elem is None or 'name' not in elem:
            return

        if event.button == 1: # left mouse
            axis = 0
        elif event.button == 3: # right mouse
            axis = 1
        elif event.button == 2:
            self.model.remove_constraint(elem)
            return
        else:
            return

        orig_cursor = self.panel.GetCursor()
        wait_cursor = wx.StockCursor(wx.CURSOR_WAIT)
        self.panel.SetCursor(wait_cursor)
        envelope = event.ydata*self.view.yunit['scale']
        self.model.add_constraint(axis, elem, envelope)
        self.panel.SetCursor(orig_cursor)

    def stop_match(self):
        """Stop matching mode."""
        self.view.figure.canvas.mpl_disconnect(self.cid)
        self.cid = None
        self.model.clear_constraints()


class MadView:
    """
    Matplotlib figure view for a MadModel.

    This is automatically updated when the model changes.

    """

    def __init__(self, model):
        """Create a matplotlib figure and register as observer."""
        self.model = model

        # create figure
        self.figure = mpl.figure.Figure()
        self.axes = self.figure.add_subplot(111)

        # plot style
        self.color = ('#8b1a0e','#5e9c36')
        self.yunit = {'label': 'mm', 'scale': 1e-3}

        # display colors for elements
        self.elements = {
            'quadrupole': {'color': '#ff0000'},
            'multipole': {'color': '#00ff00'},
            'sbend': {'color': '#0000ff'} }

        # subscribe for updates
        model.update += lambda model: self.plot()
        model.remove_constraint += lambda model, elem: self.redraw_constraints()


    def draw_constraint(self, axis, elem, envelope):
        """Draw one constraint representation in the graph."""
        return self.axes.plot(
                elem['at'], envelope/self.yunit['scale'], 's',
                color=self.color[axis],
                fillstyle='full', markersize=7)

    def redraw_constraints(self):
        """Draw all current constraints in the graph."""
        for lines in self.lines:
            for l in lines:
                l.remove()
        self.lines = []
        for axis,elem,envelope in self.model.constraints:
            lines = self.draw_constraint(axis, elem, envelope)
            self.lines.append(lines)
        self.figure.canvas.draw()


    def plot(self):
        """Plot figure and redraw canvas."""
        # data post processing
        pos = self.model.pos
        envx = self.model.envx
        envy = self.model.envy

        max_y = max(0, np.max(envx), np.max(envy))
        min_y = min(0, np.min(envx), np.min(envy))
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
                pos, envx/self.yunit['scale'],
                "o-", color=self.color[0], fillstyle='none',
                label="$\Delta x$")
        self.axes.plot(
                pos, envy/self.yunit['scale'],
                "o-", color=self.color[1], fillstyle='none',
                label="$\Delta y$")

        self.lines = []
        self.redraw_constraints()

        self.axes.grid(True)
        self.axes.legend(loc='upper left')
        self.axes.set_xlabel("position $s$ [m]")
        self.axes.set_ylabel("beam envelope [" + self.yunit['label'] + "]")
        self.axes.get_xaxis().set_minor_locator(
                MultipleLocator(2))
        self.axes.get_yaxis().set_minor_locator(
                MultipleLocator(0.002/self.yunit['scale']))
        self.axes.set_xlim(pos[0], pos[-1])

        self.figure.canvas.draw()



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
        self.toolbar.Realize()

        imgpath = os.path.join(_path, 'res', 'cursor.xpm')
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
        super(Frame, self).__init__(parent=None, title='MadGUI')
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
        self.model = MadModel('hht3', path=os.path.join(_path, 'models', 'resdata'))

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

