"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

__all__ = [
    'PlotSelector',
    'TwissFigure',
]

import math
import logging
from functools import partial
from collections import namedtuple

import numpy as np

from madgui.qt import QtGui, Qt
from madgui.core.signal import Object, Signal

from madgui.util.qt import load_icon_resource
from madgui.util.misc import memoize, strip_suffix, SingleWindow, cachedproperty
from madgui.util.collections import List, maintain_selection
from madgui.util.unit import (
    to_ui, get_raw_label, ui_units)
from madgui.plot.scene import SimpleArtist, SceneGraph
from madgui.widget.dialog import Dialog

import matplotlib.patheffects as pe     # import *after* madgui.plot.matplotlib
import matplotlib.colors as mpl_colors


PlotInfo = namedtuple('PlotInfo', [
    'name',     # internal graph id (e.g. 'beta.g')
    'title',    # long display name ('Beta function')
    'curves',   # [CurveInfo]
])

CurveInfo = namedtuple('CurveInfo', [
    'name',     # internal curve id (e.g. 'beta.g.a')
    'short',    # display name for statusbar ('beta_a')
    'label',    # y-axis/legend label ('$\beta_a$')
    'style',    # **kwargs for ax.plot
])


# basic twiss figure

class PlotSelector(QtGui.QComboBox):

    """Widget to choose the displayed graph in a TwissFigure."""

    def __init__(self, scene, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scene = scene
        self.scene.graph_changed.connect(self.update_index)
        items = [(l, n) for n, l in scene.get_graphs().items()]
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
    loaded_curves = List()

    graph_changed = Signal()

    def __init__(self, figure, session, matcher):
        super().__init__()
        self.session = session
        self.model = session.model()
        self.config = session.config.line_view
        self._graph_conf = session.config['graphs']
        self.figure = figure
        self.matcher = matcher
        # scene
        self.shown_curves = List()
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
        self.hover_marker = SceneGraph()
        self.scene_graph = SceneGraph([
            self.indicators,
            self.select_markers,
            self.constr_markers,
            self.twiss_curves,
            self.user_curves,
            self.hover_marker,
        ])
        self.scene_graph.parent = self.figure   # for invalidation
        # style
        self.x_name = 's'
        self.x_label = 's'
        self.x_unit = ui_units.get('s')
        self.element_style = self.config['element_style']
        # slots
        self.model.twiss.updated.connect(self.update, Qt.QueuedConnection)

    def attach(self, plot):
        self.plot = plot
        plot.set_scene(self)
        plot.addTool(InfoTool(plot))
        plot.addTool(MatchTool(plot, self.matcher))
        plot.addTool(CompareTool(plot))

    graph_name = None

    def set_graph(self, graph_name):
        graph_name = graph_name or self.config.default_graph
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
            ListView(partial(draw_selection_marker, ax, self),
                     self.model.selection.elements)
            for ax in axes
        ])
        self.twiss_curves.destroy()
        for ax, info in zip(axes, self.graph_info.curves):
            ax.x_name.append(self.x_name)
            ax.y_name.append(info.short)
            # assuming all curves have the same y units (as they should!!):
            ax.x_unit = self.x_unit
            ax.y_unit = ui_units.get(info.short)
        self.twiss_curves.clear([
            Curve(
                ax,
                partial(self.get_float_data, curve_info.name, 0),
                partial(self.get_float_data, curve_info.name, 1),
                with_outline(curve_info.style),
                label=ax_label(curve_info.label, ui_units.get(curve_info.name)),
                info=curve_info,
            )
            for ax, curve_info in zip(axes, self.graph_info.curves)
        ])
        self.user_curves.renew()
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
            curve.x_name = self.x_name
            curve.y_name = curve.info.short
        self.figure.set_xlabel(ax_label(self.x_label, self.x_unit))
        self.scene_graph.render()
        self.figure.autoscale()
        if self.figure.share_axes:
            ax = self.figure.axes[0]
            # TODO: move legend on the outside
            legend = ax.legend(loc='upper center', fancybox=True,
                               shadow=True, ncol=4)
            legend.draggable()

    def remove(self):
        for ax in self.axes:
            ax.cla()
        self.scene_graph.on_remove()

    def destroy(self):
        self.model.twiss.updated.disconnect(self.update)
        self.scene_graph.destroy()

    def format_coord(self, ax, x, y):
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0:.6f}{1}".format
        parts = [coord_fmt(x, get_raw_label(ax.x_unit)),
                 coord_fmt(y, get_raw_label(ax.y_unit))]
        elem = self.get_element_by_mouse_position(ax, x)
        if elem:
            name = strip_suffix(elem.node_name, '[0]')
            parts.insert(0, name.upper())
        return ', '.join(parts)

    def get_element_by_mouse_position(self, axes, pos):
        """Find an element close to the mouse cursor."""
        model = self.model
        elems = model.elements
        elem = model.get_element_by_position(pos)
        if elem is None:
            return None
        # Fuzzy select nearby elements, if they are <= 3px:
        at, L = elem.position, elem.length
        index = elem.index
        x0_px = axes.transData.transform_point((0, 0))[0]
        x2pix = lambda x: axes.transData.transform_point((x, 0))[0]-x0_px
        len_px = x2pix(L)
        if len_px > 5 or elem.base_name == 'drift':
            # max 2px cursor distance:
            edge_px = max(1, min(2, round(0.2*len_px)))
            if index > 0 \
                    and x2pix(pos-at) < edge_px \
                    and x2pix(elems[index-1].length) <= 3:
                return elems[index-1]
            if index < len(elems) \
                    and x2pix(at+L-pos) < edge_px \
                    and x2pix(elems[index+1].length) <= 3:
                return elems[index+1]
        return elem

    def update(self):
        """Update existing plot after TWISS recomputation."""
        self.update_graph_data()
        self.scene_graph.update()

    def update_graph_data(self):
        self.graph_info, graph_data = \
            self.get_graph_data(self.graph_name, self.xlim,
                                self.config['curve_style'])
        self.graph_data = {
            name: np.vstack((to_ui('s', x),
                             to_ui(name, y))).T
            for name, (x, y) in graph_data.items()
        }
        self.graph_name = self.graph_info.name

    def get_float_data(self, name, column):
        """Get data for the given parameter from model."""
        return self.graph_data[name][:, column]

    def get_curve_by_name(self, name):
        return next((c for c in self.twiss_curves.items if c.y_name == name),
                    None)

    # curves

    def get_graph_data(self, name, xlim, styles):
        """Get the data for a particular graph."""
        # TODO: use xlim for interpolate

        conf = self._graph_conf[name]
        info = PlotInfo(
            name=name,
            title=conf['title'],
            curves=[
                CurveInfo(
                    name=name,
                    short=name,
                    label=label,
                    style=style)
                for (name, label), style in zip(conf['curves'], styles)
            ])

        twiss = self.model.twiss()
        xdata = twiss.s + self.model.start.position
        data = {
            curve.short: (xdata, twiss[curve.name])
            for curve in info.curves
        }
        return info, data

    def get_graphs(self):
        """Get a list of graph names."""
        return {name: info['title']
                for name, info in self._graph_conf.items()}

    def get_graph_columns(self):
        """Get a set of all columns used in any graph."""
        cols = {
            name
            for info in self._graph_conf.values()
            for name, _ in info['curves']
        }
        cols.add('s')
        cols.update(self.model.twiss.data._cache.keys())
        return cols

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
        return dialog


