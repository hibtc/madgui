"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

import os
from functools import partial

import numpy as np

from madqt.qt import QtGui, Qt

from madqt.util.qt import waitCursor
from madqt.util.misc import memoize
from madqt.util.collections import List
from madqt.core.unit import (
    strip_unit, from_config, get_raw_label, allclose)
from madqt.resource.package import PackageResource
from madqt.plot.base import Artist, SimpleArtist, SceneGraph
from madqt.widget.filedialog import getOpenFileName


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
        super().__init__(*args, **kwargs)
        self.scene = scene
        graphs = scene.segment.get_graphs()
        items = [(title, name) for name, (_, title) in graphs.items()]
        for label, name in sorted(items):
            self.addItem(label, name)
        self.update_index()
        self.currentIndexChanged.connect(self.change_figure)

    def change_figure(self, index):
        self.scene.set_graph(self.itemData(index))

    def update_index(self):
        self.setCurrentIndex(self.findData(self.scene.graph_name))


class TwissFigure(Artist):

    """A figure containing some X/Y twiss parameters."""

    xlim = None

    def __init__(self, figure, segment, config):
        self.segment = segment
        self.config = config
        self.figure = figure
        # scene
        self.curves = SceneGraph()
        self.indicators = SceneGraph()
        self.indicators.enable(False)
        self.markers = SceneGraph()
        self.scene_graph = SceneGraph([
            self.indicators,
            self.markers,
            self.curves,
        ])
        # style
        self.x_name = 's'
        self.x_label = config['x_label']
        self.x_unit = from_config(config['x_unit'])
        self.element_style = config['element_style']
        # slots
        self.segment.twiss.updated.connect(self.update)

    def attach(self, plot):
        curves = List()
        plot.set_scene(self)
        plot.addTool(InfoTool(plot))
        plot.addTool(MatchTool(plot))
        plot.addTool(CompareTool(plot, curves))
        plot.addTool(LoadFileTool(plot, curves))
        plot.addTool(SaveCurveTool(plot, curves))

    def set_graph(self, graph_name):
        self.graph_name = graph_name
        self.relayout()

    def relayout(self):
        """Called to change the number of axes, etc."""
        self.render(False)
        self.update_graph_data()
        self.axes = axes = self.figure.set_num_axes(len(self.graph_info.curves))
        self.indicators.clear([
            ElementIndicators(ax, self, self.element_style)
            for ax in axes
        ])
        self.markers.clear([
            ElementMarkers(ax, self, self.segment.workspace.selection)
            for ax in axes
        ])
        self.curves.clear([
            Curve(
                ax,
                partial(self.get_float_data, curve_info, 0),
                partial(self.get_float_data, curve_info, 1),
                curve_info.style,
                label=ax_label(curve_info.label, curve_info.unit),
                info=curve_info,
            )
            for ax, curve_info in zip(axes, self.graph_info.curves)
        ])
        self.render()

    def draw(self):
        """Replot from clean state."""
        for curve in self.curves.items:
            ax = curve.axes
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
        self.scene_graph.render()
        self.figure.autoscale()
        self.figure.connect('xlim_changed', self.xlim_changed)
        if self.figure.share_axes:
            ax = self.figure.axes[0]
            # TODO: move legend on the outside
            legend = ax.legend(loc='upper center', fancybox=True, shadow=True, ncol=4)
            legend.draggable()
        self.figure.invalidate()

    def remove(self):
        for ax in self.axes:
            ax.cla()
        self.scene_graph.destroy()

    def destroy(self):
        self.segment.twiss.updated.disconnect(self.update)
        self.scene_graph.destroy()

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

    def invalidate(self):
        self.figure.invalidate()

    def update(self, autoscale=True):
        """Update existing plot after TWISS recomputation."""
        self.update_graph_data()
        self.curves.update()
        if autoscale:
            self.figure.autoscale()
        self.invalidate()

    def update_graph_data(self):
        self.graph_info, self.graph_data = \
            self.segment.get_graph_data(self.graph_name, self.xlim)
        self.graph_name = self.graph_info.short

    def get_float_data(self, curve_info, column):
        """Get data for the given parameter from segment."""
        return self.graph_data[curve_info.name][:,column]

    def get_curve_by_name(self, name):
        return next((c for c in self.curves.items if c.y_name == name), None)

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
        return self.indicators.enabled

    @show_indicators.setter
    def show_indicators(self, show):
        if self.show_indicators != show:
            self.indicators.enable(show)
            self.invalidate()


