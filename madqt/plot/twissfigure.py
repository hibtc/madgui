# encoding: utf-8
"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple
from functools import partial

import numpy as np

from madqt.qt import QtGui, Qt

from madqt.util.qt import waitCursor
from madqt.core.unit import units, strip_unit, from_config, get_unit_label, get_raw_label
from madqt.resource.package import PackageResource
from madqt.plot.base import SceneElement, SceneGraph


__all__ = [
    'TwissFigure',
    'ElementIndicators',
]


#----------------------------------------
# basic twiss figure
#----------------------------------------

class TwissFigure(object):

    """A figure containing some X/Y twiss parameters."""

    def __init__(self, backend, segment, graphname, config):

        # create figure
        self.backend = backend
        self.segment = segment
        self.config = config

        self.graphs = sorted(self.segment.get_graph_names())
        combo = self.combo = QtGui.QComboBox()
        combo.addItems(self.graphs)

        self.figure = backend.MultiFigure(2)
        axes = self.figure.axes

        # create scene
        elements_style = config['element_style']
        self.scene_graph = SceneGraph([None, None])
        self.indicators = SceneGraph([
            ElementIndicators(axes[0], self, elements_style),
            ElementIndicators(axes[1], self, elements_style),
        ])
        self.markers = ElementMarkers(self, segment.universe.selection)
        self.scene_graph.items.append(self.markers)

        self.set_graph(graphname)
        combo.currentIndexChanged.connect(self.change_figure)

        # subscribe for updates
        self.segment.updated.connect(self.update)

    def attach(self, plot, canvas, toolbar):
        plot.addTool(InfoTool(plot))
        plot.addTool(MatchTool(plot))
        plot.addTool(CompareTool(plot))

    def top_widget(self):
        return self.combo

    def change_figure(self, index):
        self.set_graph(self.combo.itemText(index))
        self.plot()

    def set_graph(self, graph_name):

        self.combo.setCurrentIndex(self.graphs.index(graph_name))

        translate = {
            'alfa':     'alf',
            'beta':     'bet',
            'envelope': 'env',
            'position': 'pos',
        }

        config = self.config
        axes = self.figure.axes

        self.basename = basename = translate.get(graph_name, graph_name)
        self.title = config['title'].get(basename, graph_name)
        self.names = self.backend.Triple(basename+'x', basename+'y', 's')

        # plot style
        self.label = config['label']
        unit_names = config['unit']
        self.unit = {col: from_config(unit_names.get(col, 1))
                     for col in self.names}

        # Store names
        axes[0].twiss_name = self.names.x
        axes[0].twiss_conj = self.names.y
        axes[1].twiss_name = self.names.y
        axes[1].twiss_conj = self.names.x

        # Tune the builtin coord status message on the toolbar:
        axes[0].format_coord = partial(self.format_coord, self.names.x)
        axes[1].format_coord = partial(self.format_coord, self.names.y)

        self.set_twiss_curve(self.basename)

    @property
    def backend_figure(self):
        return self.figure.backend_figure

    def format_coord(self, name, x, y):
        unit = self.unit
        elem = self.segment.get_element_by_position(x * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', x, get_raw_label(unit['s'])),
                 coord_fmt(name, y, get_raw_label(unit[name]))]
        if elem and 'name' in elem:
            parts.insert(0, 'elem={0}'.format(elem['name']))
        return ', '.join(parts)

    def get_label(self, name):
        return self.label.get(name, name) + ' ' + get_unit_label(self.unit.get(name))

    def plot(self):
        """Replot from clean state."""
        self.update_graph_data()
        fig = self.figure
        fig.clear()
        fig.axes[0].set_ylabel(self.get_label(self.names.x))
        fig.axes[1].set_ylabel(self.get_label(self.names.y))
        fig.set_slabel(self.get_label(self.names.s))
        self.scene_graph.plot()
        fig.draw()

    def draw(self):
        self.figure.draw()

    def update(self):
        """Update existing plot after TWISS recomputation."""
        self.update_graph_data()
        self.scene_graph.update()
        self.draw()

    def remove(self):
        self.scene_graph.remove()
        self.segment.updated.disconnect(self.update)

    def get_ax_by_name(self, name):
        return self.figure.axes[self.names.index(name)]

    def get_axes_name(self, axes):
        return self.names[self.figure.axes.index(axes)]

    def get_conjugate(self, name):
        return self.names[1-self.names.index(name)]

    def set_twiss_curve(self, basename):
        """
        Add an X/Y pair of lines of TWISS parameters into the figure.

        :param str basename: stem of the parameter name, e.g. 'bet'
        """
        sname = 's'
        xname = basename + 'x'
        yname = basename + 'y'
        style = self.config['curve_style']
        axes = self.figure.axes
        get_sdata = partial(self.get_float_data, 's', sname)
        get_xdata = partial(self.get_float_data, 'x', xname)
        get_ydata = partial(self.get_float_data, 'y', yname)
        for curve in filter(None, self.scene_graph.items[0:2]):
            curve.remove()
        self.scene_graph.items[0:2] = [
            self.backend.Curve(axes[0], get_sdata, get_xdata, style['x']),
            self.backend.Curve(axes[1], get_sdata, get_ydata, style['y']),
        ]

    def update_graph_data(self):
        self.graph_data = self.segment.get_graph_data(self.plotname)

    def get_float_data(self, name, quant_name):
        """Get data for the given parameter from segment."""
        return strip_unit(self.graph_data[name], self.unit[quant_name])

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

    @property
    def plotname(self):
        translate = {
            'alf': 'alfa',
            'bet': 'beta',
            'env': 'envelope',
            'pos': 'position',
        }
        return translate.get(self.basename, self.basename)