class Curve(SimpleArtist):

    """Plot a TWISS parameter curve model into a 2D figure."""

    def __init__(self, axes, get_xdata, get_ydata, style,
                 label=None, info=None):
        """Store meta data."""
        self.axes = axes
        self.get_xdata = get_xdata
        self.get_ydata = get_ydata
        self.style = style
        self.label = label
        self.lines = ()
        self.info = info

    def _get_data(self):
        xdata = self.get_xdata()
        ydata = self.get_ydata()
        if xdata is None or ydata is None:
            return (), ()
        return xdata, ydata

    def draw(self):
        """Make one subplot."""
        xdata, ydata = self._get_data()
        self.lines = self.axes.plot(
            xdata, ydata, label=self.label, **self.style)
        self.line, = self.lines

    def update(self):
        """Update the y values for one subplot."""
        xdata, ydata = self._get_data()
        self.line.set_xdata(self.get_xdata())
        self.line.set_ydata(self.get_ydata())
        self.invalidate()


class ListView(SceneGraph):

    def __init__(self, fn, model):
        super().__init__()
        self.fn = fn
        self.model = model
        self.renew()
        model.insert_notify.connect(self._add)
        model.delete_notify.connect(self._rm)
        model.modify_notify.connect(self._chg)

    def renew(self):
        self.items.clear()
        for idx, item in enumerate(self.model):
            self._add(idx, item)

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

    def create(self, axes, scene, style):
        self.scene = scene
        self.axes = axes
        self.style = style
        self.clear()
        self.update()

    def update(self):
        # TODO: update indicators rather than recreate all of them anew:
        scene, style = self.scene, self.style
        self.clear([
            SceneGraph([
                ElementIndicator(ax, scene, style, elem)
                for elem in self.scene.model.elements
                if elem.base_name.lower() in style
            ])
            for ax in self.axes
        ])

    def remove(self):
        super().remove()


