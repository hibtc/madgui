"""
View component for the MadGUI application.
"""

# scipy
import numpy as np
import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator

class MadLineView:
    """
    Matplotlib figure view for a MadModel.

    This is automatically updated when the model changes.

    """

    def __init__(self, model):
        """Create a matplotlib figure and register as observer."""
        self.model = model

        # create figure
        self.figure = mpl.figure.Figure()
        self.axes = self.figure.add_subplot(111)

        # plot style
        self.unit = {
            'x': {'label': 'm',  'scale': 1},
            'y': {'label': 'mm', 'scale': 1e-3}}

        self.curve = (
            {'factor':  1, 'color': '#8b1a0e'},
            {'factor': -1, 'color': '#5e9c36'})

        # display colors for elements
        self.element_types = {
            'f-quadrupole': {'color': '#ff0000'},
            'd-quadrupole': {'color': '#0000ff'},
            'f-sbend':      {'color': '#770000'},
            'd-sbend':      {'color': '#000077'},
            'multipole':    {'color': '#00ff00'}
        }

        # subscribe for updates
        model.update += lambda model: self.plot()
        model.remove_constraint += lambda model, elem, axis=None: self.redraw_constraints()
        model.clear_constraints += lambda model: self.redraw_constraints()
        model.add_constraint += lambda model, axis, elem, envelope: self.redraw_constraints()


    def draw_constraint(self, axis, elem, envelope):
        """Draw one constraint representation in the graph."""
        return self.axes.plot(
                elem['at'], envelope/self.unit['y']['scale']*self.curve[axis]['factor'], 's',
                color=self.curve[axis]['color'],
                fillstyle='full', markersize=7)

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

    def plot(self):
        """Plot figure and redraw canvas."""
        # data post processing
        pos = self.model.pos
        envx, envy = self.model.env

        if self.curve[1]['factor'] < 0:
            max_y = np.max(envx)
            min_y = -np.max(envy)
        else:
            max_y = max(0, np.max(envx), np.max(envy))
            min_y = min(0, np.min(envx), np.min(envy))
        patch_y = 0.75 * min_y
        patch_h = 0.75 * (max_y - min_y)

        # plot
        self.axes.cla()

        for elem in self.model.sequence:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue

            if 'L' in elem and float(elem['L']) != 0:
                patch_w = float(elem['L'])
                patch_x = float(elem['at']) - patch_w/2
                self.axes.add_patch(
                        mpl.patches.Rectangle(
                            (patch_x, patch_y/self.unit['y']['scale']),
                            patch_w, patch_h/self.unit['y']['scale'],
                            alpha=0.5, color=elem_type['color']))
            else:
                patch_x = float(elem['at'])
                self.axes.vlines(
                        patch_x,
                        patch_y/self.unit['y']['scale'],
                        (patch_y+patch_h)/self.unit['y']['scale'],
                        alpha=0.5, color=elem_type['color'])

        self.axes.plot(
                pos, envx/self.unit['y']['scale']*self.curve[0]['factor'],
                "o-", color=self.curve[0]['color'], fillstyle='none',
                label="$\Delta x$")
        self.axes.plot(
                pos, envy/self.unit['y']['scale']*self.curve[1]['factor'],
                "o-", color=self.curve[1]['color'], fillstyle='none',
                label="$\Delta y$")

        self.lines = []
        self.redraw_constraints()

        self.axes.grid(True)
        self.axes.legend(loc='upper left')
        self.axes.set_xlabel("position $s$ [m]")
        self.axes.set_ylabel("beam envelope [" + self.unit['y']['label'] + "]")
        self.axes.get_xaxis().set_minor_locator(
                MultipleLocator(2))
        self.axes.get_yaxis().set_minor_locator(
                MultipleLocator(0.002/self.unit['y']['scale']))
        self.axes.set_xlim(pos[0], pos[-1])

        self.figure.canvas.draw()


