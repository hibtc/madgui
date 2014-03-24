# encoding: utf-8
"""
View component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# scipy
import numpy as np
from matplotlib.ticker import MultipleLocator

# internal
import madgui.core
from madgui.util.plugin import hookcollection
from madgui.util.vector import Vector
from madgui.util.unit import units, stripunit, unit_label

import matplotlib
import matplotlib.figure

# exported symbols
__all__ = ['LineView']


class LineView(object):

    """
    Matplotlib figure view for a MadModel.

    This is automatically updated when the model changes.
    """

    hook = hookcollection(
        'madgui.component.lineview', [
            'plot'
        ])

    @classmethod
    def create(cls, model, frame):
        """Create a new view panel as a page in the notebook frame."""
        view = cls(model)
        frame.AddView(view, model.name)
        return view

    def __init__(self, model):
        """Create a matplotlib figure and register as observer."""
        self.model = model

        # create figure
        self.figure = matplotlib.figure.Figure()
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
        model.hook.update.connect(self.update)
        model.hook.remove_constraint.connect(self.redraw_constraints)
        model.hook.clear_constraints.connect(self.redraw_constraints)
        model.hook.add_constraint.connect(self.redraw_constraints)

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
        for elem in self.model.sequence:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            if 'L' in elem and stripunit(elem['L']) != 0:
                patch_w = stripunit(elem['L'], self.unit.x)
                patch_x = stripunit(elem['at'], self.unit.x) - patch_w/2
                self.axes.x.add_patch(
                    matplotlib.patches.Rectangle(
                        (patch_x, 0),
                        patch_w, patch_h.x,
                        alpha=0.5, color=elem_type['color']))
                self.axes.y.add_patch(
                    matplotlib.patches.Rectangle(
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

        if self.model.sequence:
            self._drawelements()

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

        # trigger event
        self.hook.plot()