class ElementIndicator(SimpleArtist):

    def __init__(self, axes, scene, style, elem, default=None, effects=None):
        super().__init__(self._draw)
        self.axes = axes
        self.scene = scene
        self.style = style
        self.elem = elem
        self.default = default
        self.effects = effects or (lambda x: x)

    def draw_patch(self, position, length, style):
        at = to_ui('s', position)
        if length != 0:
            patch_w = to_ui('l', length)
            return self.axes.axvspan(at, at + patch_w, **style)
        else:
            return self.axes.axvline(at, **style)

    def _draw(self):
        """Return the element type name used for properties like coloring."""
        elem = self.elem
        axes_dirs = {n[-1] for n in self.axes.y_name} & set("xy")
        type_name = elem.base_name.lower()
        # sigmoid flavor with convenient output domain [-1,+1]:
        sigmoid = math.tanh
        style = self.style.get(type_name, self.default)
        if style is None:
            return []

        style = dict(style, zorder=0)
        styles = [(style, elem.position, elem.length)]

        if type_name == 'quadrupole':
            invert = self.axes.y_name[0].endswith('y')
            k1 = float(elem.k1) * 100                   # scale = 0.1/m²
            scale = sigmoid(k1) * (1-2*invert)
            style['color'] = ((1+scale)/2, (1-abs(scale))/2, (1-scale)/2)
        elif type_name == 'sbend':
            angle = float(elem.angle) * 180/math.pi     # scale = 1 degree
            ydis = sigmoid(angle) * (-0.15)
            style['ymin'] += ydis
            style['ymax'] += ydis
            # MAD-X uses the condition k0=0 to check whether the attribute
            # should be used (against my recommendations, and even though that
            # means you can never have a kick that exactlycounteracts the
            # bending angle):
            if elem.k0 != 0:
                style = dict(self.style.get('hkicker'),
                             ymin=style['ymin'], ymax=style['ymax'])
                styles.append((style, elem.position+elem.length/2, 0))
                type_name = 'hkicker'

        if type_name in ('hkicker', 'vkicker'):
            axis = "xy"[type_name.startswith('v')]
            kick = float(elem.kick) * 10000         # scale = 0.1 mrad
            ydis = sigmoid(kick) * 0.1
            style['ymin'] += ydis
            style['ymax'] += ydis
            if axis not in axes_dirs:
                style['alpha'] = 0.2

        return [
            self.draw_patch(position, length, self.effects(style))
            for style, position, length in styles
        ]


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


# Toolbar item for matching


class MatchTool(CaptureTool):

    """
    This toolbar item performs (when checked) simple interactive matching
    via mouse clicks into the plot window.
    """

    # TODO: define matching via config file and fix implementation

    mode = 'MATCH'
    short = 'match constraints'
    text = 'Match for desired target value'

    @cachedproperty
    def icon(self):
        return load_icon_resource('madgui.data', 'target.xpm')

    def __init__(self, plot, matcher):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.plot = plot
        self.model = plot.scene.model
        self.matcher = matcher
        self.matcher.finished.connect(partial(self.setChecked, False))

    def activate(self):
        """Start matching mode."""
        self.matcher.start()
        self.plot.startCapture(self.mode, self.short)
        self.plot.buttonPress.connect(self.onClick)
        self.plot.scene.session.window().viewMatchDialog.create()

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
        if event.button == 1:
            return self.on_left_click(event, curves, name)
        if event.button == 2:
            return self.on_middle_click(event, curves, name)

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
        from madgui.model.match import Constraint
        elem, pos = self.model.get_best_match_pos(event.x)
        constraints = [Constraint(elem, pos, name, event.y)]

        if self.matcher.mirror_mode:
            # add another constraint to hold the orthogonal axis constant
            # TODO: should do this only once for each yname!
            constraints.extend([
                Constraint(elem, pos, c.y_name,
                           self.model.get_twiss(elem.node_name, c.y_name, pos))
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
                   if c.elem.index == elem.index and c.axis == axis]
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
        to_ui(curve.x_name, pos),
        to_ui(curve.y_name, val),
        **style) or ()