class Curve(SimpleArtist):

    """Plot a TWISS parameter curve segment into a 2D figure."""

    def __init__(self, axes, get_xdata, get_ydata, style, label=None, info=None):
        """Store meta data."""
        self.axes = axes
        self.get_xdata = get_xdata
        self.get_ydata = get_ydata
        self.style = style
        self.label = label
        self.lines = ()
        self.info = info

    def draw(self):
        """Make one subplot."""
        xdata = self.get_xdata()
        ydata = self.get_ydata()
        self.axes.set_xlim(xdata[0], xdata[-1])
        self.lines = self.axes.plot(xdata, ydata, label=self.label, **self.style)
        self.line, = self.lines

    def update(self):
        """Update the y values for one subplot."""
        self.line.set_xdata(self.get_xdata())
        self.line.set_ydata(self.get_ydata())


class ElementIndicators(SimpleArtist):

    """
    Draw beam line elements (magnets etc) into a :class:`TwissFigure`.
    """

    def __init__(self, axes, scene, style):
        super().__init__(self._draw)
        self.axes = axes
        self.scene = scene
        self.style = style

    @property
    def elements(self):
        return self.scene.segment.elements

    def _draw(self):
        """Draw the elements into the canvas."""
        return [
            self.make_element_indicator(elem, style)
            for elem in self.elements
            for style in [self.get_element_style(elem)]
            if style is not None
        ]

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


class ButtonTool:

    @memoize
    def action(self):
        icon = self.icon
        if isinstance(icon, QtGui.QStyle.StandardPixmap):
            icon = self.plot.style().standardIcon(icon)
        action = QtGui.QAction(icon, self.text, self.plot)
        action.triggered.connect(self.activate)
        return action


class CheckTool:

    active = False

    def setChecked(self, checked):
        self.action().setChecked(checked)

    def onToggle(self, active):
        """Update enabled state to match the UI."""
        if active == self.active:
            return
        self.active = active
        if active:
            self.activate()
        else:
            self.deactivate()

    @memoize
    def action(self):
        icon = self.icon
        if isinstance(icon, QtGui.QStyle.StandardPixmap):
            icon = self.plot.style().standardIcon(icon)
        action = QtGui.QAction(icon, self.text, self.plot)
        action.setCheckable(True)
        action.toggled.connect(self.onToggle)
        return action


class CaptureTool(CheckTool):

    def action(self):
        action = super().action()
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
        self.plot.scene.scene_graph.add(self.markers)
        self.matcher.finished.connect(self.deactivate)

    def activate(self):
        """Start matching mode."""
        self.active = True
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.window().parent().viewMatchDialog.create()
        # TODO: insert markers

    def deactivate(self):
        """Stop matching mode."""
        self.active = False
        self.clearConstraints()
        self.plot.buttonPress.disconnect(self.onClick)
        self.plot.endCapture(self.mode)
        self.plot.figure.invalidate()

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

        if self.matcher.mirror_mode:
            # add another constraint to hold the orthogonal axis constant
            # TODO: should do this only once for each yname!
            constraints.extend([
                Constraint(elem, pos, c.y_name,
                        self.segment.get_twiss(elem['name'], c.y_name))
                for c in curves
                if c.y_name != name
            ])

        constraints = sorted(constraints, key=lambda c: (c.pos, c.axis))
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


class ConstraintMarkers(SimpleArtist):

    def __init__(self, scene, constraints):
        super().__init__(self._draw)
        self.scene = scene
        self.style = scene.config['constraint_style']
        self.constraints = constraints
        constraints.update_after.connect(lambda *args: self.update())

    def _draw(self):
        return [
            line for constraint in self.constraints
            for line in self.plotConstraint(*constraint)
        ]

    def plotConstraint(self, elem, pos, axis, val):
        """Draw one constraint representation in the graph."""
        curve = self.scene.get_curve_by_name(axis)
        return curve and curve.axes.plot(
            strip_unit(pos, curve.x_unit),
            strip_unit(val, curve.y_unit),
            **self.style) or ()


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
        self.active = True
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.keyPress.connect(self.onKey)
        self.plot.canvas.setFocus()

    def deactivate(self):
        """Stop select mode."""
        self.active = False
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


