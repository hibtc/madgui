"""
View component for the MadGUI application.
"""

# GUI
import wx

# scipy
import numpy as np
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

# 3rd party
from obsub import event
from cern.resource.package import PackageResource

# internal
from .model import Vector
from .unit import units, stripunit, unit_label
from .element_view import MadElementPopup, MadElementView


class MadLineView(object):
    """
    Matplotlib figure view for a MadModel.

    This is automatically updated when the model changes.

    """

    @classmethod
    def create(cls, model, frame):
        view = cls(model)
        frame.AddView(view, model.name)
        return view

    def __init__(self, model):
        """Create a matplotlib figure and register as observer."""
        self.model = model

        # create figure
        self.figure = mpl.figure.Figure()
        self.figure.subplots_adjust(hspace=0.00)
        axx = self.figure.add_subplot(211)
        axy = self.figure.add_subplot(212, sharex=axx)
        self.axes = Vector(axx, axy)


        # plot style
        self.unit = Vector(units.m, units.mm)
        self.curve = Vector(
            {'color': '#8b1a0e'},
            {'color': '#5e9c36'})

        self.clines = Vector(None, None)

        # display colors for elements
        self.element_types = {
            'f-quadrupole': {'color': '#ff0000'},
            'd-quadrupole': {'color': '#0000ff'},
            'f-sbend':      {'color': '#770000'},
            'd-sbend':      {'color': '#000077'},
            'multipole':    {'color': '#00ff00'},
            'solenoid':     {'color': '#555555'},
        }

        # subscribe for updates
        model.update += lambda model: self.update()
        model.remove_constraint += lambda model, elem, axis=None: self.redraw_constraints()
        model.clear_constraints += lambda model: self.redraw_constraints()
        model.add_constraint += lambda model, axis, elem, envelope: self.redraw_constraints()


    def draw_constraint(self, axis, elem, envelope):
        """Draw one constraint representation in the graph."""
        return self.axes[axis].plot(
            stripunit(elem['at'], self.unit.x),
            stripunit(envelope, self.unit.y),
            's',
            color=self.curve[axis]['color'],
            fillstyle='full',
            markersize=7)

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

    def get_element_type(self, elem):
        """Return the element type name used for properties like coloring."""
        if 'type' not in elem or 'at' not in elem:
            return None
        type_name = elem['type'].lower()
        focussing = None
        if type_name == 'quadrupole':
            i = self.model.get_element_index(elem)
            focussing = stripunit(self.model.tw.k1l[i]) > 0
        elif type_name == 'sbend':
            i = self.model.get_element_index(elem)
            focussing = stripunit(self.model.tw.angle[i]) > 0
        if focussing is not None:
            if focussing:
                type_name = 'f-' + type_name
            else:
                type_name = 'd-' + type_name
        return self.element_types.get(type_name)

    def update(self):
        if self.clines.x is None or self.clines.y is None:
            self.plot()
            return
        self.clines.x.set_ydata(stripunit(self.model.env.x, self.unit.y))
        self.clines.y.set_ydata(stripunit(self.model.env.y, self.unit.y))
        self.figure.canvas.draw()

    @event
    def plot(self):
        """Plot figure and redraw canvas."""
        # data post processing
        pos = self.model.pos
        envx, envy = self.model.env

        max_env = Vector(np.max(envx), np.max(envy))
        patch_h = Vector(0.75*stripunit(max_env.x, self.unit.y),
                         0.75*stripunit(max_env.y, self.unit.y))

        # plot
        self.axes.x.cla()
        self.axes.y.cla()

        # disable labels on x-axis
        for label in self.axes.x.xaxis.get_ticklabels():
            label.set_visible(False)
        self.axes.y.yaxis.get_ticklabels()[0].set_visible(False)

        for elem in self.model.sequence:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue

            if 'L' in elem and stripunit(elem['L']) != 0:
                patch_w = stripunit(elem['L'], self.unit.x)
                patch_x = stripunit(elem['at'], self.unit.x) - patch_w/2
                self.axes.x.add_patch(
                        mpl.patches.Rectangle(
                            (patch_x, 0),
                            patch_w, patch_h.x,
                            alpha=0.5, color=elem_type['color']))
                self.axes.y.add_patch(
                        mpl.patches.Rectangle(
                            (patch_x, 0),
                            patch_w, patch_h.y,
                            alpha=0.5, color=elem_type['color']))
            else:
                patch_x = stripunit(elem['at'], self.unit.x)
                self.axes.x.vlines(
                        patch_x, 0,
                        patch_h.x,
                        alpha=0.5, color=elem_type['color'])
                self.axes.y.vlines(
                        patch_x, 0,
                        patch_h.y,
                        alpha=0.5, color=elem_type['color'])

        self.clines = Vector(
            self.axes.x.plot(
                stripunit(pos, self.unit.x), stripunit(envx, self.unit.y),
                "o-", color=self.curve.x['color'], fillstyle='none',
                label="$\Delta x$")[0],
            self.axes.y.plot(
                stripunit(pos, self.unit.x), stripunit(envy, self.unit.y),
                "o-", color=self.curve.y['color'], fillstyle='none',
                label="$\Delta y$")[0])

        self.lines = []
        self.redraw_constraints()

        # self.axes.legend(loc='upper left')
        self.axes.y.set_xlabel("position $s$ [m]")

        for axis_index, axis_name in enumerate(['x', 'y']):
            self.axes[axis_index].grid(True)
            self.axes[axis_index].get_xaxis().set_minor_locator(
                MultipleLocator(2))
            self.axes[axis_index].get_yaxis().set_minor_locator(
                MultipleLocator(2))
            self.axes[axis_index].set_xlim(stripunit(pos[0], self.unit.x),
                                           stripunit(pos[-1], self.unit.x))
            self.axes[axis_index].set_ylabel(r'$\Delta %s$ %s' % (
                axis_name, unit_label(self.unit.y)))
            self.axes[axis_index].set_ylim(0)

        # invert y-axis:
        self.axes.y.set_ylim(self.axes.y.get_ylim()[::-1])
        self.figure.canvas.draw()