class ElementIndicators(object):

    """
    Draw beam line elements (magnets etc) into a :class:`TwissFigure`.
    """

    def __init__(self, axes, figure, style):
        self.axes = axes
        self.figure = figure
        self.style = style
        self.lines = []

    @property
    def s_unit(self):
        return self.figure.unit[self.figure.names.s]

    @property
    def elements(self):
        return self.figure.segment.elements

    def plot(self):
        """Draw the elements into the canvas."""
        axes = self.axes
        s_unit = self.s_unit
        for elem in self.elements:
            elem_type = self.get_element_type(elem)
            if elem_type is None:
                continue
            at = strip_unit(elem['at'], s_unit)
            if strip_unit(elem['l']) != 0:
                patch_w = strip_unit(elem['l'], s_unit)
                line = axes.axvspan(at, at + patch_w, **elem_type)
            else:
                line = axes.vlines(at, **elem_type)
            self.lines.append(line)

    def update(self):
        pass

    def remove(self):
        for line in self.lines:
            line.remove()
        del self.lines[:]

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


class CheckTool(object):

    action = None
    active = False

    def setChecked(self, checked):
        self.action.setChecked(checked)

    def onToggle(self, active):
        """Update enabled state to match the UI."""
        if active == self.active:
            return
        self.active = active
        if active:
            self.activate()
        else:
            self.deactivate()

    def action(self):
        icon = self.icon
        if isinstance(icon, QtGui.QStyle.StandardPixmap):
            icon =  self.plot.style().standardIcon(icon)
        action = self.action = QtGui.QAction(icon, self.text, self.plot)
        action.setCheckable(True)
        action.toggled.connect(self.onToggle)
        return action


class CaptureTool(CheckTool):

    def action(self):
        action = super(CaptureTool, self).action()
        self.plot.addCapture(self.mode, action.setChecked)
        return action


#----------------------------------------
# Toolbar item for matching
#----------------------------------------

Constraint = namedtuple('Constraint', ['elem', 'axis', 'value'])


