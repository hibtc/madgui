# encoding: utf-8
"""
View component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# scipy
from matplotlib.ticker import AutoMinorLocator

# internal
from madgui.core.plugin import HookCollection
from madgui.util.unit import units, strip_unit, get_unit_label, get_raw_label

import matplotlib
import matplotlib.figure

# exported symbols
__all__ = [
    'TwissView',
]


def _clear_ax(ax):
    """Clear a single :class:`matplotlib.axes.Axes` instance."""
    ax.cla()
    ax.grid(True)
    ax.get_xaxis().set_minor_locator(AutoMinorLocator())
    ax.get_yaxis().set_minor_locator(AutoMinorLocator())


def _autoscale_axes(axes):
    """Autoscale a :class:`matplotlib.axes.Axes` to its contents."""
    axes.relim()
    axes.autoscale()


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
        self.axy       = figure.add_subplot(212, sharex=axx)

    @property
    def canvas(self):
        """Get the canvas."""
        return self.figure.canvas

    def draw(self):
        """Draw the figure on its canvas."""
        _autoscale_axes(self.axx)
        _autoscale_axes(self.axy)
        self.figure.canvas.draw()

    def set_slabel(self, label):
        """Set label on the s axis."""
        self.axy.set_xlabel(label)

    def start_plot(self):
        """Start a fresh plot."""
        _clear_ax(self.axx)
        _clear_ax(self.axy)


class TwissCurveSegment(object):

    """Plot a TWISS parameter curve segment into a 2D figure."""

    def __init__(self, segment, view):
        """Store meta data."""
        self._segment = segment
        self._unit = view.unit
        self._style = view.config['curve_style']
        self._clines = {}
        self._view = view
        # Register for update events
        view.hook.plot_ax.connect(self.plot_ax)
        self._segment.hook.update.connect(self.update)
        self._segment.hook.remove.connect(self.destroy)

    def plot_ax(self, axes, name):
        """Make one subplot."""
        style = self._style[name[-1]]
        abscissa = self.get_float_data('s')
        ordinate = self.get_float_data(name)
        axes.set_xlim(abscissa[0], abscissa[-1])
        self._clines[name] = axes.plot(abscissa, ordinate, **style)[0]

    def update(self):
        """Update the (previously plotted!) lines in the graph."""
        self.update_ax(self._view.figure.axx, self._view.xname)
        self.update_ax(self._view.figure.axy, self._view.yname)

    def update_ax(self, axes, name):
        """Update the y values for one subplot."""
        self._clines[name].set_ydata(self.get_float_data(name))

    def get_float_data(self, name):
        """Get a float data vector."""
        return strip_unit(self._segment.tw[name], self._unit[name])

    def destroy(self):
        """Disconnect update events."""
        self._view.hook.plot_ax.disconnect(self.plot_ax)
        self._segment.hook.update.disconnect(self.update)
        self._segment.hook.remove.disconnect(self.destroy)
        for line in self._clines.values():
            line.remove()
        self._clines.clear()


class TwissView(object):

    """Instanciate an FigurePair + XYCurve(Envelope)."""

    @classmethod
    def create(cls, session, frame, basename):
        """Create a new view panel as a page in the notebook frame."""
        if not session.segment:
            return
        view = cls(session.segment, basename, frame.app.conf['line_view'])
        panel = frame.AddView(view, view.title)
        return view

    def __init__(self, segment, basename, line_view_config):

        self.hook = HookCollection(
            plot=None,
            plot_ax=None,
            destroy=None,
        )

        # create figure
        self.figure = figure = FigurePair()
        self.segment = segment
        self.config = line_view_config

        self.title = line_view_config['title'][basename]

        self.sname = sname = 's'
        self.xname = xname = basename + 'x'
        self.yname = yname = basename + 'y'
        self.axes = {xname: figure.axx,
                     yname: figure.axy}
        self._conjugate = {xname: yname, yname: xname}

        # plot style
        self._label = line_view_config['label']
        unit_names = line_view_config['unit']
        self.unit = {col: getattr(units, unit_names[col])
                     for col in [sname, xname, yname]}

        # subscribe for updates
        TwissCurveSegment(segment, self)
        DrawLineElements(self, self.config['element_style'])
        self.segment.hook.update.connect(self.update)

    def destroy(self):
        self.segment.hook.update.disconnect(self.update)
        self.hook.destroy()

    def update(self):
        self.figure.draw()

    def get_label(self, name):
        return self._label[name] + ' ' + get_unit_label(self.unit[name])

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

    def __init__(self, matching, view):
        self.view = view
        self.matching = matching
        self._style = view.config['constraint_style']
        self.lines = []
        redraw = self.redraw_constraints
        matching.hook.remove_constraint.connect(redraw)
        matching.hook.clear_constraints.connect(redraw)
        matching.hook.add_constraint.connect(redraw)
        matching.hook.stop.connect(self.on_stop)

    def on_stop(self):
        matching = self.matching
        redraw = self.redraw_constraints
        matching.hook.remove_constraint.disconnect(redraw)
        matching.hook.clear_constraints.disconnect(redraw)
        matching.hook.add_constraint.disconnect(redraw)
        matching.hook.stop.disconnect(self.on_stop)

    def draw_constraint(self, name, elem, envelope):
        """Draw one constraint representation in the graph."""
        view = self.view
        return view.axes[name].plot(
            strip_unit(elem['at'] + elem['l']/2, view.unit[view.sname]),
            strip_unit(envelope, view.unit[name]),
            **self._style)

    def redraw_constraints(self):
        """Draw all current constraints in the graph."""
        for lines in self.lines:
            for l in lines:
                l.remove()
        self.lines = []
        for name, constr in self.matching.constraints.items():
            for elem,envelope in constr:
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
        elem = self._view.segment.element_by_position(xdata * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', xdata, get_raw_label(unit['s'])),
                 coord_fmt(name, ydata, get_raw_label(unit[name]))]
        if elem and 'name' in elem:
            parts.append('elem={0}'.format(elem['name']))
        self._set_status_text(', '.join(parts))


class DrawLineElements(object):

    def __init__(self, view, style):
        self._view = view
        self._style = style
        segment = view.segment
        view.hook.plot_ax.connect(self.plot_ax)
        segment.hook.show_element_indicators.connect(view.plot)

    def destroy(self):
        view = self._view
        segment = view.segment
        view.hook.plot_ax.disconnect(self.plot_ax)
        segment.hook.show_element_indicators.disconnect(view.plot)

    def plot_ax(self, axes, name):
        """Draw the elements into the canvas."""
        view = self._view
        segment = view.segment
        if not segment.show_element_indicators:
            return
        unit_s = view.unit[view.sname]
        for elem in segment.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            patch_x = strip_unit(elem['at'], unit_s)
            if strip_unit(elem['l']) != 0:
                patch_w = strip_unit(elem['l'], unit_s)
                axes.axvspan(patch_x, patch_x + patch_w, **elem_type)
            else:
                axes.vlines(patch_x, **elem_type)

    def get_element_type(self, elem):
        """Return the element type name used for properties like coloring."""
        if 'type' not in elem or 'at' not in elem:
            return None
        type_name = elem['type'].lower()
        focussing = None
        if type_name == 'quadrupole':
            focussing = strip_unit(elem['k1']) > 0
        elif type_name == 'sbend':
            focussing = strip_unit(elem['angle']) > 0
        if focussing is not None:
            if focussing:
                type_name = 'f-' + type_name
            else:
                type_name = 'd-' + type_name
        return self._style.get(type_name)
