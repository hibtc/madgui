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
__all__ = ['LineView']


class LineView(object):

    """
    Matplotlib figure view for a MadModel.

    This is automatically updated when the model changes.
    """

    hook = ivar(HookCollection,
                plot=None)

    @classmethod
    def create(cls, model, frame):
        """Create a new view panel as a page in the notebook frame."""
        view = cls(model, frame.app.conf)
        frame.AddView(view, model.name)
        return view

    def __init__(self, model, config):
        """Create a matplotlib figure and register as observer."""
        self.model = model
        self.config = line_view_config = config['line_view']
        self.clines = {'x': None, 'y': None}
        self.lines = []

        # create figure
        self.figure = matplotlib.figure.Figure()
        self.figure.subplots_adjust(hspace=0.00)
        axx = self.figure.add_subplot(211)
        axy = self.figure.add_subplot(212, sharex=axx)
        self.axes = {'x': axx,
                     'y': axy}

        # plot style
        self.unit = {
            's': getattr(units, line_view_config['unit']['s']),
            'x': getattr(units, line_view_config['unit']['x']),
            'y': getattr(units, line_view_config['unit']['y']),
        }
        self.curve_style = line_view_config['curve_style']

        # subscribe for updates
        model.hook.update.connect(self.update)
        model.hook.remove_constraint.connect(self.redraw_constraints)
        model.hook.clear_constraints.connect(self.redraw_constraints)
        model.hook.add_constraint.connect(self.redraw_constraints)

    def draw_constraint(self, axis, elem, envelope):
        """Draw one constraint representation in the graph."""
        return self.axes[axis].plot(
            stripunit(elem.at, self.unit['s']),
            stripunit(envelope, self.unit[axis]),
            's',
            fillstyle='full',
            markersize=7,
            color=self.curve_style[axis]['color'])

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

    def update(self):
        """Redraw the envelopes."""
        if self.clines['x'] is None or self.clines['y'] is None:
            self.plot()
            return
        self.clines['x'].set_ydata(stripunit(self.model.env['x'],
                                             self.unit['x']))
        self.clines['y'].set_ydata(stripunit(self.model.env['y'],
                                             self.unit['y']))
        self.figure.canvas.draw()

    def get_abscissa(self):
        """Get the abcissa values."""
        return stripunit(self.model.pos, self.unit['s'])

    def get_ordinate(self, axis):
        """Get the ordinate values."""
        return stripunit(self.model.env[axis], self.unit[axis])

    def plot(self):

        """Plot figure and redraw canvas."""

        for axis in ('x', 'y'):
            # clear plot + set style
            ax = self.axes[axis]
            ax.cla()
            ax.grid(True)
            ax.get_xaxis().set_minor_locator(AutoMinorLocator())
            ax.get_yaxis().set_minor_locator(AutoMinorLocator())
            label = r'$\Delta %s$ %s' % (axis, unit_label(self.unit[axis]))
            ax.set_ylabel(label)
            # main pot
            abscissa = self.get_abscissa()
            ordinate = self.get_ordinate(axis)
            curve_style = self.curve_style[axis]
            ax.set_xlim(abscissa[0], abscissa[-1])
            self.clines[axis] = ax.plot(abscissa, ordinate, **curve_style)[0]
            ax.set_ylim(0)

        # components that should be externalized:
        self.redraw_constraints()

        axx = self.axes['x']
        axy = self.axes['y']

        # disable x-labels in upper axes
        for label in axx.xaxis.get_ticklabels():
            label.set_visible(False)
        axy.set_xlabel("position $s$ [m]")
        # disable the y=0 label in the lower axes
        axy.yaxis.get_ticklabels()[0].set_visible(False)
        # invert y-axis in lower axes:
        axy.set_ylim(axy.get_ylim()[::-1])

        # trigger event
        self.hook.plot()

        # draw canvas *after* event has been triggered, because there can be
        # event handlers that add elements to the plot:
        self.figure.canvas.draw()


class UpdateStatusBar(object):

    """
    Update utility for status bars.
    """

    def __init__(self, panel):
        """Connect mouse event handler."""
        self._frame = panel.GetTopLevelParent()
        self._view = panel.view
        # Just passing self.on_mouse_move to mpl_connect does not keep the
        # self object alive. The closure does the job, though:
        def on_mouse_move(event):
            self.on_mouse_move(event)
        panel.canvas.mpl_connect('motion_notify_event', on_mouse_move)

    def on_mouse_move(self, event):
        """Update statusbar text."""
        xdata, ydata = event.xdata, event.ydata
        if xdata is None or ydata is None:
            # outside of axes:
            self.status_text = ""
            return
        axis = 'x' if event.inaxes is self._view.axes['x'] else 'y'
        unit = self._view.unit
        model = self._view.model
        elem = model.element_by_position(xdata * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', xdata, raw_label(unit['s'])),
                 coord_fmt(axis, ydata, raw_label(unit[axis]))]
        if elem and 'name' in elem:
            parts.append('elem={0}'.format(elem['name']))
        self.status_text = ', '.join(parts)

    @property
    def status_text(self):
        """Get the statusbar text."""
        return self.statusbar.GetStatusText(0)

    @status_text.setter
    def status_text(self, text):
        """Set the statusbar text."""
        self.statusbar.SetStatusText(text, 0)

    @property
    def statusbar(self):
        """Get the statusbar."""
        return self._frame.GetStatusBar()


class DrawLineElements(object):

    def __init__(self, panel):
        self._view = view = panel.view
        self._model = view.model

        def on_plot():
            self.drawelements()
        view.hook.plot.connect(on_plot)

        # display colors for elements
        self.element_style = view.config['element_style']

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
        return self.element_style.get(type_name)

    def drawelements(self):
        """Draw the elements into the canvas."""
        view = self._view
        max_env = {'x': np.max(view.model.env['x']),
                   'y': np.max(view.model.env['y'])}
        patch_h = {'x': 0.75*stripunit(max_env['x'], view.unit['x']),
                   'y': 0.75*stripunit(max_env['y'], view.unit['y'])}
        for elem in view.model.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            if stripunit(elem.L) != 0:
                patch_w = stripunit(elem['L'], view.unit['s'])
                patch_x = stripunit(elem['at'], view.unit['s']) - patch_w/2
                view.axes['x'].add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h['x'],
                        **elem_type))
                view.axes['y'].add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h['y'],
                        **elem_type))
            else:
                patch_x = stripunit(elem['at'], view.unit['s'])
                view.axes['x'].vlines(
                    patch_x, 0,
                    patch_h['x'],
                    **elem_type)
                view.axes['y'].vlines(
                    patch_x, 0,
                    patch_h['y'],
                    **elem_type)
