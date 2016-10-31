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
    'PlotSelector',
    'TwissFigure',
    'ElementIndicators',
]


#----------------------------------------
# basic twiss figure
#----------------------------------------

class PlotSelector(QtGui.QComboBox):

    """Widget to choose the displayed graph in a TwissFigure."""

    # TODO: show plot names in a first column?

    # TODO: show multiple combobox widgets:
    # - category (e.g. 'Bunch phase space' or 'Radiation integrals')
    # - graph (e.g. 'Integrated I4A Radiation Integral')
    # - curves: all-curves-separate-axes / all-curves-joint-axes / single-curve

    def __init__(self, scene, *args, **kwargs):
        super(PlotSelector, self).__init__(*args, **kwargs)
        self.scene = scene
        graphs = scene.segment.get_graphs()
        items = [(title, name) for name, (_, title) in graphs.items()]
        for label, name in sorted(items):
            self.addItem(label, name)
        self.update_index()
        self.currentIndexChanged.connect(self.change_figure)

    def change_figure(self, index):
        self.scene.graph_name = self.itemData(index)
        self.scene.plot()

    def update_index(self):
        self.setCurrentIndex(self.findData(self.scene.graph_name))


class TwissFigure(object):

    """A figure containing some X/Y twiss parameters."""

    def __init__(self, figure, segment, config):
        self.segment = segment
        self.config = config
        self.figure = figure
        # scene
        self.curves = SceneGraph()
        self.indicators = SceneGraph()
        self.markers = SceneGraph()
        self.scene_graph = SceneGraph([
            # self.indicators,
            self.markers,
            self.curves,
        ])
        # style
        self.x_name = 's'
        self.x_label = config['x_label']
        self.x_unit = from_config(config['x_unit'])
        self.element_style = config['element_style']
        # slots
        self.segment.updated.connect(self.update)

    def attach(self, plot):
        plot.set_scene(self)
        plot.addTool(InfoTool(plot))
        plot.addTool(MatchTool(plot))
        plot.addTool(CompareTool(plot))

    @property
    def graph_name(self):
        return self._graph_name

    @graph_name.setter
    def graph_name(self, graph_name):
        self._graph_name = graph_name
        self.update_graph_data()
        self.scene_graph.clear_items()
        self.axes = axes = self.figure.set_num_axes(len(self.graph_info.curves))
        self.indicators.items.extend([
            ElementIndicators(ax, self, self.element_style)
            for ax in axes
        ])
        self.markers.items.extend([
            ElementMarkers(ax, self, self.segment.universe.selection)
            for ax in axes
        ])
        self.curves.items.extend([
            self.figure.Curve(
                ax,
                partial(self.get_float_data, curve_info, 0),
                partial(self.get_float_data, curve_info, 1),
                curve_info.style)
            for ax, curve_info in zip(axes, self.graph_info.curves)
        ])

    def plot(self):
        """Replot from clean state."""
        for ax, curve_info in zip(self.axes, self.graph_info.curves):
            ax.cla()
            ax.set_ylabel(ax_label(curve_info.label, curve_info.unit))
            # replace formatter method for mouse status:
            ax.format_coord = partial(self.format_coord, ax)
            # set axes properties for convenient access:
            ax.curve_info = curve_info
            ax.x_unit = self.x_unit
            ax.x_name = self.x_name
            ax.y_unit = curve_info.unit
            ax.y_name = curve_info.short
        self.figure.set_xlabel(ax_label(self.x_label, self.x_unit))
        self.scene_graph.plot()
        self.figure.draw()

    def format_coord(self, ax, x, y):
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt(ax.x_name, x, get_raw_label(ax.x_unit)),
                 coord_fmt(ax.y_name, y, get_raw_label(ax.y_unit))]
        elem = self.segment.get_element_by_position(x * ax.x_unit)
        if elem and 'name' in elem:
            parts.insert(0, 'elem={0}'.format(elem['name']))
        return ', '.join(parts)

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

    def update_graph_data(self):
        self.graph_info, self.graph_data = \
            self.segment.get_graph_data(self.graph_name)
        self._graph_name = self.graph_info.short

    def get_float_data(self, curve_info, column):
        """Get data for the given parameter from segment."""
        return self.graph_data[curve_info.name][:,column]

    def get_ax_by_name(self, name):
        return next(ax for ax in self.axes if ax.y_name == name)

    # TODO: scene.show_indicators -> scene.indicators.show()
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