class MirkoView(object):
    """
    View component to display mirko envelope for comparison.

    Draws the mirko envelope into a MadLineView figure whenever that figure
    is replotted.

    """
    ON_MIRKO = wx.NewId()

    @classmethod
    def connect_toolbar(cls, panel):
        view = panel.view
        mirko = cls(view.model, view)
        bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_HOME, wx.ART_TOOLBAR)
        panel.toolbar.AddCheckTool(
                cls.ON_MIRKO,
                bitmap=bmp,
                shortHelp='Show MIRKO envelope',
                longHelp='Show MIRKO envelope for comparison. The envelope is computed for the default parameters.')
        wx.EVT_TOOL(panel, cls.ON_MIRKO, mirko.OnMirkoClick)

    def OnMirkoClick(self, event):
        """Invoked when user clicks Mirko-Button"""
        self.visible = event.IsChecked()

    def __init__(self, model, view):
        """
        Create a mirko envelope display component.

        The envelope is NOT visible by default.

        """
        self.model = model
        self.view = view
        self.lines = None
        def onplot(_):
            if self.visible:
                self._plot()
        self.view.plot += onplot

    @property
    def visible(self):
        """Visibility state of the envelope."""
        return self.lines is not None

    @visible.setter
    def visible(self, value):
        if value:
            self._plot()
        else:
            self._remove()

    def _plot(self):
        """Plot the envelope into the figure."""
        model = self.model.model
        optic = model._mdef['optics'][model._active['optic']]
        if 'test' not in optic:
            # TODO: log error
            return

        with model.mdata.get_by_dict(optic['test']).filename() as f:
            aenv = units.mm * np.loadtxt(f, usecols=(0,1,2))
        envdata = Vector(
            Vector(aenv[:,0], aenv[:,1]),
            Vector(aenv[:,0], aenv[:,2]))

        self.lines = Vector(
            self.view.axes.x.plot(stripunit(envdata.x.x, self.view.unit.x),
                                  stripunit(envdata.x.y, self.view.unit.y),
                                  'k'),
            self.view.axes.y.plot(stripunit(envdata.y.x, self.view.unit.x),
                                  stripunit(envdata.y.y, self.view.unit.y),
                                  'k'))
        self.view.figure.canvas.draw()

    def _remove(self):
        """Remove the envelope from the figure."""
        if self.lines:
            # self.view.axes.x.lines.remove(self.lines.x)
            # self.view.axes.y.lines.remove(self.lines.y)
            for l in self.lines.x:
                l.remove()
            for l in self.lines.y:
                l.remove()
            self.lines = None
            self.view.figure.canvas.draw()