class MatchTool(CaptureTool):

    """
    This toolbar item performs (when checked) simple interactive matching
    via mouse clicks into the plot window.
    """

    mode = 'MATCH'
    short = 'match constraints'
    text = 'Match for desired target value'

    @property
    def icon(self):
        with PackageResource('madqt.data', 'target.xpm').filename() as xpm:
            return QtGui.QIcon(QtGui.QPixmap(xpm, 'XPM'))

    def __init__(self, plot):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.plot = plot
        self.segment = plot.figure.segment
        self.rules = plot.figure.config['matching']
        self.constraints = []
        self.markers = ConstraintMarkers(plot.figure, self.constraints)

    @property
    def elements(self):
        return self.segment.elements

    def activate(self):
        """Start matching mode."""
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.figure.scene_graph.items.append(self.markers)
        # TODO: insert markers

    def deactivate(self):
        """Stop matching mode."""
        self.clearConstraints()
        self.markers.draw()
        self.plot.figure.scene_graph.items.remove(self.markers)
        self.plot.buttonPress.disconnect(self.onClick)
        self.plot.endCapture(self.mode)

    def onClick(self, event):

        """
        Draw new constraint and perform matching.

        Invoked after the user clicks in matching mode.
        """

        elem = event.elem
        name = event.axes.twiss_name
        conj = event.axes.twiss_conj

        if elem is None or 'name' not in elem:
            return

        if event.button == 2:
            self.removeConstraint(elem, name)
            self.removeConstraint(elem, conj)
            return
        elif event.button != 1:
            return

        shift = bool(event.guiEvent.modifiers() & Qt.ShiftModifier)
        control = bool(event.guiEvent.modifiers() & Qt.ControlModifier)

        # By default, the list of constraints will be reset. The shift/alt
        # keys are used to add more constraints.
        if not shift and not control:
            self.clearConstraints()

        # add the clicked constraint
        self.addConstraint(Constraint(elem, name, event.y))

        # add another constraint to hold the orthogonal axis constant
        orth_env = self.segment.get_twiss(elem['name'], conj)
        self.addConstraint(Constraint(elem, conj, orth_env))
        self.markers.draw()

        with waitCursor():
            self.match()

    def _allvars(self, axis):
        # filter element list for usable types:
        param_spec = self.rules.get(axis, {})
        return [(elem, param_spec[elem['type']])
                for elem in self.elements
                if elem['type'] in param_spec]

    def match(self):

        """Perform matching according to current constraints."""

        segment = self.segment
        universe = self.segment.universe
        transform = MatchTransform(segment)

        # transform constraints (envx => betx, etc)
        constraints = [
            Constraint(c.elem, *getattr(transform, c.axis)(c.value))
            for c in self.constraints]

        # The following uses a greedy algorithm to select all elements that
        # can be used for varying. This means that for advanced matching it
        # will most probably not work.
        # Copy all needed variable lists (for later modification):
        axes = {c.axis for c in constraints}
        allvars = {axis: self._allvars(axis)[:] for axis in axes}
        vary = []
        for c in constraints:
            at = c.elem['at']
            allowed = [v for v in allvars[c.axis] if v[0]['at'] < at]
            if not allowed:
                # No variable in range found! Ok.
                continue
            v = max(allowed, key=lambda v: v[0]['at'])
            expr = _get_any_elem_param(v[0], v[1])
            if expr is None:
                allvars[c.axis].remove(v)
            else:
                vary.append(expr)
                for c in allvars.values():
                    try:
                        c.remove(v)
                    except ValueError:
                        pass

        # create constraints list to be passed to Madx.match
        madx_constraints = [
            {'range': elem['name'],
             axis: universe.utool.strip_unit(axis, val)}
            for elem, axis, val in constraints]

        twiss_args = universe.utool.dict_strip_unit(segment.twiss_args)
        universe.madx.match(sequence=segment.sequence.name,
                            vary=vary,
                            constraints=madx_constraints,
                            twiss_init=twiss_args)
        segment.retrack()

    def findConstraint(self, elem, axis):
        """Find and return the constraint for the specified element."""
        return [c for c in self.constraints
                if c.elem['name'] == elem['name'] and c.axis == axis]

    def addConstraint(self, constraint):
        """Add constraint and perform matching."""
        self.removeConstraint(constraint.elem, constraint.axis)
        self.constraints.append(constraint)

    def removeConstraint(self, elem, axis):
        """Remove the constraint for elem."""
        self.constraints[:] = [
            c for c in self.constraints
            if c.elem['name'] != elem['name'] or c.axis != axis]

    def clearConstraints(self):
        """Remove all constraints."""
        del self.constraints[:]
        self.markers.draw()


class MatchTransform(object):

    def __init__(self, segment):
        self._ex = segment.summary['ex']
        self._ey = segment.summary['ey']

    def envx(self, val):
        return 'betx', val*val/self._ex

    def envy(self, val):
        return 'bety', val*val/self._ey

    def x(self, val):
        return 'x', val

    posx = x

    def y(self, val):
        return 'y', val

    posy = y


def _get_any_elem_param(elem, params):
    for param in params:
        try:
            return elem[param]._expression
        except KeyError:
            pass
        except AttributeError:
            if strip_unit(elem[param]) != 0.0:
                return elem['name'] + '->' + param
    raise ValueError()


class ConstraintMarkers(SceneElement):

    def __init__(self, figure, constraints):
        self.figure = figure
        self.style = figure.config['constraint_style']
        self.lines = []
        self.constraints = constraints

    def draw(self):
        self.update()
        self.figure.draw()

    def plot(self):
        for constraint in self.constraints:
            self.plotConstraint(*constraint)

    def update(self):
        self.remove()
        self.plot()

    def remove(self):
        for line in self.lines:
            line.remove()
        del self.lines[:]

    def plotConstraint(self, elem, axis, envelope):
        """Draw one constraint representation in the graph."""
        figure = self.figure
        ax = figure.get_ax_by_name(axis)
        at = elem['at'] + elem['l']         # TODO: how to match at center?
        self.lines.extend(ax.plot(
            strip_unit(at, figure.unit[figure.names.s]),
            strip_unit(envelope, figure.unit[axis]),
            **self.style))


#----------------------------------------
# Toolbar item for info boxes
#----------------------------------------

