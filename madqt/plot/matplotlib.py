# encoding: utf-8
"""
Utilities to create plots using matplotlib via the Qt4Agg backend.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple
from functools import partial

from madqt.qt import QtCore, QtGui      # import Qt before matplotlib!

import matplotlib as mpl
mpl.use('Qt4Agg')                       # select before mpl.backends import!
import matplotlib.backends.backend_qt4agg as mpl_backend
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator

from madqt.core.unit import units, strip_unit, get_unit_label, get_raw_label
from madqt.core.base import Object, Signal
from madqt.util.layout import VBoxLayout


__all__ = [
    'PlotWidget',
    'FigurePair',
    'TwissFigure',
    'ElementIndicators',
]


Pair = namedtuple('Pair', ['x', 'y'])


class PlotWidget(QtGui.QWidget):

    """
    Widget containing a matplotlib figure.
    """

    def __init__(self, figure, *args, **kwargs):

        """
        Initialize figure/canvas and connect the view.

        :param TwissFigure figure: the contained figure
        :param args: positional arguments for :class:`QWidget`
        :param kwargs: keyword arguments for :class:`QWidget`
        """

        super(PlotWidget, self).__init__(*args, **kwargs)

        self.figure = figure
        self.canvas = mpl_backend.FigureCanvas(figure.mpl_figure)
        self.toolbar = mpl_backend.NavigationToolbar2QT(self.canvas, self)
        self.figure.plot()

        self.setLayout(VBoxLayout([self.canvas, self.toolbar]))


class FigurePair(object):

    """
    A figure composed of two subplots with shared s-axis.

    :ivar matplotlib.figure.Figure mpl_figure: composed figure
    :ivar matplotlib.axes.Axes axx: upper subplot
    :ivar matplotlib.axes.Axes axy: lower subplot
    """

    def __init__(self):
        """Create an empty matplotlib figure with two subplots."""
        self.mpl_figure = figure = Figure()
        axx = figure.add_subplot(211)
        axy = figure.add_subplot(212, sharex=axx)
        self.axes = Pair(axx, axy)

    @property
    def canvas(self):
        """Get the canvas."""
        return self.mpl_figure.canvas

    def draw(self):
        """Draw the figure on its canvas."""
        _autoscale_axes(self.axes.x)
        _autoscale_axes(self.axes.y)
        self.mpl_figure.canvas.draw()

    def set_slabel(self, label):
        """Set label on the s axis."""
        self.axes.y.set_xlabel(label)

    def clear(self):
        """Start a fresh plot."""
        _clear_ax(self.axes.x)
        _clear_ax(self.axes.y)


class TwissFigure(object):

    """A figure containing some X/Y twiss parameters."""

    @classmethod
    def create(cls, universe, frame, basename):
        """Create a new view panel as a page in the notebook frame."""
        if not universe.segment:
            return
        view = cls(universe.segment, basename, frame.config['line_view'])
        #panel = frame.AddView(view, view.title)
        return view

    def __init__(self, segment, basename, config):

        # create figure
        self.figure = figure = FigurePair()
        self.segment = segment
        self.config = config
        self.basename = basename

        self.title = config['title'][basename]
        self.sname = sname = 's'
        self.names = Pair(basename+'x', basename+'y')

        # plot style
        self.label = config['label']
        unit_names = config['unit']
        all_axes_names = (self.sname,) + self.names
        self.unit = {col: getattr(units, unit_names[col])
                     for col in all_axes_names}

        # create scene
        elements_style = config['element_style']
        self.scene_graph = SceneGraph([])
        self.add_twiss_curve(self.basename)
        self.indicators = SceneGraph([
            ElementIndicators(self.figure.axes.x, self, elements_style),
            ElementIndicators(self.figure.axes.y, self, elements_style),
        ])

        # subscribe for updates
        self.segment.updated.connect(self.update)

    @property
    def mpl_figure(self):
        return self.figure.mpl_figure

    def remove(self):
        self.scene_graph.remove()
        self.segment.updated.disconnect(self.update)

    def get_label(self, name):
        return self.label[name] + ' ' + get_unit_label(self.unit[name])

    def plot(self):
        """Replot from clean state."""
        fig = self.figure
        fig.clear()
        fig.axes.x.set_ylabel(self.get_label(self.names.x))
        fig.axes.y.set_ylabel(self.get_label(self.names.y))
        fig.set_slabel(self.get_label(self.sname))
        self.scene_graph.plot()
        fig.draw()

    def update(self):
        """Update existing plot after TWISS recomputation."""
        self.scene_graph.update()
        self.figure.draw()

    def get_axes_name(self, axes):
        return self.names[self.axes.index(axes)]

    def get_conjugate(self, name):
        return self.names[1-self.names.index(name)]

    def add_twiss_curve(self, basename, sname='s'):
        """
        Add an X/Y pair of lines of TWISS parameters into the figure.

        :param str basename: stem of the parameter name, e.g. 'bet'
        :param str sname: data name of the shared s-axis
        """
        xname = basename + 'x'
        yname = basename + 'y'
        style = self.config['curve_style']
        axes = self.figure.axes
        get_sdata = partial(self.get_float_data, sname)
        get_xdata = partial(self.get_float_data, xname)
        get_ydata = partial(self.get_float_data, yname)
        self.scene_graph.items.extend([
            Curve(axes.x, get_sdata, get_xdata, style['x']),
            Curve(axes.y, get_sdata, get_ydata, style['y']),
        ])

    def get_float_data(self, name):
        """Get data for the given parameter from segment."""
        return strip_unit(self.segment.tw[name], self.unit[name])

    @property
    def show_indicators(self):
        return self.indicators in self.scene_graph.items

    @show_indicators.setter
    def show_indicators(self, show):
        if show == self.show_indicators:
            return
        if show:
            self.scene_graph.items.append(self.indicators)
        else:
            self.scene_graph.items.remove(self.indicators)


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


class SceneGraph(object):

    def __init__(self, items):
        self.items = items

    def remove(self):
        for item in self.items:
            item.remove()

    def plot(self):
        for item in self.items:
            item.plot()

    def update(self):
        for item in self.items:
            item.update()


class Curve(object):

    """Plot a TWISS parameter curve segment into a 2D figure."""

    def __init__(self, axes, get_xdata, get_ydata, style):
        """Store meta data."""
        self.axes = axes
        self.get_xdata = get_xdata
        self.get_ydata = get_ydata
        self.style = style
        self.line = None

    def remove(self):
        """Disconnect update events."""
        if self.line is not None:
            self.line.remove()
            self.line = None

    def update(self):
        """Update the y values for one subplot."""
        self.line.set_ydata(self.get_ydata())

    def plot(self):
        """Make one subplot."""
        xdata = self.get_xdata()
        ydata = self.get_ydata()
        self.axes.set_xlim(xdata[0], xdata[-1])
        self.line = self.axes.plot(xdata, ydata, **self.style)[0]


class ElementIndicators(object):

    """
    Draw beam line elements (magnets etc) into a :class:`TwissFigure`.
    """

    def __init__(self, axes, view, style):
        self.axes = axes
        self.view = view
        self.style = style
        self.lines = []

    @property
    def s_unit(self):
        return self.view.unit[self.view.sname]

    @property
    def elements(self):
        return self.view.segment.elements

    def remove(self):
        for line in self.lines:
            line.remove()
        self.lines.clear()

    def plot(self):
        """Draw the elements into the canvas."""
        axes = self.axes
        s_unit = self.s_unit
        for elem in self.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            patch_x = strip_unit(elem['at'], s_unit)
            if strip_unit(elem['l']) != 0:
                patch_w = strip_unit(elem['l'], s_unit)
                line = axes.axvspan(patch_x, patch_x + patch_w, **elem_type)
            else:
                line = axes.vlines(patch_x, **elem_type)
            self.lines.append(line)

    def update(self):
        pass

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
        return self.style.get(type_name)


class UpdateStatusBar(object):

    """
    Update utility for status bars.
    """

    def __init__(self, frame, view):
        """Connect mouse event handler."""
        self.frame = frame
        self.view = view
        # Just passing self.on_mouse_move to mpl_connect does not keep the
        # self object alive. The closure does the job, though:
        def on_mouse_move(event):
            self.on_mouse_move(event)
        view.figure.canvas.mpl_connect('motion_notify_event', on_mouse_move)

    def set_status_text(self, text):
        return self.frame.getStatusBar().showMessage(text)

    def compose_status_text(self, inaxes, x, y):
        if x is None or y is None:
            # outside of axes:
            return ""
        name = self.view.get_axes_name(inaxes)
        unit = self.view.unit
        elem = self.view.segment.element_by_position(xdata * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', xdata, get_raw_label(unit['s'])),
                 coord_fmt(name, ydata, get_raw_label(unit[name]))]
        if elem and 'name' in elem:
            parts.append('elem={0}'.format(elem['name']))
        return ', '.join(parts)

    def on_mouse_move(self, event):
        """Update statusbar text."""
        self.set_status_text(self.compose_status_text(
            event.inaxes, event.xdata, event.ydata))
