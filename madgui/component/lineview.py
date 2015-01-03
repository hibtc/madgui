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
from madgui.component.changetwiss import TwissDialog
from madgui.component.model import Segment
from madgui.component.modeldetail import ModelDetailDlg
from madgui.core import wx
from madgui.core.plugin import HookCollection
from madgui.util.unit import units, strip_unit, get_unit_label, get_raw_label

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
        axes.relim()
        axes.autoscale_view()

    def get_float_data(self, name):
        """Get a float data vector."""
        return strip_unit(self._model.tw[name], self._unit[name])


class TwissView(object):

    """Instanciate an FigurePair + XYCurve(Envelope)."""

    @classmethod
    def create(cls, simulator, frame, basename):
        """Create a new view panel as a page in the notebook frame."""
        if simulator.model:
            cls.create_from_model(simulator.model, frame, basename)
        else:
            cls.create_from_plain(simulator.madx, frame, basename)


    @classmethod
    def create_from_model(cls, cpymad_model, frame, basename):
        """Create a new view panel as a page in the notebook frame."""
        select_detail_dlg = ModelDetailDlg(frame, model=cpymad_model,
                                           title=cpymad_model.name)
        try:
            if select_detail_dlg.ShowModal() != wx.ID_OK:
                return
        finally:
            select_detail_dlg.Destroy()

        detail = select_detail_dlg.data

        sequence = cpymad_model.sequences[detail['sequence']]
        range = sequence.ranges[detail['range']]
        twiss_args = range.initial_conditions[detail['twiss']]
        twiss_args = frame.madx_units.dict_add_unit(twiss_args)
        range.init()

        segment = Segment(
            sequence=detail['sequence'],
            range=range.bounds,
            madx=frame.env['madx'],
            utool=frame.madx_units,
            twiss_args=twiss_args,
        )
        segment.model = cpymad_model

        view = cls(segment, basename, frame.app.conf['line_view'])
        frame.AddView(view, view.title)
        return view

    @classmethod
    def create_from_plain(cls, madx, frame, basename):

        # look for sequences
        sequences = madx.get_sequence_names()
        if len(sequences) == 0:
            # TODO: log
            return
        elif len(sequences) == 1:
            name = sequences[0]
        else:
            # if there are multiple sequences - just ask the user which
            # one to use rather than taking a wild guess based on twiss
            # computation etc
            dlg = wx.SingleChoiceDialog(parent=frame,
                                        caption="Select sequence",
                                        message="Select sequence:",
                                        choices=sequences)
            try:
                if dlg.ShowModal() != wx.ID_OK:
                    return
                name = dlg.GetStringSelection()
            finally:
                dlg.Destroy()

        # select twiss initial conditions
        twiss_args = TwissDialog.create(frame, frame.madx_units, None)

        # now create the actual model object
        model = Segment(madx, utool=frame.madx_units, name=name)
        frame.env.update(control=model,
                         model=None,
                         name=name)
        if name:
            model.hook.show(model, frame)

    def __init__(self, model, basename, line_view_config):

        self.hook = HookCollection(
            plot=None,
            update_ax=None,
            plot_ax=None)

        # create figure
        self.figure = figure = FigurePair()
        self.model = model
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
        self.unit = unit = {col: getattr(units, unit_names[col])
                            for col in [sname, xname, yname]}

        # create a curve as first plotter hook
        TwissCurve.from_view(self)

        # subscribe for updates
        model.hook.update.connect(self.update)

    def destroy(self):
        self.model.hook.update.disconnect(self.update)

    def update(self):
        self.hook.update_ax(self.figure.axx, self.xname)
        self.hook.update_ax(self.figure.axy, self.yname)
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
        model = self._view.model
        elem = model.element_by_position(xdata * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', xdata, get_raw_label(unit['s'])),
                 coord_fmt(name, ydata, get_raw_label(unit[name]))]
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
        unit_s = view.unit[view.sname]
        for elem in view.model.elements:
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