# Toolbar item for info boxes

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
        self.plot.mouseMotion.connect(self.onMotion)
        self.plot.keyPress.connect(self.onKey)
        self.plot.canvas.setFocus()

    def deactivate(self):
        """Stop select mode."""
        self.plot.buttonPress.disconnect(self.onClick)
        self.plot.mouseMotion.disconnect(self.onMotion)
        self.plot.keyPress.disconnect(self.onKey)
        self.plot.endCapture(self.mode)
        self.plot.scene.hover_marker.clear()

    def onClick(self, event):
        """Display a popup window with info about the selected element."""

        if event.elem is None:
            return
        el_id = event.elem.index

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

    def onMotion(self, event):
        scene = self.plot.scene
        el_idx = event.elem.index
        scene.hover_marker.clear([
            draw_selection_marker(ax, scene, el_idx, _hover_effects, '#ffffff')
            for ax in scene.axes
        ])

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
        old_index = self.model.elements.index(old_el_id)
        new_index = old_index + move_step
        new_el_id = self.model.elements[new_index % len(elements)].index
        selected[top] = new_el_id


def draw_selection_marker(axes, scene, el_idx, _effects=None,
                          drift_color='#eeeeee'):
    """In-figure markers for active/selected elements."""
    style = scene.config['element_style']
    elem = scene.model.elements[el_idx]
    default = dict(ymin=0, ymax=1, color=drift_color)
    return ElementIndicator(
        axes, scene, style, elem, default, _effects or _selection_effects)


def _selection_effects(style):
    r, g, b = mpl_colors.colorConverter.to_rgb(style['color'])
    h, s, v = mpl_colors.rgb_to_hsv((r, g, b))
    s = (s + 0) / 2
    v = (v + 1) / 2
    return dict(
        style,
        color=mpl_colors.hsv_to_rgb((h, s, v)),
        path_effects=[
            pe.withStroke(linewidth=2, foreground='#000000', alpha=1.0),
        ],
    )


def _hover_effects(style):
    r, g, b = mpl_colors.colorConverter.to_rgb(style['color'])
    h, s, v = mpl_colors.rgb_to_hsv((r, g, b))
    s = (s + 0) / 1.5
    v = (v + 0) / 1.025
    return dict(
        style,
        color=mpl_colors.hsv_to_rgb((h, s, v)),
        path_effects=[
            pe.withStroke(linewidth=1, foreground='#000000', alpha=1.0),
        ],
    )


# Compare tool

class CompareTool(ButtonTool):

    """
    Display a precomputed reference curve for comparison.

    The reference curve is NOT visible by default.
    """

    short = 'Show reference curve'
    icon = QtGui.QStyle.SP_DirLinkIcon
    text = 'Load data file for comparison.'

    def __init__(self, plot):
        super().__init__()
        self.plot = plot

    def activate(self):
        self.plot.scene._curveManager.create()


def make_user_curve(scene, idx):
    name, data, style = scene.loaded_curves[idx]
    return SceneGraph([
        Curve(
            ax,
            partial(_get_curve_data, data, x_name),
            partial(_get_curve_data, data, y_name),
            style, label=name,
        )
        for ax in scene.axes
        for x_name, y_name in zip(ax.x_name, ax.y_name)
    ])


def _get_curve_data(data, name):
    try:
        return to_ui(name, data[name])
    except KeyError:
        logging.debug("Missing curve data {!r}, we only know: {}"
                      .format(name, ','.join(data)))


def ax_label(label, unit):
    if unit in (1, None):
        return label
    return "{} [{}]".format(label, get_raw_label(unit))


def with_outline(style, linewidth=6, foreground='w', alpha=0.7):
    return dict(style, path_effects=[
        pe.withStroke(linewidth=linewidth, foreground=foreground, alpha=alpha),
    ])
