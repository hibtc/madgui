"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

from functools import partial

from madgui.qt import QtGui, Qt
from madgui.core.worker import fetch_all
from madgui.core.base import Object, Signal

from madgui.util.misc import memoize, strip_suffix, SingleWindow
from madgui.util.collections import List, maintain_selection
from madgui.core.unit import (
    strip_unit, from_config, get_raw_label, allclose)
from madgui.resource.package import PackageResource
from madgui.plot.base import SimpleArtist, SceneGraph
from madgui.widget.dialog import Dialog


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

    def __init__(self, scene, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scene = scene
        self.scene.graph_changed.connect(self.update_index)
        items = [(l, n) for n, l in scene.model.get_graphs().items()]
        for label, name in sorted(items):
            self.addItem(label, name)
        self.update_index()
        self.currentIndexChanged.connect(self.change_figure)

    def change_figure(self, index):
        self.scene.set_graph(self.itemData(index))

    def update_index(self):
        self.setCurrentIndex(self.findData(self.scene.graph_name))


class TwissFigure(Object):

    """A figure containing some X/Y twiss parameters."""

    xlim = None
    snapshot_num = 0
    axes = ()

    graph_changed = Signal()

    def __init__(self, figure, model, config):
        super().__init__()
        self.model = model
        self.config = config
        self.figure = figure
        self.matcher = self.model.get_matcher()
        # scene
        self.shown_curves = List()
        self.loaded_curves = List()
        maintain_selection(self.shown_curves, self.loaded_curves)
        self.twiss_curves = SceneGraph()
        self.user_curves = ListView(
            partial(make_user_curve, self),
            self.shown_curves)
        self.indicators = IndicatorManager()
        self.indicators.enable(False)
        self.select_markers = SceneGraph()
        self.constr_markers = ListView(
            partial(SimpleArtist, draw_constraint, self),
            self.matcher.constraints)
        self.scene_graph = SceneGraph([
            self.indicators,
            self.select_markers,
            self.constr_markers,
            self.twiss_curves,
            self.user_curves,
        ])
        self.scene_graph.parent = self.figure   # for invalidation
        # style
        self.x_name = 's'
        self.x_label = config['x_label']
        self.x_unit = from_config(config['x_unit'])
        self.element_style = config['element_style']
        # slots
        self.model.twiss.updated.connect(self.update, Qt.QueuedConnection)

    def attach(self, plot):
        self.plot = plot
        plot.set_scene(self)
        plot.addTool(InfoTool(plot))
        plot.addTool(MatchTool(plot))
        plot.addTool(CompareTool(plot, self.shown_curves))

    graph_name = None
    def set_graph(self, graph_name):
        if graph_name == self.graph_name:
            return
        self.graph_name = graph_name
        self.relayout()
        self.graph_changed.emit()

    def relayout(self):
        """Called to change the number of axes, etc."""
        self.remove()
        self.update_graph_data()
        self.axes = axes = self.figure.set_num_axes(len(self.graph_info.curves))
        self.indicators.destroy()
        self.indicators.create(axes, self, self.element_style)
        self.select_markers.destroy()
        self.select_markers.clear([
            ListView(partial(SimpleArtist, draw_selection_marker, ax, self),
                     self.model.selection.elements)
            for ax in axes
        ])
        self.twiss_curves.destroy()
        self.twiss_curves.clear([
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
        self.draw()

    def draw(self):
        """Replot from clean state."""
        for curve in self.twiss_curves.items:
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

    def remove(self):
        for ax in self.axes:
            ax.cla()
        self.scene_graph.on_remove()

    def destroy(self):
        self.model.twiss.updated.disconnect(self.update)
        self.scene_graph.destroy()

    def format_coord(self, ax, x, y):
        # Avoid StopIteration while hovering the graph and loading another
        # model/curve:
        if not self.twiss_curves.items:
            return ''
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0:.6f}{1}".format
        curve = next(c for c in self.twiss_curves.items if c.axes is ax)
        parts = [coord_fmt(x, get_raw_label(curve.x_unit)),
                 coord_fmt(y, get_raw_label(curve.y_unit))]
        elem = self.model.get_element_by_mouse_position(ax, x * curve.x_unit)
        if elem and 'name' in elem:
            name = strip_suffix(elem.Name, '[0]')
            parts.insert(0, name.upper())
        return ', '.join(parts)

    def update(self):
        """Update existing plot after TWISS recomputation."""
        self.update_graph_data()
        self.twiss_curves.update()

    def update_graph_data(self):
        self.graph_info, self.graph_data = \
            self.model.get_graph_data(self.graph_name, self.xlim)
        self.graph_name = self.graph_info.name

    def get_float_data(self, curve_info, column):
        """Get data for the given parameter from model."""
        return self.graph_data[curve_info.name][:,column]

    def get_curve_by_name(self, name):
        return next((c for c in self.twiss_curves.items if c.y_name == name), None)

    def xlim_changed(self, ax):
        xstart, ystart, xdelta, ydelta = ax.viewLim.bounds
        xend = xstart + xdelta
        self.xlim = self.model.elements.bound_range((
            self.x_unit * xstart,
            self.x_unit * xend))
        if not allclose(self.xlim, self.data_lim()):
            ax.set_autoscale_on(False)
            self.update()
            ax.set_autoscale_on(True)

    def data_lim(self):
        curve = next(iter(self.graph_data))
        xdata = self.graph_data[curve][:,0]
        return (self.x_unit * xdata[0],
                self.x_unit * xdata[-1])

    @property
    def show_indicators(self):
        return self.indicators.enabled

    @show_indicators.setter
    def show_indicators(self, show):
        if self.show_indicators != show:
            self.indicators.enable(show)

    @SingleWindow.factory
    def _curveManager(self):
        from madgui.widget.curvemanager import CurveManager
        widget = CurveManager(self)
        dialog = Dialog(self.plot.window())
        dialog.setWidget(widget, tight=True)
        dialog.setWindowTitle("Curve manager")
        dialog.show()
        return dialog


class Curve(SimpleArtist):

    """Plot a TWISS parameter curve model into a 2D figure."""

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
        self.invalidate()


class ListView(SceneGraph):

    def __init__(self, fn, model):
        super().__init__()
        self.fn = fn
        self.model = model
        for idx, item in enumerate(model):
            self._add(idx, item)
        model.insert_notify.connect(self._add)
        model.delete_notify.connect(self._rm)
        model.modify_notify.connect(self._chg)

    def _add(self, idx, item):
        self.insert(idx, self.fn(item))

    def _rm(self, idx):
        self.pop(self.items[idx])

    def _chg(self, idx, val):
        self._rm(idx)
        self._add(idx, val)

    def destroy(self):
        self.model.insert_notify.disconnect(self._add)
        self.model.delete_notify.disconnect(self._rm)
        self.model.modify_notify.disconnect(self._chg)
        super().destroy()


class IndicatorManager(SceneGraph):

    _fetch = None

    def create(self, axes, scene, style):
        self.clear()
        callback = lambda elements: self.extend([
            ElementIndicators(ax, scene, style, elements)
            for ax in axes
        ])
        self._fetch = fetch_all(scene.model.elements, callback, block=0.5)

    def remove(self):
        if self._fetch:
            self._fetch.stop()
            self._fetch = None
        super().remove()


class ElementIndicators(SimpleArtist):

    """
    Draw beam line elements (magnets etc) into a :class:`TwissFigure`.
    """

    def __init__(self, axes, scene, style, elements):
        super().__init__(self._draw)
        self.axes = axes
        self.scene = scene
        self.style = style
        self.elements = elements

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
        at = strip_unit(elem.At, x_unit)
        if strip_unit(elem.L) != 0:
            patch_w = strip_unit(elem.L, x_unit)
            return self.axes.axvspan(at, at + patch_w, **style)
        else:
            return self.axes.axvline(at, **style)

    def get_element_style(self, elem):
        """Return the element type name used for properties like coloring."""
        if 'type' not in elem or 'at' not in elem:
            return None
        type_name = elem.Type.lower()
        focussing = None
        if type_name == 'quadrupole':
            focussing = strip_unit(elem.K1) > 0
        elif type_name == 'sbend':
            focussing = strip_unit(elem.Angle) > 0
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

    def __init__(self, plot):
        self.plot = plot

    # NOTE: always go through setChecked in order to de-/activate!
    # Calling de-/activate directly will leave behind inconsistent state.
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

    with PackageResource('madgui.data', 'target.xpm').filename() as xpm:
        icon = QtGui.QIcon(QtGui.QPixmap(xpm, 'XPM'))

    def __init__(self, plot):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.plot = plot
        self.model = plot.scene.model
        self.matcher = self.model.get_matcher()
        self.matcher.finished.connect(partial(self.setChecked, False))

    def activate(self):
        """Start matching mode."""
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.window().parent().viewMatchDialog.create()

    def deactivate(self):
        """Stop matching mode."""
        self.plot.buttonPress.disconnect(self.onClick)
        self.plot.endCapture(self.mode)

    def onClick(self, event):
        """Handle clicks into the figure in matching mode."""
        # If the selected plot has two curves, select the primary/alternative
        # (i.e. first/second) curve according to whether the user pressed ALT:
        curves = self.plot.scene.twiss_curves.items
        index = int(bool(self.plot.scene.figure.share_axes and
                         event.guiEvent.modifiers() & Qt.AltModifier and
                         len(curves) > 1))
        curve = [c for c in curves if c.axes is event.axes][index]
        name = curve.y_name
        if event.button == 1: return self.on_left_click(event, curves, name)
        if event.button == 2: return self.on_middle_click(event, curves, name)

    def on_middle_click(self, event, curves, name):
        """Remove constraint nearest to cursor location."""
        constraints = [c for c in self.matcher.constraints
                        if c.axis == name]
        if constraints:
            cons = min(constraints, key=lambda c: abs(c.pos-event.x))
            elem = cons.elem
            for c in curves:
                self.removeConstraint(elem, c.y_name)

    def on_left_click(self, event, curves, name):
        """Add constraint at cursor location."""
        shift = bool(event.guiEvent.modifiers() & Qt.ShiftModifier)
        control = bool(event.guiEvent.modifiers() & Qt.ControlModifier)

        # By default, the list of constraints will be reset. The shift/alt
        # keys are used to add more constraints.
        if not shift and not control:
            self.clearConstraints()

        # add the clicked constraint
        from madgui.correct.match import Constraint
        elem, pos = self.model.get_best_match_pos(event.x)
        constraints = [Constraint(elem, pos, name, event.y)]

        if self.matcher.mirror_mode:
            # add another constraint to hold the orthogonal axis constant
            # TODO: should do this only once for each yname!
            constraints.extend([
                Constraint(elem, pos, c.y_name,
                        self.model.get_twiss(elem.Name, c.y_name, pos))
                for c in curves
                if c.y_name != name
            ])

        constraints = sorted(constraints, key=lambda c: (c.pos, c.axis))
        self.addConstraints(constraints)

        self.matcher.detect_variables()
        if len(self.matcher.variables) > 0:
            self.matcher.match()

    def addConstraints(self, constraints):
        """Add constraint and perform matching."""
        for constraint in constraints:
            self.removeConstraint(constraint.elem, constraint.axis)
        self.matcher.constraints.extend(constraints)

    def removeConstraint(self, elem, axis):
        """Remove the constraint for elem."""
        indexes = [i for i, c in enumerate(self.matcher.constraints)
                   if c.elem.El_id == elem.El_id and c.axis == axis]
        for i in indexes[::-1]:
            del self.matcher.constraints[i]
        # NOTE: we should probably only delete "automatic" variables, but for
        # now let's just assume this is the right thing...
        del self.matcher.variables[:]

    def clearConstraints(self):
        """Remove all constraints."""
        del self.matcher.constraints[:]
        del self.matcher.variables[:]


def draw_constraint(scene, constraint):
    """Draw one constraint representation in the graph."""
    elem, pos, axis, val = constraint
    curve = scene.get_curve_by_name(axis)
    style = scene.config['constraint_style']
    return curve and curve.axes.plot(
        strip_unit(pos, curve.x_unit),
        strip_unit(val, curve.y_unit),
        **style) or ()


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
        self.model = plot.scene.model
        self.selection = self.model.selection

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
        el_id = event.elem.El_id

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
        elements = self.model.elements
        old_el_id = selected[top]
        old_index = self.model.get_element_index(old_el_id)
        new_index = old_index + move_step
        new_el_id = self.model.elements[new_index % len(elements)].El_id
        selected[top] = new_el_id


def draw_selection_marker(axes, scene, el_idx):
    """In-figure markers for active/selected elements."""
    style = scene.config['select_style']
    element = scene.model.elements[el_idx]
    at = strip_unit(element.At, scene.x_unit)
    return [axes.axvline(at, **style)]


#----------------------------------------
# Compare tool
#----------------------------------------

class CompareTool(CheckTool):

    """
    Display a precomputed reference curve for comparison.

    The reference curve is NOT visible by default.
    """

    short = 'Show reference curve'
    icon = QtGui.QStyle.SP_DirLinkIcon
    text = 'Load data file for comparison.'

    def __init__(self, plot, selection):
        super().__init__(plot)
        self.selection = selection
        selection.update_after.connect(self._update)
        self.plot.scene._curveManager.holds_value.changed.connect(self._update)

    def _update(self, *args):
        self.setChecked(len(self.selection) > 0 or
                        self.plot.scene._curveManager.holds_value.value)

    def activate(self):
        self.plot.scene._curveManager.create()

    def deactivate(self):
        self.selection.clear()


def make_user_curve(scene, idx):
    name, data = scene.loaded_curves[idx]
    style = scene.config['reference_style']
    return SceneGraph([
        Curve(
            curve.axes,
            partial(strip_unit, data[curve.x_name], curve.x_unit),
            partial(strip_unit, data[curve.y_name], curve.y_unit),
            style, label=name,
        )
        for curve in scene.twiss_curves.items
    ])


def ax_label(label, unit):
    if unit in (1, None):
        return label
    return "{} [{}]".format(label, get_raw_label(unit))