class InfoTool(CaptureTool):

    """
    Opens info boxes when clicking on an element.
    """

    mode = 'INFO'
    short = 'element info'
    icon = QtGui.QStyle.SP_MessageBoxInformation
    text = 'Show element info boxes'

    def __init__(self, plot):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.plot = plot
        self.segment = plot.figure.segment
        self.selection = self.segment.universe.selection

    def activate(self):
        """Start select mode."""
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.keyPress.connect(self.onKey)
        self.plot.canvas.setFocus()

    def deactivate(self):
        """Stop select mode."""
        self.plot.buttonPress.disconnect(self.onClick)
        self.plot.keyPress.disconnect(self.onKey)
        self.plot.endCapture(self.mode)

    def onClick(self, event):
        """Display a popup window with info about the selected element."""

        elem = event.elem
        if event.elem is None or 'name' not in elem:
            return
        elem_name = elem['name']

        shift = bool(event.guiEvent.modifiers() & Qt.ShiftModifier)
        control = bool(event.guiEvent.modifiers() & Qt.ControlModifier)

        # By default, show info in an existing dialog. The shift/ctrl keys
        # are used to open more dialogs:
        selected = self.selection.elements
        if selected and not shift and not control:
            selected[self.selection.top] = elem_name
        elif shift:
            # stack box
            selected.append(elem_name)
        else:
            selected.insert(0, elem_name)

        # Set focus to parent window, so left/right cursor buttons can be
        # used immediately.
        self.plot.canvas.setFocus()

    def onKey(self, event):
        selected = self.selection.elements
        if not selected:
            return
        if 'left' in event.key:
            move_step = -1
        elif 'right' in event.key:
            move_step = 1
        else:
            return
        top = self.selection.top
        elements = self.segment.elements
        old_name = selected[top]
        old_index = self.segment.get_element_index(old_name)
        new_index = old_index + move_step
        new_name = elements[new_index % len(elements)]
        selected[top] = new_name


class ElementMarkers(object):

    def __init__(self, figure, selection):
        self.figure = figure
        self.style = figure.config['select_style']
        self.lines = []
        self.selection = selection
        selection.elements.update_after.connect(
            lambda *args: self.draw())

    def draw(self):
        self.update()
        self.figure.draw()

    def plot(self):
        axx, axy = self.figure.figure.axes
        segment = self.figure.segment
        for el_name in self.selection.elements:
            element = segment.get_element_by_name(el_name)
            self.plotMarker(axx, element)
            self.plotMarker(axy, element)

    def update(self):
        self.remove()
        self.plot()

    def remove(self):
        for line in self.lines:
            line.remove()
        del self.lines[:]

    def plotMarker(self, ax, element):
        """Draw the elements into the canvas."""
        s_unit = self.figure.unit[self.figure.names.s]
        at = strip_unit(element['at'], s_unit)
        self.lines.append(ax.axvline(at, **self.style))


#----------------------------------------
# Compare tool
#----------------------------------------


class CompareTool(CheckTool):

    """
    Display a precomputed reference curve for comparison.
    """

    short = 'Show reference curve'
    icon = QtGui.QStyle.SP_DirLinkIcon
    text = 'Show MIRKO envelope for comparison. The envelope is computed for the default parameters.'

    # TODO: allow to plot any dynamically loaded curve from any file

    def __init__(self, plot):
        """
        The reference curve is NOT visible by default.
        """
        self.plot = plot
        self.style = plot.figure.config['reference_style']
        self.curve = None

    def activate(self):
        if not self.curve:
            self.createCurve()
        if self.curve:
            self.curve.plot()
            self.plot.figure.scene_graph.items.append(self.curve)
            self.plot.figure.draw()
        else:
            self.setChecked(False)

    def deactivate(self):
        if self.curve:
            self.curve.remove()
            self.plot.figure.scene_graph.items.remove(self.curve)
            self.plot.figure.draw()
            self.curve = None

    def createCurve(self):
        self.curve = None
        try:
            data = self.getData()
        except KeyError:
            return
        figure = self.plot.figure
        self.curve = SceneGraph([
            self.plot_ax(data, figure.figure.axes[0], figure.names.x),
            self.plot_ax(data, figure.figure.axes[1], figure.names.y),
        ])

    def plot_ax(self, data, axes, name):
        """Plot the envelope into the figure."""
        figure = self.plot.figure
        sname = figure.names.s
        return figure.backend.Curve(
            axes,
            lambda: strip_unit(data[sname], figure.unit[sname]),
            lambda: strip_unit(data[name], figure.unit[name]),
            self.style)

    def getData(self):
        metadata, resource = self.getMeta()
        column_info = metadata['columns']
        figure = self.plot.figure
        columns = [column_info[ax] for ax in figure.names]
        usecols = [column['column'] for column in columns]
        with resource.filename() as f:
            ref_data = np.loadtxt(f, usecols=usecols, unpack=True)
        return {
            name: from_config(column['unit']) * data
            for name, column, data in zip(figure.names, columns, ref_data)
        }

    def getMeta(self):
        universe = self.plot.figure.segment.universe
        metadata = universe.data['review']
        resource = universe.repo.get(metadata['file'])
        return metadata, resource
