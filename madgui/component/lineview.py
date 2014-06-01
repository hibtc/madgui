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
from madgui.util.vector import Vector
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
            unit = view.unit
            elem = model.element_by_position(x*unit.x)
            # TODO: in some cases, it might be necessary to adjust the
            # precision to the displayed xlim/ylim.
            coord_fmt = "{0}={1:.6f}{2}".format
            parts = [coord_fmt('x', x, raw_label(unit.x)),
                     coord_fmt('y', y, raw_label(unit.y))]
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
        self.axes = Vector(axx, axy)

        # plot style
        self.unit = Vector(units.m, units.mm)
        self.curve_style = Vector(line_view_config['curve_style']['x'],
                                  line_view_config['curve_style']['y'])

        self.clines = Vector(None, None)

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
            stripunit(elem.at, self.unit.x),
            stripunit(envelope, self.unit.y),
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
        if self.clines.x is None or self.clines.y is None:
            self.plot()
            return
        self.clines.x.set_ydata(stripunit(self.model.env.x, self.unit.y))
        self.clines.y.set_ydata(stripunit(self.model.env.y, self.unit.y))
        self.figure.canvas.draw()

    def _drawelements(self):
        """Draw the elements into the canvas."""
        envx, envy = self.model.env
        max_env = Vector(np.max(envx), np.max(envy))
        patch_h = Vector(0.75*stripunit(max_env.x, self.unit.y),
                         0.75*stripunit(max_env.y, self.unit.y))
        for elem in self.model.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            if stripunit(elem.L) != 0:
                patch_w = stripunit(elem['L'], self.unit.x)
                patch_x = stripunit(elem['at'], self.unit.x) - patch_w/2
                self.axes.x.add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h.x,
                        alpha=0.5,
                        **elem_type))
                self.axes.y.add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h.y,
                        alpha=0.5,
                        **elem_type))
            else:
                patch_x = stripunit(elem['at'], self.unit.x)
                self.axes.x.vlines(
                    patch_x, 0,
                    patch_h.x,
                    alpha=0.5,
                    **elem_type)
                self.axes.y.vlines(
                    patch_x, 0,
                    patch_h.y,
                    alpha=0.5,
                    **elem_type)

    def plot(self):

        """Plot figure and redraw canvas."""

        # data post processing
        pos = self.model.pos
        envx, envy = self.model.env

        # plot
        self.axes.x.cla()
        self.axes.y.cla()

        # disable labels on x-axis
        for label in self.axes.x.xaxis.get_ticklabels():
            label.set_visible(False)
        self.axes.y.yaxis.get_ticklabels()[0].set_visible(False)

        self._drawelements()

        self.clines = Vector(
            self.axes.x.plot(
                stripunit(pos, self.unit.x), stripunit(envx, self.unit.y),
                "o-", fillstyle='none',
                label="$\Delta x$",
                **self.curve_style.x)[0],
            self.axes.y.plot(
                stripunit(pos, self.unit.x), stripunit(envy, self.unit.y),
                "o-", fillstyle='none',
                label="$\Delta y$",
                **self.curve_style.y)[0])

        self.lines = []
        self.redraw_constraints()

        # self.axes.legend(loc='upper left')
        self.axes.y.set_xlabel("position $s$ [m]")

        for axis_index, axis_name in enumerate(['x', 'y']):
            self.axes[axis_index].grid(True)
            self.axes[axis_index].get_xaxis().set_minor_locator(AutoMinorLocator())
            self.axes[axis_index].get_yaxis().set_minor_locator(AutoMinorLocator())
            self.axes[axis_index].set_xlim(stripunit(pos[0], self.unit.x),
                                           stripunit(pos[-1], self.unit.x))
            self.axes[axis_index].set_ylabel(r'$\Delta %s$ %s' % (
                axis_name, unit_label(self.unit.y)))
            self.axes[axis_index].set_ylim(0)

        # invert y-axis:
        self.axes.y.set_ylim(self.axes.y.get_ylim()[::-1])
        self.figure.canvas.draw()

        # trigger event
        self.hook.plot()
