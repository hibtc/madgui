# encoding: utf-8
"""
View component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# scipy
import numpy as np
from matplotlib.ticker import AutoMinorLocator

# internal
import madgui.core
from madgui.util.common import ivar
from madgui.util.plugin import HookCollection
from madgui.util.unit import units, stripunit, unit_label, raw_label

import matplotlib
import matplotlib.figure

# exported symbols
__all__ = ['TwissView']


def _clear_ax(ax):
    """Clear a single :class:`matplotlib.axes.Axes` instance."""
    ax.cla()
    ax.grid(True)
    ax.get_xaxis().set_minor_locator(AutoMinorLocator())
    ax.get_yaxis().set_minor_locator(AutoMinorLocator())


class FigurePair(object):

    """
    A figure composed of two subplots with shared s-axis.

    :ivar matplotlib.figure.Figure figure: composed figure
    :ivar matplotlib.axes.Axes axx: upper subplot
    :ivar matplotlib.axes.Axes axy: lower subplot
    """

    def __init__(self):
        """Create an empty matplotlib figure with two subplots."""
        self.figure = figure = matplotlib.figure.Figure()
        self.axx = axx = figure.add_subplot(211)
        self.axy = axy = figure.add_subplot(212, sharex=axx)

    @property
    def canvas(self):
        """Get the canvas."""
        return self.figure.canvas

    def draw(self):
        """Draw the figure on its canvas."""
        self.figure.canvas.draw()

    def set_slabel(self, label):
        """Set label on the s axis."""
        self.axy.set_xlabel(label)

    def start_plot(self):
        """Start a fresh plot."""
        _clear_ax(self.axx)
        _clear_ax(self.axy)


class TwissCurve(object):

    """Plot a TWISS parameter curve into a 2D figure."""

    @classmethod
    def from_view(cls, view):
        """Create a :class:`TwissCurve` inside a :class:`TwissView`."""
        style = view.config['curve_style']
        curve = cls(view.model, view.unit, style)
        # register for update events
        view.hook.plot_ax.connect(curve.plot_ax)
        view.hook.update_ax.connect(curve.update_ax)
        return curve

    def __init__(self, model, unit, style):
        """Store meta data."""
        self._model = model
        self._unit = unit
        self._style = style
        self._clines = {}

    def plot_ax(self, axes, name):
        """Make one subplot."""
        style = self._style[name[-1]]
        abscissa = self.get_float_data('s')
        ordinate = self.get_float_data(name)
        axes.set_xlim(abscissa[0], abscissa[-1])
        self._clines[name] = axes.plot(abscissa, ordinate, **style)[0]

    def update_ax(self, axes, name):
        """Update the y values for one subplot."""
        self._clines[name].set_ydata(self.get_float_data(name))

    def get_float_data(self, name):
        """Get a float data vector."""
        return stripunit(self._model.tw[name], self._unit[name])


class TwissView(object):

    """Instanciate an FigurePair + XYCurve(Envelope)."""

    hook = ivar(HookCollection,
                plot=None,
                update_ax=None,
                plot_ax=None)

    @classmethod
    def create(cls, model, frame, basename='env'):
        """Create a new view panel as a page in the notebook frame."""
        view = cls(model, basename, frame.app.conf['line_view'])
        frame.AddView(view, model.name)
        return view

    def __init__(self, model, basename, line_view_config):

        # create figure
        self.figure = figure = FigurePair()
        self.model = model
        self.config = line_view_config

        self.sname = sname = 's'
        self.xname = xname = basename + 'x'
        self.yname = yname = basename + 'y'
        self.axes = {xname: figure.axx,
                     yname: figure.axy}
        self._conjugate = {xname: yname, yname: xname}

        # plot style
        self._label = line_view_config['label']
        unit_names = line_view_config['unit']
        self.unit = unit = {col: getattr(units, unit_names[col])
                            for col in [sname, xname, yname]}

        # create a curve as first plotter hook
        TwissCurve.from_view(self)

        # subscribe for updates
        model.hook.update.connect(self.update)

    def update(self):
        self.hook.update_ax(self.figure.axx, self.xname)
        self.hook.update_ax(self.figure.axy, self.yname)
        self.figure.draw()

    def get_label(self, name):
        return self._label[name] + ' ' + unit_label(self.unit[name])

    def plot(self):
        fig = self.figure
        axx = fig.axx
        axy = fig.axy
        sname, xname, yname = self.sname, self.xname, self.yname
        # start new plot
        fig.start_plot()
        axx.set_ylabel(self.get_label(xname))
        axy.set_ylabel(self.get_label(yname))
        fig.set_slabel(self.get_label(sname))
        # invoke plot hooks
        self.hook.plot_ax(axx, xname)
        self.hook.plot_ax(axy, yname)
        self.hook.plot()
        # finish and draw:
        fig.draw()

    def get_axes_name(self, axes):
        return next(k for k,v in self.axes.items() if v is axes)

    def get_conjugate(self, name):
        return self._conjugate[name]


# TODO: Store the constraints with a Match object, rather than "globally"
# with the model.
class DrawConstraints(object):

    def __init__(self, panel):
        self.view = view = panel.view
        self.model = model = view.model
        self.lines = []
        def redraw():
            self.redraw_constraints()
        model.hook.remove_constraint.connect(redraw)
        model.hook.clear_constraints.connect(redraw)
        model.hook.add_constraint.connect(redraw)

    def draw_constraint(self, name, elem, envelope):
        """Draw one constraint representation in the graph."""
        view = self.view
        return view.axes[name].plot(
            stripunit(elem.at, view.unit[view.sname]),
            stripunit(envelope, view.unit[name]),
            's',
            fillstyle='full',
            markersize=7,
            color='black')

    def redraw_constraints(self):
        """Draw all current constraints in the graph."""
        for lines in self.lines:
            for l in lines:
                l.remove()
        self.lines = []
        for name,elem,envelope in self.model.constraints:
            lines = self.draw_constraint(name, elem, envelope)
            self.lines.append(lines)
        self.view.figure.draw()


class UpdateStatusBar(object):

    """
    Update utility for status bars.
    """

    @classmethod
    def create(cls, panel):
        frame = panel.GetTopLevelParent()
        view = panel.view
        def set_status_text(text):
            return frame.GetStatusBar().SetStatusText(text, 0)
        return cls(view, set_status_text)

    def __init__(self, view, set_status_text):
        """Connect mouse event handler."""
        self._view = view
        self._set_status_text = set_status_text
        # Just passing self.on_mouse_move to mpl_connect does not keep the
        # self object alive. The closure does the job, though:
        def on_mouse_move(event):
            self.on_mouse_move(event)
        view.figure.canvas.mpl_connect('motion_notify_event', on_mouse_move)

    def on_mouse_move(self, event):
        """Update statusbar text."""
        xdata, ydata = event.xdata, event.ydata
        if xdata is None or ydata is None:
            # outside of axes:
            self._set_status_text("")
            return
        name = self._view.get_axes_name(event.inaxes)
        unit = self._view.unit
        model = self._view.model
        elem = model.element_by_position(xdata * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', xdata, raw_label(unit['s'])),
                 coord_fmt(name, ydata, raw_label(unit[name]))]
        if elem and 'name' in elem:
            parts.append('elem={0}'.format(elem['name']))
        self._set_status_text(', '.join(parts))


class DrawLineElements(object):

    @classmethod
    def create(cls, panel):
        view = panel.view
        model = view.model
        style = view.config['element_style']
        return cls(view, model, style)

    def __init__(self, view, model, style):
        self._view = view
        self._model = model
        self._style = style
        view.hook.plot_ax.connect(self.plot_ax)

    def plot_ax(self, axes, name):
        """Draw the elements into the canvas."""
        view = self._view
        max_env = np.max(view.model.tw[name])
        patch_h = 0.75*stripunit(max_env, view.unit[name])
        unit_s = view.unit[view.sname]
        for elem in view.model.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            if stripunit(elem.L) != 0:
                patch_w = stripunit(elem['L'], unit_s)
                patch_x = stripunit(elem['at'], unit_s) - patch_w/2
                axes.add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h,
                        **elem_type))
            else:
                patch_x = stripunit(elem['at'], unit_s)
                axes.vlines(patch_x, 0, patch_h, **elem_type)

    def get_element_type(self, elem):
        """Return the element type name used for properties like coloring."""
        if 'type' not in elem or 'at' not in elem:
            return None
        type_name = elem.type.lower()
        focussing = None
        if type_name == 'quadrupole':
            focussing = stripunit(elem.k1) > 0
        elif type_name == 'sbend':
            focussing = stripunit(elem.angle) > 0
        if focussing is not None:
            if focussing:
                type_name = 'f-' + type_name
            else:
                type_name = 'd-' + type_name
        return self._style.get(type_name)
