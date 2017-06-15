# encoding: utf-8
"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from functools import partial

import numpy as np

from madqt.qt import QtGui, Qt

from madqt.util.qt import waitCursor
from madqt.core.unit import (
    strip_unit, from_config, get_raw_label, allclose)
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

    xlim = None

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
        self.relayout()

    def relayout(self):
        self.update_graph_data()
        self.scene_graph.clear_items()
        self.axes = axes = self.figure.set_num_axes(len(self.graph_info.curves))
        self.indicators.items.extend([
            ElementIndicators(ax, self, self.element_style)
            for ax in axes
        ])
        self.markers.items.extend([
            ElementMarkers(ax, self, self.segment.workspace.selection)
            for ax in axes
        ])
        self.curves.items.extend([
            self.figure.Curve(
                ax,
                partial(self.get_float_data, curve_info, 0),
                partial(self.get_float_data, curve_info, 1),
                curve_info.style,
                label=ax_label(curve_info.label, curve_info.unit),
                info=curve_info,
            )
            for ax, curve_info in zip(axes, self.graph_info.curves)
        ])

    def plot(self):
        """Replot from clean state."""
        for curve in self.curves.items:
            ax = curve.axes
            ax.cla()
            if not self.figure.share_axes:
                ax.set_ylabel(curve.label)
            # replace formatter method for mouse status:
            ax.format_coord = partial(self.format_coord, ax)
            # set axes properties for convenient access:
            curve.x_unit = self.x_unit
            curve.x_name = self.x_name
            curve.y_unit = curve.info.unit
            curve.y_name = curve.info.short
            ax.x_unit = curve.x_unit
            ax.y_unit = curve.y_unit
        self.figure.set_xlabel(ax_label(self.x_label, self.x_unit))
        self.scene_graph.plot()
        self.figure.autoscale()
        self.figure.connect('xlim_changed', self.xlim_changed)
        if self.figure.share_axes:
            ax = self.figure.axes[0]
            legend = ax.legend(loc='upper center', fancybox=True, shadow=True, ncol=4)
            legend.draggable()
        self.figure.draw()

    def format_coord(self, ax, x, y):
        # Avoid StopIteration while hovering the graph and loading another
        # model/curve:
        if not self.curves.items:
            return ''
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        curve = next(c for c in self.curves.items if c.axes is ax)
        parts = [coord_fmt(curve.x_name, x, get_raw_label(curve.x_unit)),
                 coord_fmt(curve.y_name, y, get_raw_label(curve.y_unit))]
        elem = self.segment.get_element_by_position(x * curve.x_unit)
        if elem and 'name' in elem:
            parts.insert(0, 'elem={0}'.format(elem['name']))
        return ', '.join(parts)

    def draw(self):
        self.figure.draw()

    def update(self, autoscale=True):
        """Update existing plot after TWISS recomputation."""
        self.update_graph_data()
        self.scene_graph.update()
        if autoscale:
            self.figure.autoscale()
        self.draw()

    def remove(self):
        self.scene_graph.remove()
        self.segment.updated.disconnect(self.update)

    def update_graph_data(self):
        self.graph_info, self.graph_data = \
            self.segment.get_graph_data(self.graph_name, self.xlim)
        self._graph_name = self.graph_info.short

    def get_float_data(self, curve_info, column):
        """Get data for the given parameter from segment."""
        return self.graph_data[curve_info.name][:,column]

    def get_curve_by_name(self, name):
        return next(c for c in self.curves.items if c.y_name == name)

    def xlim_changed(self, ax):
        xstart, ystart, xdelta, ydelta = ax.viewLim.bounds
        xend = xstart + xdelta
        self.xlim = self.segment.elements.bound_range((
            self.x_unit * xstart,
            self.x_unit * xend))
        if not allclose(self.xlim, self.data_lim()):
            ax.set_autoscale_on(False)
            self.update(autoscale=False)

    def data_lim(self):
        curve = next(iter(self.graph_data))
        xdata = self.graph_data[curve][:,0]
        return (self.x_unit * xdata[0],
                self.x_unit * xdata[-1])

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
            return self.axes.axvline(at, **style)

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


