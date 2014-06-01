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
        def on_mouse_move(event):
            x, y = event.xdata, event.ydata
            if x is None or y is None:
                # outside of axes:
                frame.GetStatusBar().SetStatusText("", 0)
                return
            axis = 'x' if event.inaxes is view.axes['x'] else 'y'
            unit = view.unit
            elem = model.element_by_position(x*unit['s'])
            # TODO: in some cases, it might be necessary to adjust the
            # precision to the displayed xlim/ylim.
            coord_fmt = "{0}={1:.6f}{2}".format
            parts = [coord_fmt('s', x, raw_label(unit['s'])),
                     coord_fmt(axis, y, raw_label(unit[axis]))]
            if elem and 'name' in elem:
                parts.append('elem={0}'.format(elem['name']))
            frame.GetStatusBar().SetStatusText(', '.join(parts), 0)
        view.figure.canvas.mpl_connect('motion_notify_event', on_mouse_move)
        return view

    def __init__(self, model, config):
        """Create a matplotlib figure and register as observer."""
        self.model = model
        self.config = line_view_config = config['line_view']

        # create figure
        self.figure = matplotlib.figure.Figure()
        self.figure.subplots_adjust(hspace=0.00)
        axx = self.figure.add_subplot(211)
        axy = self.figure.add_subplot(212, sharex=axx)
        self.axes = {'x': axx,
                     'y': axy}

        # plot style
        self.unit = {'s': units.m,
                     'x': units.mm,
                     'y': units.mm}
        self.curve_style = line_view_config['curve_style']

        self.clines = {'x': None,
                       'y': None}

        # display colors for elements
        self.element_style = line_view_config['element_style']

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

    def _drawelements(self):
        """Draw the elements into the canvas."""
        max_env = {'x': np.max(self.model.env['x']),
                   'y': np.max(self.model.env['y'])}
        patch_h = {'x': 0.75*stripunit(max_env['x'], self.unit['x']),
                   'y': 0.75*stripunit(max_env['y'], self.unit['y'])}
        for elem in self.model.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            if stripunit(elem.L) != 0:
                patch_w = stripunit(elem['L'], self.unit['s'])
                patch_x = stripunit(elem['at'], self.unit['s']) - patch_w/2
                self.axes['x'].add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h['x'],
                        **elem_type))
                self.axes['y'].add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h['y'],
                        **elem_type))
            else:
                patch_x = stripunit(elem['at'], self.unit['s'])
                self.axes['x'].vlines(
                    patch_x, 0,
                    patch_h['x'],
                    **elem_type)
                self.axes['y'].vlines(
                    patch_x, 0,
                    patch_h['y'],
                    **elem_type)

    def plot(self):

        """Plot figure and redraw canvas."""

        # data post processing
        pos = self.model.pos
        env = self.model.env

        # plot
        self.axes['x'].cla()
        self.axes['y'].cla()

        # disable labels on x-axis
        for label in self.axes['x'].xaxis.get_ticklabels():
            label.set_visible(False)
        self.axes['y'].yaxis.get_ticklabels()[0].set_visible(False)

        self._drawelements()

        self.clines = {
            'x': self.axes['x'].plot(
                stripunit(pos, self.unit['s']),
                stripunit(env['x'], self.unit['x']),
                **self.curve_style['x'])[0],
            'y': self.axes['y'].plot(
                stripunit(pos, self.unit['s']),
                stripunit(env['y'], self.unit['y']),
                **self.curve_style['y'])[0]
        }

        self.lines = []
        self.redraw_constraints()

        # self.axes.legend(loc='upper left')
        self.axes['y'].set_xlabel("position $s$ [m]")

        for axis in ('x', 'y'):
            ax = self.axes[axis]
            ax.grid(True)
            ax.get_xaxis().set_minor_locator(AutoMinorLocator())
            ax.get_yaxis().set_minor_locator(AutoMinorLocator())
            ax.set_xlim(stripunit(pos[0], self.unit['s']),
                        stripunit(pos[-1], self.unit['s']))
            ax.set_ylabel(r'$\Delta %s$ %s' % (axis,
                                               unit_label(self.unit[axis])))
            ax.set_ylim(0)

        # invert y-axis:
        axy = self.axes['y']
        axy.set_ylim(axy.get_ylim()[::-1])
        self.figure.canvas.draw()

        # trigger event
        self.hook.plot()