class MadCtrl(object):
    """
    Controller class for a ViewPanel and MadModel

    """
    ON_MATCH = wx.NewId()
    ON_SELECT = wx.NewId()

    @classmethod
    def create(cls, viewpanel):
        return cls(viewpanel.view.model, viewpanel)


    def __init__(self, model, panel):
        """Initialize and subscribe as observer for user events."""
        self.cid_match = None
        self.cid_select = None
        self.model = model
        self.panel = panel
        self.view = panel.view

        # match
        res = PackageResource(__package__)
        with res.open(['resource', 'cursor.xpm']) as xpm:
            img = wx.ImageFromStream(xpm, wx.BITMAP_TYPE_XPM)
        bmp = wx.BitmapFromImage(img)
        panel.toolbar.AddCheckTool(
                self.ON_MATCH,
                bitmap=bmp,
                shortHelp='Beam matching',
                longHelp='Match by specifying constraints for envelope x(s), y(s).')
        wx.EVT_TOOL(panel, self.ON_MATCH, self.OnMatchClick)

        # select
        bmp = wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR)
        panel.toolbar.AddCheckTool(
                self.ON_SELECT,
                bitmap=bmp,
                shortHelp='Show info for individual elements',
                longHelp='Show info for individual elements')
        wx.EVT_TOOL(panel, self.ON_SELECT, self.OnSelectClick)


    def OnSelectClick(self, event):
        """Invoked when user clicks Mirko-Button"""
        if event.IsChecked():
            self.start_select()
        else:
            self.stop_select()

    def start_select(self):
        """Start select mode."""
        self.cid_select = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_select)

    def stop_select(self):
        """Stop select mode."""
        if self.cid_select is not None:
            self.view.figure.canvas.mpl_disconnect(self.cid_select)
            self.cid_select = None

    def OnMatchClick(self, event):
        """Invoked when user clicks Match-Button"""
        if event.IsChecked():
            self.start_match()
        else:
            self.stop_match()

    def start_match(self):
        """Start matching mode."""
        self.cid_match = self.view.figure.canvas.mpl_connect(
                'button_press_event',
                self.on_match)
        self.constraints = []

    def stop_match(self):
        """Stop matching mode."""
        if self.cid_match is not None:
            self.view.figure.canvas.mpl_disconnect(self.cid_match)
            self.cid_match = None
        self.model.clear_constraints()

    @property
    def frame(self):
        wnd = self.panel
        while wnd.GetParent():
            wnd = wnd.GetParent()
        return wnd

    def on_select(self, event):
        """Display a popup window with info about the selected element."""
        elem = self.model.element_by_position_center(
            event.xdata * self.view.unit.x)
        if elem is None or 'name' not in elem:
            return
        popup = MadElementPopup(self.frame)
        element_view = MadElementView(popup, self.model, elem['name'])
        popup.Show()


    def on_match(self, event):
        axes = event.inaxes
        if axes is None:
            return
        axis = 0 if axes is self.view.axes.x else 1

        elem = self.model.element_by_position_center(
            event.xdata * self.view.unit.x)
        if elem is None or 'name' not in elem:
            return

        if event.button == 2:
            self.model.remove_constraint(elem)
            return
        elif event.button != 1:
            return

        orig_cursor = self.panel.GetCursor()
        wait_cursor = wx.StockCursor(wx.CURSOR_WAIT)
        self.panel.SetCursor(wait_cursor)

        # add the clicked constraint
        envelope = event.ydata*self.view.unit.y
        self.model.add_constraint(axis, elem, envelope)

        # add another constraint to hold the orthogonal axis constant
        orth_axis = 1-axis
        orth_env = self.model.get_envelope_center(elem, orth_axis)
        self.model.add_constraint(orth_axis, elem, orth_env)

        self.model.match()
        self.panel.SetCursor(orig_cursor)