class MatchTool(CaptureTool):

    """
    This toolbar item performs (when checked) simple interactive matching
    via mouse clicks into the plot window.
    """

    # TODO: define matching via config file and fix implementation

    mode = 'MATCH'
    short = 'match constraints'
    text = 'Match for desired target value'

    with PackageResource('madqt.data', 'target.xpm').filename() as xpm:
        icon = QtGui.QIcon(QtGui.QPixmap(xpm, 'XPM'))

    def __init__(self, plot):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.plot = plot
        self.segment = plot.scene.segment
        self.matcher = self.segment.get_matcher()
        self.markers = ConstraintMarkers(plot.scene, self.matcher.constraints)
        self.matcher.destroyed.connect(self.deactivate)

    def activate(self):
        """Start matching mode."""
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.scene.scene_graph.items.append(self.markers)
        self.plot.window().parent().viewMatchDialog.create()
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

        elem, pos = self.segment.get_best_match_pos(event.x)

        # If the selected plot has two curves, select the primary/alternative
        # (i.e. first/second) curve according to whether the user pressed ALT:
        curves = self.plot.scene.curves.items
        index = int(bool(self.plot.scene.figure.share_axes and
                         event.guiEvent.modifiers() & Qt.AltModifier and
                         len(curves) > 1))
        curve = [c for c in curves if c.axes is event.axes][index]
        name = curve.y_name

        # Right click: remove constraint
        if event.button == 2:
            for c in curves:
                self.removeConstraint(elem, c.y_name)
            return
        # Proceed only if left click:
        elif event.button != 1:
            return

        shift = bool(event.guiEvent.modifiers() & Qt.ShiftModifier)
        control = bool(event.guiEvent.modifiers() & Qt.ControlModifier)

        # By default, the list of constraints will be reset. The shift/alt
        # keys are used to add more constraints.
        if not shift and not control:
            self.clearConstraints()

        # add the clicked constraint
        from madqt.correct.match import Constraint
        constraints = [Constraint(elem, pos, name, event.y)]
        # add another constraint to hold the orthogonal axis constant
        # TODO: should do this only once for each yname!
        constraints.extend([
            Constraint(elem, pos, c.y_name,
                       self.segment.get_twiss(elem['name'], c.y_name))
            for c in curves
            if c.y_name != name
        ])

        self.addConstraints(constraints)

        with waitCursor():
            self.matcher.detect_variables()
            self.matcher.match()

    def addConstraints(self, constraints):
        """Add constraint and perform matching."""
        for constraint in constraints:
            self.removeConstraint(constraint.elem, constraint.axis)
        self.matcher.constraints.extend(constraints)

    def removeConstraint(self, elem, axis):
        """Remove the constraint for elem."""
        indexes = [i for i, c in enumerate(self.matcher.constraints)
                   if c.elem['el_id'] == elem['el_id'] and c.axis == axis]
        for i in indexes[::-1]:
            del self.matcher.constraints[i]

    def clearConstraints(self):
        """Remove all constraints."""
        del self.matcher.constraints[:]


class ConstraintMarkers(SceneElement):

    def __init__(self, scene, constraints):
        self.scene = scene
        self.style = scene.config['constraint_style']
        self.lines = []
        self.constraints = constraints
        constraints.update_after.connect(lambda *args: self.draw())

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

    def plotConstraint(self, elem, pos, axis, val):
        """Draw one constraint representation in the graph."""
        scene = self.scene
        curve = scene.get_curve_by_name(axis)
        self.lines.extend(curve.axes.plot(
            strip_unit(pos, curve.x_unit),
            strip_unit(val, curve.y_unit),
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
        self.selection = self.segment.workspace.selection

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

        if event.elem is None:
            return
        el_id = event.elem['el_id']

        shift = bool(event.guiEvent.modifiers() & Qt.ShiftModifier)
        control = bool(event.guiEvent.modifiers() & Qt.ControlModifier)

        # By default, show info in an existing dialog. The shift/ctrl keys
        # are used to open more dialogs:
        selected = self.selection.elements
        if selected and not shift and not control:
            selected[self.selection.top] = el_id
        elif shift:
            # stack box
            selected.append(el_id)
        else:
            selected.insert(0, el_id)

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
        old_el_id = selected[top]
        old_index = self.segment.get_element_index(old_el_id)
        new_index = old_index + move_step
        new_el_id = self.segment.elements[new_index % len(elements)]['el_id']
        selected[top] = new_el_id


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
        elements = [segment.elements[el_id]
                    for el_id in self.selection.elements]
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
        scene = self.plot.scene
        self.curve = SceneGraph([
            scene.figure.Curve(
                curve.axes,
                partial(strip_unit, data[curve.x_name], curve.x_unit),
                partial(strip_unit, data[curve.y_name], curve.y_unit),
                self.style,
                label=None, # TODO
            )
            for curve in scene.curves.items
        ])

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
        workspace = self.plot.scene.segment.workspace
        metadata = workspace.data['review']
        resource = workspace.repo.get(metadata['file'])
        return metadata, resource


def ax_label(label, unit):
    if unit in (1, None):
        return label
    return "{} [{}]".format(label, get_raw_label(unit))
