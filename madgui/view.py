"""
View component for the MadGUI application.
"""

# scipy
import numpy as np
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

from collections import namedtuple
Vector = namedtuple('Vector', ['x', 'y'])

class MadView(object):
    """
    Matplotlib figure view for a MadModel.

    This is automatically updated when the model changes.

    """

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
        self.unit = Vector(
            {'label': 'm',  'scale': 1},
            {'label': 'mm', 'scale': 1e-3})

        self.curve = Vector(
            {'factor': 1, 'color': '#8b1a0e'},
            {'factor': 1, 'color': '#5e9c36'})

        self.clines = None, None

        # display colors for elements
        self.element_types = {
            'f-quadrupole': {'color': '#ff0000'},
            'd-quadrupole': {'color': '#0000ff'},
            'f-sbend':      {'color': '#770000'},
            'd-sbend':      {'color': '#000077'},
            'multipole':    {'color': '#00ff00'}
        }

        # subscribe for updates
        model.update += lambda model: self.update()
        model.remove_constraint += lambda model, elem, axis=None: self.redraw_constraints()
        model.clear_constraints += lambda model: self.redraw_constraints()
        model.add_constraint += lambda model, axis, elem, envelope: self.redraw_constraints()


    def draw_constraint(self, axis, elem, envelope):
        """Draw one constraint representation in the graph."""
        return self.axes[axis].plot(
            elem['at'],
            envelope/self.unit.y['scale']*self.curve[axis]['factor'],
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
            focussing = self.model.tw.k1l[i] > 0
        elif type_name == 'sbend':
            i = self.model.get_element_index(elem)
            focussing = self.model.tw.angle[i] > 0
        if focussing is not None:
            if focussing:
                type_name = 'f-' + type_name
            else:
                type_name = 'd-' + type_name
        return self.element_types.get(type_name)

    def update(self):
        lx, ly = self.clines
        if lx is None or ly is None:
            self.plot()
            return
        envx, envy = self.model.env
        lx.set_ydata(envx/self.unit.y['scale']*self.curve.x['factor'])
        ly.set_ydata(envy/self.unit.y['scale']*self.curve.y['factor'])
        self.figure.canvas.draw()

    def plot(self):
        """Plot figure and redraw canvas."""
        # data post processing
        pos = self.model.pos
        envx, envy = self.model.env

        max_env = Vector(np.max(envx), np.max(envy))
        patch_h = Vector(0.75*max_env.x, 0.75*max_env.y)

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

            if 'L' in elem and float(elem['L']) != 0:
                patch_w = float(elem['L'])
                patch_x = float(elem['at']) - patch_w/2
                self.axes.x.add_patch(
                        mpl.patches.Rectangle(
                            (patch_x, 0),
                            patch_w, patch_h.x/self.unit.y['scale'],
                            alpha=0.5, color=elem_type['color']))
                self.axes.y.add_patch(
                        mpl.patches.Rectangle(
                            (patch_x, 0),
                            patch_w, patch_h.y/self.unit.y['scale'],
                            alpha=0.5, color=elem_type['color']))
            else:
                patch_x = float(elem['at'])
                self.axes.x.vlines(
                        patch_x, 0,
                        patch_h.x/self.unit.y['scale'],
                        alpha=0.5, color=elem_type['color'])
                self.axes.y.vlines(
                        patch_x, 0,
                        patch_h.y/self.unit.y['scale'],
                        alpha=0.5, color=elem_type['color'])

        lx, = self.axes.x.plot(
                pos, envx/self.unit.y['scale']*self.curve.x['factor'],
                "o-", color=self.curve.x['color'], fillstyle='none',
                label="$\Delta x$")
        ly, = self.axes.y.plot(
                pos, envy/self.unit.y['scale']*self.curve.y['factor'],
                "o-", color=self.curve.y['color'], fillstyle='none',
                label="$\Delta y$")
        self.clines = lx, ly

        self.lines = []
        self.redraw_constraints()

        # self.axes.legend(loc='upper left')
        self.axes.y.set_xlabel("position $s$ [m]")

        for axis_index, axis_name in enumerate(['x', 'y']):
            self.axes[axis_index].grid(True)
            self.axes[axis_index].get_xaxis().set_minor_locator(
                MultipleLocator(2))
            self.axes[axis_index].get_yaxis().set_minor_locator(
                MultipleLocator(0.002/self.unit.y['scale']))
            self.axes[axis_index].set_xlim(pos[0], pos[-1])
            self.axes[axis_index].set_ylabel("$\Delta %s$ [%s]" % (
                axis_name, self.unit.y['label']))
            self.axes[axis_index].set_ylim(0)

        # invert y-axis:
        self.axes.y.set_ylim(self.axes.y.get_ylim()[::-1])
        self.figure.canvas.draw()