class ElementMarkers(SimpleArtist):

    """
    In-figure markers for active/selected elements.
    """

    def __init__(self, axes, scene, selection):
        super().__init__(self._draw)
        self.axes = axes
        self.scene = scene
        self.style = scene.config['select_style']
        self.selection = selection
        selection.elements.update_after.connect(
            lambda *args: self.update())

    def _draw(self):
        elements = self.scene.segment.elements
        return [self.plot_marker(elements[el_id])
                for el_id in self.selection.elements]

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
    text = 'Load data file for comparison.'

    # TODO: allow to plot any dynamically loaded curve from any file

    def __init__(self, plot, curves):
        """
        The reference curve is NOT visible by default.
        """
        self.plot = plot
        self.curves = curves
        self.style = plot.scene.config['reference_style']
        self.scene = SceneGraph([])
        self.plot.scene.scene_graph.add(self.scene)
        self.curves.insert_notify.connect(self.add_curve)
        self.curves.delete_notify.connect(self.del_curve)

    def activate(self):
        self.active = True
        self.scene.enable(True)
        self.plot.scene.invalidate()

    def deactivate(self):
        self.active = False
        self.scene.enable(False)
        self.plot.scene.invalidate()

    def add_all(self):
        for i, c in enumerate(self.curves):
            self.add_curve(i, c)

    def add_curve(self, idx, item):
        name, data = item
        scene = self.plot.scene
        c = SceneGraph([
            Curve(
                curve.axes,
                partial(strip_unit, data[curve.x_name], curve.x_unit),
                partial(strip_unit, data[curve.y_name], curve.y_unit),
                self.style,
                label=name,
            )
            for curve in scene.curves.items
        ])
        self.scene.insert(idx, c)
        self.plot.scene.invalidate()

    def del_curve(self, idx):
        self.scene.pop(self.scene.items[idx])
        self.plot.scene.invalidate()


class LoadFileTool(ButtonTool):

    short = 'Load data file'
    icon = QtGui.QStyle.SP_FileIcon
    text = 'Load data file for comparison.'

    dataFileFilters = [
        ("Text files", "*.txt", "*.dat"),
        ("TFS tables", "*.tfs", "*.twiss"),
    ]

    def __init__(self, plot, curves):
        self.plot = plot
        self.curves = curves
        self.folder = self.plot.scene.segment.workspace.repo.path

    def activate(self):
        filename = getOpenFileName(
            self.plot.window(), 'Open data file for comparison',
            self.folder, self.dataFileFilters)
        if filename:
            self.folder, basename = os.path.split(filename)
            data = self.load_file(filename)
            self.curves.append((basename, data))

    def load_file(self, filename):
        from madqt.util.table import read_table, read_tfsfile
        if filename.lower().rsplit('.')[-1] not in ('tfs', 'twiss'):
            return read_table(filename)
        segment = self.plot.scene.segment
        utool = segment.workspace.utool
        table = read_tfsfile(filename)
        data = table.copy()
        # TODO: this should be properly encapsulated:
        if 'sig11' in data:
            data['envx'] = data['sig11'] ** 0.5
        elif 'betx' in data:
            try:
                ex = table.summary['ex']
            except ValueError:
                ex = utool.strip_unit('ex', segment.ex())
            data['envx'] = (data['betx'] * ex) ** 0.5
        if 'sig33' in data:
            data['envy'] = data['sig33']**0.5
        elif 'bety' in data:
            try:
                ey = table.summary['ey']
            except ValueError:
                ey = utool.strip_unit('ey', segment.ey())
            data['envy'] = (data['bety'] * ey) ** 0.5
        return utool.dict_add_unit(data)


class SaveCurveTool(ButtonTool):

    short = 'Save the current curve'
    icon = QtGui.QStyle.SP_DialogSaveButton
    text = 'Save the current curve data for later comparison.'

    def __init__(self, plot, curves):
        self.plot = plot
        self.curves = curves

    def activate(self):
        data = {
            curve.y_name: curve.get_ydata()
            for curve in self.plot.scene.curves.items
        }
        curve = next(iter(self.plot.scene.curves.items))
        data[curve.x_name] = curve.get_xdata()
        self.curves.append(("saved curve", data))


def ax_label(label, unit):
    if unit in (1, None):
        return label
    return "{} [{}]".format(label, get_raw_label(unit))