class ElementIndicators(object):

    """
    Draw beam line elements (magnets etc) into a :class:`TwissFigure`.
    """

    def __init__(self, axes, scene, style):
        self.axes = axes
        self.scene = scene
        self.style = style
        self.lines = []

    @property
    def elements(self):
        return self.scene.segment.elements

    def plot(self):
        """Draw the elements into the canvas."""
        self.lines.extend([
            self.make_element_indicator(elem, style)
            for elem in self.elements
            for style in [self.get_element_style(elem)]
            if style is not None
        ])

    def update(self):
        pass

    def remove(self):
        for line in self.lines:
            line.remove()
        del self.lines[:]

    def make_element_indicator(self, elem, style):
        x_unit = self.scene.x_unit
        at = strip_unit(elem['at'], x_unit)
        if strip_unit(elem['l']) != 0:
            patch_w = strip_unit(elem['l'], x_unit)
            return self.axes.axvspan(at, at + patch_w, **style)
        else:
            return self.axes.vlines(at, **style)

    def get_element_style(self, elem):
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

    # TODO: define matching via config file and fix implementation

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
        self.segment = plot.scene.segment
        self.rules = plot.scene.config['matching']
        self.constraints = []
        self.markers = ConstraintMarkers(plot.scene, self.constraints)

    @property
    def elements(self):
        return self.segment.elements

    def activate(self):
        """Start matching mode."""
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.scene.scene_graph.items.append(self.markers)
        # TODO: insert markers

    def deactivate(self):
        """Stop matching mode."""
        self.clearConstraints()
        self.markers.draw()
        self.plot.scene.scene_graph.items.remove(self.markers)
        self.plot.buttonPress.disconnect(self.onClick)
        self.plot.endCapture(self.mode)

    def onClick(self, event):

        """
        Draw new constraint and perform matching.

        Invoked after the user clicks in matching mode.
        """

        elem = event.elem

        if elem is None or 'name' not in elem:
            return

        name = event.axes.y_name
        axes = self.plot.scene.axes

        if event.button == 2:
            for ax in axes:
                self.removeConstraint(elem, ax.y_name)
            self.markers.draw()
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
        for ax in axes:
            if ax.y_name == name:
                continue
            # TODO: tao can do this with exact s positions
            value = self.segment.get_twiss(elem['name'], ax.y_name)
            self.addConstraint(Constraint(elem, ax.y_name, value))

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

        # FIXME: the following is not generic in number of axes

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

    def __getattr__(self, name):
        return lambda val: (name, val)


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

    def __init__(self, scene, constraints):
        self.scene = scene
        self.style = scene.config['constraint_style']
        self.lines = []
        self.constraints = constraints

    def draw(self):
        self.update()
        self.scene.draw()

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

    def plotConstraint(self, elem, axis, val):
        """Draw one constraint representation in the graph."""
        scene = self.scene
        ax = scene.get_ax_by_name(axis)
        pos = elem['at'] + elem['l']         # TODO: how to match at center?
        self.lines.extend(ax.plot(
            strip_unit(pos, ax.x_unit),
            strip_unit(val, ax.y_unit),
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
        self.segment = plot.scene.segment
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
        if 'left' in event.key:
            self.advance_selection(-1)
        elif 'right' in event.key:
            self.advance_selection(+1)

    def advance_selection(self, move_step):
        selected = self.selection.elements
        if not selected:
            return
        top = self.selection.top
        elements = self.segment.elements
        old_name = selected[top]
        old_index = self.segment.get_element_index(old_name)
        new_index = old_index + move_step
        new_name = elements[new_index % len(elements)]['name']
        selected[top] = new_name


class ElementMarkers(object):

    """
    In-figure markers for active/selected elements.
    """

    def __init__(self, axes, scene, selection):
        self.axes = axes
        self.scene = scene
        self.style = scene.config['select_style']
        self.lines = []
        self.selection = selection
        selection.elements.update_after.connect(
            lambda *args: self.draw())

    def draw(self):
        self.update()
        self.scene.draw()

    def plot(self):
        segment = self.scene.segment
        elements = [segment.get_element_by_name(el_name)
                    for el_name in self.selection.elements]
        self.lines.extend(map(self.plot_marker, elements))

    def update(self):
        self.remove()
        self.plot()

    def remove(self):
        for line in self.lines:
            line.remove()
        del self.lines[:]

    def plot_marker(self, element):
        """Draw the elements into the canvas."""
        at = strip_unit(element['at'], self.scene.x_unit)
        return self.axes.axvline(at, **self.style)


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
        self.style = plot.scene.config['reference_style']
        self.curve = None

    def activate(self):
        if not self.curve:
            self.createCurve()
        if self.curve:
            self.curve.plot()
            self.plot.scene.scene_graph.items.append(self.curve)
            self.plot.scene.draw()
        else:
            self.setChecked(False)

    def deactivate(self):
        if self.curve:
            self.curve.remove()
            self.plot.scene.scene_graph.items.remove(self.curve)
            self.plot.scene.draw()
            self.curve = None

    def createCurve(self):
        self.curve = None
        try:
            data = self.getData()
        except KeyError:
            return
        self.curve = SceneGraph([
            self.plot_ax(data, ax)
            for ax in self.plot.scene.axes
        ])

    def plot_ax(self, data, axes):
        """Plot the envelope into the figure."""
        scene = self.plot.scene
        curve = axes.curve_info
        return scene.figure.Curve(
            axes,
            lambda: strip_unit(data[axes.x_name], axes.x_unit),
            lambda: strip_unit(data[axes.y_name], axes.y_unit),
            self.style)

    def getData(self):
        metadata, resource = self.getMeta()
        column_info = metadata['columns']
        scene = self.plot.scene
        col_names = [curve.short for curve in scene.graph_info.curves]
        col_names += [scene.x_name]
        col_infos = [column_info[col_name] for col_name in col_names]
        usecols = [col_info['column'] for col_info in col_infos]
        with resource.filename() as f:
            ref_data = np.loadtxt(f, usecols=usecols, unpack=True)
        return {
            name: from_config(column['unit']) * data
            for name, column, data in zip(col_names, col_infos, ref_data)
        }

    def getMeta(self):
        universe = self.plot.scene.segment.universe
        metadata = universe.data['review']
        resource = universe.repo.get(metadata['file'])
        return metadata, resource


def ax_label(label, unit):
    if unit in (1, None):
        return label
    return "{} [{}]".format(label, get_raw_label(unit))
