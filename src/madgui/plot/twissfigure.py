"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

__all__ = [
    'TwissWidget',
    'TwissFigure',
    'plot_curve',
    'plot_element_indicators',
    'plot_element_indicator',
    'plot_constraint',
    'plot_selection_marker',
    'plot_curves',
    'CaptureTool',
    'MatchTool',
    'InfoTool',
    'CompareTool',
    'PlotInfo',
    'CurveInfo',
    'UserData',
    'MouseEvent',
    'KeyboardEvent',
    'draw_patch',
    'ax_label',
    'indicator_params',
]

import math
import logging
from functools import partial
from collections import namedtuple

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAction, QComboBox, QMenuBar, QStyle, QWidget

from madgui.util.signal import Signal
from madgui.util.yaml import load_resource

from madgui.util.qt import load_icon_resource, SingleWindow
from madgui.util.misc import memoize, strip_suffix, cachedproperty
from madgui.util.layout import VBoxLayout
from madgui.util.collections import List
from madgui.util.unit import (
    to_ui, from_ui, get_raw_label, ui_units)
from madgui.plot.scene import (
    SceneGraph, ListView, LineBundle, plot_line, SimpleArtist)
from madgui.widget.dialog import Dialog
import madgui.widget.plot as plt
import madgui.util.menu as menu

import matplotlib.patheffects as pe
import matplotlib.colors as mpl_colors

CONFIG = load_resource(__package__, 'twissfigure.yml')
ELEM_STYLES = CONFIG['element_style']


PlotInfo = namedtuple('PlotInfo', [
    'name',     # internal graph name (e.g. 'beta')
    'title',    # long display name ('Beta function')
    'curves',   # [CurveInfo]
])

CurveInfo = namedtuple('CurveInfo', [
    'name',     # curve name (e.g. 'betx')
    'label',    # y-axis/legend label ('$\beta_x$')
    'style',    # **kwargs for ax.plot
])

UserData = namedtuple('UserData', [
    'name',
    'data',
    'style',
])

MouseEvent = namedtuple('MouseEvent', [
    'button', 'x', 'y', 'axes', 'elem', 'guiEvent'])

KeyboardEvent = namedtuple('KeyboardEvent', [
    'key', 'guiEvent'])


class TwissWidget(QWidget):

    @classmethod
    def from_session(cls, session, name):
        model = session.model()
        config = session.config

        # NOTE: using the plot_windows list as a stack with its top at 0:
        settings = (config.plot_windows and
                    config.plot_windows.pop(0) or {})

        # indicators require retrieving data for all elements which can be too
        # time consuming for large lattices:
        show_indicators = len(model.elements) < 500

        parent = session.window()
        widget = cls(
            session, model, name=name,
            show_indicators=show_indicators,
            settings=settings)
        dialog = Dialog(parent, widget)
        dialog.layout().setMenuBar(QMenuBar())
        widget.create_menu(dialog.layout().menuBar())

        size = settings.get('size')
        pos = settings.get('pos')
        if not size:
            size = (parent.size().width(), dialog.sizeHint().height())
        dialog.resize(*size)
        if pos:
            dialog.move(*pos)
        dialog.show()

        widget.update_window_title()
        session.model.changed_singleshot(dialog.close)
        return widget

    def __init__(self, session, model, name=None,
                 show_indicators=True, settings={}):

        super().__init__()

        self.session = session
        self.model = model
        self.settings = settings

        figure = plt.Figure(tight_layout=True)
        plot = plt.PlotWidget(figure)

        scene = self.scene = TwissFigure(
            figure, session, session.matcher)
        scene.show_indicators = show_indicators
        scene.set_graph(name or settings.get('graph'))
        scene.attach(plot)

        # for convenience when debugging:
        session.user_ns.__dict__.update({
            'plot': plot,
            'figure': figure,
            'canvas': plot.canvas,
            'scene': scene,
        })

        selector = self.selector = QComboBox()
        self.setLayout(VBoxLayout([selector, plot], tight=True))
        scene.graph_changed.connect(self.update_window_title)

        items = [(l, n) for n, l in scene.get_graphs().items()]
        for label, name in sorted(items):
            selector.addItem(label, name)

        selector.currentIndexChanged.connect(self.change_figure)

    def create_menu(self, menubar):
        Menu, Item = menu.Menu, menu.Item
        menu.extend(self.window(), menubar, [
            Menu('&View', [
                # TODO: dynamic checked state
                Item('&Shared plot', 'Ctrl+M',
                     'Plot all curves into the same axes.',
                     self.toggleShareAxes, checked=False),
                # TODO: dynamic checked state
                Item('Element &indicators', None,
                     'Show element indicators',
                     self.toggleIndicators, checked=self.scene.show_indicators),
                Item('Manage curves', None,
                     'Select which data sets are shown',
                     self.scene._curveManager.toggle,
                     checked=self.scene._curveManager.holds_value),
            ]),
        ])

    def toggleShareAxes(self):
        scene = self.scene
        scene.share_axes = not scene.share_axes
        scene.reset()

    def toggleIndicators(self):
        scene = self.scene
        scene.show_indicators = not scene.show_indicators

    def update_window_title(self):
        self.window().setWindowTitle("{1} ({0})".format(
            self.model.name, self.scene.graph_name))
        self.selector.setCurrentIndex(
            self.selector.findData(self.scene.graph_name))

    def change_figure(self, index):
        self.scene.set_graph(self.selector.itemData(index))


class TwissFigure:

    """A figure containing some X/Y twiss parameters."""

    xlim = None
    snapshot_num = 0

    graph_changed = Signal()

    buttonPress = Signal(MouseEvent)
    mouseMotion = Signal(MouseEvent)
    keyPress = Signal(KeyboardEvent)

    def __init__(self, figure, session, matcher):
        self.figure = figure
        self.share_axes = False
        self.session = session
        self.model = session.model()
        self.config = dict(CONFIG, **session.config.get('twissfigure', {}))
        self.element_style = self.config['element_style']
        self.monitors = []
        # scene
        self.layout_el_names = [
            elem.name for elem in self.model.elements
            if elem.base_name in self.element_style]
        self.layout_elems = List()
        self.user_tables = List()
        self.curve_info = List()
        self.hovered_elements = List()
        get_element = self.model.elements.__getitem__
        self.scene_graph = SceneGraph('', [
            ListView(
                'lattice_elements',
                self.layout_elems,
                plot_element_indicator,
                elem_styles=self.element_style),
            ListView(
                'selected_elements',
                self.session.selected_elements.map(get_element),
                plot_selection_marker, self.model,
                elem_styles=self.element_style),
            ListView(
                'hovered_elements',
                self.hovered_elements.map(get_element),
                plot_selection_marker, self.model,
                elem_styles=self.element_style,
                _effects=_hover_effects, drift_color='#ffffff'),
            ListView(
                'match_constraints',
                self.session.matcher.constraints,
                plot_constraint, self),
            ListView('twiss_curves', self.curve_info, self.plot_twiss_curve),
            ListView('user_curves', self.user_tables, self.plot_user_curve),
            SimpleArtist('monitor_readouts', self.plot_user_curve, (
                'monitor_readouts', self._get_monitor_curve_data,
                'readouts_style')),
        ], figure)
        self.scene_graph.draw_idle = self.draw_idle
        # style
        self.x_name = 's'
        self.x_label = 's'
        self.x_unit = ui_units.get('s')
        # slots
        self.model.updated.connect(self.on_model_updated)
        self.session.control.sampler.updated.connect(self.on_readouts_updated)

    def attach(self, plot):
        self.plot = plot
        plot.addTool(InfoTool(plot, self))
        plot.addTool(MatchTool(plot, self, self.session.matcher))
        plot.addTool(CompareTool(plot, self))

        canvas = plot.canvas
        canvas.mpl_connect('button_press_event', self._on_button_press)
        canvas.mpl_connect('motion_notify_event', self._on_motion_notify)
        canvas.mpl_connect('key_press_event', self._on_key_press)

    def _on_button_press(self, mpl_event):
        self._mouse_event(self.buttonPress, mpl_event)

    def _on_motion_notify(self, mpl_event):
        self._mouse_event(self.mouseMotion, mpl_event)

    def _mouse_event(self, signal, mpl_event):
        if mpl_event.inaxes is None:
            return
        axes = mpl_event.inaxes
        xpos = from_ui(axes.x_name[0], mpl_event.xdata)
        ypos = from_ui(axes.y_name[0], mpl_event.ydata)
        elem = self.get_element_by_mouse_position(axes, xpos)
        event = MouseEvent(mpl_event.button, xpos, ypos,
                           axes, elem, mpl_event.guiEvent)
        signal.emit(event)

    def _on_key_press(self, mpl_event):
        event = KeyboardEvent(mpl_event.key, mpl_event.guiEvent)
        self.keyPress.emit(event)

    graph_name = None

    def set_graph(self, graph_name):
        graph_name = graph_name or self.config['default_graph']
        if graph_name == self.graph_name:
            return
        self.graph_info = self.get_graph_info(graph_name, self.xlim)
        self.graph_name = self.graph_info.name
        self.reset()
        self.graph_changed.emit()

    def reset(self):
        """Reset figure and plot."""
        figure = self.figure
        figure.clear()
        self.scene_graph.on_clear_figure()
        self.scene_graph.enable(False)
        self.curve_info[:] = self.graph_info.curves
        self.layout_elems[:], self.layout_params = self._layout_elems()
        num_curves = len(self.curve_info)
        if num_curves == 0:
            return
        num_axes = 1 if self.share_axes else num_curves
        top_ax = figure.add_subplot(num_axes, 1, 1)
        for i in range(1, num_axes):
            figure.add_subplot(num_axes, 1, i+1, sharex=top_ax)
        for ax in figure.axes:
            ax.grid(True, axis='y')
            ax.x_name = []
            ax.y_name = []
        axes = figure.axes * (num_curves if self.share_axes else 1)
        for ax, info in zip(axes, self.curve_info):
            ax.x_name.append(self.x_name)
            ax.y_name.append(info.name)
            # assuming all curves have the same y units (as they should!!):
            ax.x_unit = self.x_unit
            ax.y_unit = ui_units.get(info.name)
            if not self.share_axes:
                ax.set_ylabel(ax_label(info.label, ax.y_unit))
            # replace formatter method for mouse status:
            ax.format_coord = partial(self.format_coord, ax)
        self.figure.axes[-1].set_xlabel(ax_label(self.x_label, self.x_unit))
        self.scene_graph.enable(True)
        self.scene_graph.render()
        if self.share_axes:
            ax = figure.axes[0]
            # TODO: move legend on the outside
            legend = ax.legend(loc='upper center', fancybox=True,
                               shadow=True, ncol=4)
            legend.set_draggable(True)
        for ax in self.figure.axes:
            # prevent matplotlib from using an offset and displaying
            # near-constant quantities in a weird way, see #32:
            ax.axhline(alpha=0)
            ax.set_autoscale_on(False)

    def draw_idle(self):
        """Draw the figure on its canvas."""
        canvas = self.figure.canvas
        if canvas:
            canvas.draw_idle()

    def destroy(self):
        self.model.updated.disconnect(self.on_model_updated)
        self.session.control.sampler.updated.disconnect(self.on_readouts_updated)
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

    def on_model_updated(self):
        """Update existing plot after TWISS recomputation."""
        self.scene_graph.node('twiss_curves').invalidate()
        # Redraw changed elements:
        new_elems, new_params = self._layout_elems()
        for i, (old, new) in enumerate(zip(self.layout_params, new_params)):
            if old != new:
                self.layout_elems[i] = new_elems[i]
        self.layout_params = new_params
        self.draw_idle()

    def on_readouts_updated(self, *_):
        node = self.scene_graph.node('monitor_readouts')
        if node.enabled():
            node.invalidate()
            self.draw_idle()

    def _layout_elems(self):
        elems = self.model.elements
        layout_elems = [elems[elem] for elem in self.layout_el_names]
        layout_params = [indicator_params(elem) for elem in layout_elems]
        return layout_elems, layout_params

    def get_curve_by_name(self, name):
        return next((c for c in self.curve_info if c.name == name), None)

    # curves

    def get_graph_info(self, name, xlim):
        """Get the data for a particular graph."""
        # TODO: use xlim for interpolate
        conf = self.config['graphs'][name]
        return PlotInfo(
            name=name,
            title=conf['title'],
            curves=[
                CurveInfo(name, label, style)
                for (name, label, style) in conf['curves']
            ])

    def get_graphs(self):
        """Get a list of graph names."""
        return {name: info['title']
                for name, info in self.config['graphs'].items()}

    def get_graph_columns(self):
        """Get a set of all columns used in any graph."""
        cols = {
            name
            for info in self.config['graphs'].values()
            for (name, label, style) in info['curves']
        }
        cols.add('s')
        cols.update(self.model.twiss()._cache.keys())
        return cols

    @property
    def show_indicators(self):
        return self.scene_graph.node('lattice_elements').enabled()

    @show_indicators.setter
    def show_indicators(self, show):
        if self.show_indicators != show:
            self.scene_graph.node('lattice_elements').enable(show)

    @SingleWindow.factory
    def _curveManager(self):
        from madgui.widget.curvemanager import CurveManager
        return Dialog(self.plot.window(), CurveManager(self))

    def show_monitor_readouts(self, monitors):
        self.monitors = [m.lower() for m in monitors]
        self.scene_graph.node('monitor_readouts').enable(True)
        self.scene_graph.node('monitor_readouts').invalidate()

    def hide_monitor_readouts(self):
        self.scene_graph.node('monitor_readouts').enable(False)

    def _get_monitor_curve_data(self):
        elements = self.model.elements
        offsets = self.session.config['online_control']['offsets']
        monitor_data = [
            {'s': elements[r.name].position,
             'x': r.posx + dx,
             'y': r.posy + dy,
             'envx': r.envx,
             'envy': r.envy,
             }
            for r in self.session.control.sampler.readouts_list
            for dx, dy in [offsets.get(r.name.lower(), (0, 0))]
            if r.name.lower() in self.monitors
            and r.posx is not None
            and r.posy is not None
        ]
        return {
            name: np.array([d[name] for d in monitor_data])
            for name in ['s', 'envx', 'envy', 'x', 'y']
        }

    def add_curve(self, name, data, style):
        item = UserData(name, data, style)
        for i, c in enumerate(self.user_tables):
            if c.name == name:
                self.user_tables[i] = item
                break
        else:
            self.user_tables.append(item)

    def del_curve(self, name):
        for i, c in enumerate(self.user_tables):
            if c.name == name:
                del self.user_tables[i]
                break

    def plot_twiss_curve(self, ax, info):
        style = with_outline(info.style)
        label = ax_label(info.label, ui_units.get(info.name))
        return plot_curves(ax, self.model.twiss, style, label, [info.name])

    def plot_user_curve(self, ax, info):
        name, data, style = info
        style = self.config[style] if isinstance(style, str) else style
        return plot_curves(ax, data, style, name, ax.y_name)


def plot_curve(axes, data, x_name, y_name, style, label=None):
    """Plot a TWISS parameter curve model into a 2D figure."""
    def get_xydata():
        table = data() if callable(data) else data
        xdata = _get_curve_data(table, x_name)
        ydata = _get_curve_data(table, y_name)
        if xdata is None or ydata is None:
            return (), ()
        return xdata, ydata
    return plot_line(axes, get_xydata, label=label, **style)


def plot_element_indicators(ax, elements, elem_styles=ELEM_STYLES,
                            default_style=None, effects=None):
    """Plot element indicators, i.e. create lattice layout plot."""
    return LineBundle([
        plot_element_indicator(ax, elem, elem_styles, default_style, effects)
        for elem in elements
    ])


def draw_patch(ax, position, length, style):
    at = to_ui('s', position)
    if length != 0:
        patch_w = to_ui('l', length)
        return ax.axvspan(at, at + patch_w, **style)
    else:
        return ax.axvline(at, **style)


def plot_element_indicator(ax, elem, elem_styles=ELEM_STYLES,
                           default_style=None, effects=None):
    """Return the element type name used for properties like coloring."""
    type_name = elem.base_name.lower()
    style = elem_styles.get(type_name, default_style)
    if style is None:
        return LineBundle()

    axes_dirs = {n[-1] for n in ax.y_name} & set("xy")
    # sigmoid flavor with convenient output domain [-1,+1]:
    sigmoid = math.tanh

    style = dict(style, zorder=0)
    styles = [(style, elem.position, elem.length)]

    if type_name == 'quadrupole':
        invert = ax.y_name[0].endswith('y')
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
            style = dict(elem_styles.get('hkicker'),
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

    effects = effects or (lambda x: x)
    return LineBundle([
        draw_patch(ax, position, length, effects(style))
        for style, position, length in styles
    ])


def indicator_params(elem):
    base_name = elem.base_name
    return (elem.position, elem.length,
            (elem.angle, elem.k0) if base_name == 'sbend' else
            (elem.k1) if base_name == 'quadrupole' else
            (elem.kick) if base_name.endswith('kicker') else
            None)


class CaptureTool:

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
        if isinstance(icon, QStyle.StandardPixmap):
            icon = self.plot.style().standardIcon(icon)
        action = QAction(icon, self.text, self.plot)
        action.setCheckable(True)
        action.toggled.connect(self.onToggle)
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

    def __init__(self, plot, scene, matcher):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.plot = plot
        self.scene = scene
        self.model = scene.model
        self.matcher = matcher
        self.matcher.finished.connect(partial(self.setChecked, False))

    def activate(self):
        """Start matching mode."""
        self.matcher.start()
        self.plot.startCapture(self.mode, self.short)
        self.scene.buttonPress.connect(self.onClick)
        self.scene.session.window().viewMatchDialog.create()

    def deactivate(self):
        """Stop matching mode."""
        self.scene.buttonPress.disconnect(self.onClick)
        self.plot.endCapture(self.mode)

    def onClick(self, event):
        """Handle clicks into the figure in matching mode."""
        # If the selected plot has two curves, select the primary/alternative
        # (i.e. first/second) curve according to whether the user pressed ALT:
        index = int(bool(self.scene.share_axes and
                         event.guiEvent.modifiers() & Qt.AltModifier and
                         len(self.scene.curve_info) > 1))
        name = event.axes.y_name[index]
        if event.button == 1:
            return self.add_constraint(event, name)
        if event.button == 2:
            return self.remove_constraint(event, name)

    def remove_constraint(self, event, name):
        """Remove constraint nearest to cursor location."""
        constraints = [c for c in self.matcher.constraints
                       if c.axis == name]
        if constraints:
            cons = min(constraints, key=lambda c: abs(c.pos-event.x))
            elem = cons.elem
            for c in self.scene.curve_info:
                self.removeConstraint(elem, c.name)

    def add_constraint(self, event, name):
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
                Constraint(elem, pos, c.name,
                           self.model.get_twiss(elem.node_name, c.name, pos))
                for c in self.scene.curve_info
                if c.name != name
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


def plot_constraint(ax, scene, constraint):
    """Draw one constraint representation in the graph."""
    elem, pos, axis, val = constraint
    style = scene.config['constraint_style']
    return LineBundle(ax.plot(
        to_ui('s', pos),
        to_ui(axis, val),
        **style) if axis in ax.y_name else ())


# Toolbar item for info boxes

class InfoTool(CaptureTool):

    """
    Opens info boxes when clicking on an element.
    """

    mode = 'INFO'
    short = 'element info'
    icon = QStyle.SP_MessageBoxInformation
    text = 'Show element info boxes'

    def __init__(self, plot, scene):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.plot = plot
        self.scene = scene
        self.model = scene.model
        self.selection = scene.session.selected_elements
        self._hovered = None

    def activate(self):
        """Start select mode."""
        self.plot.startCapture(self.mode, self.short)
        self.scene.buttonPress.connect(self.onClick)
        self.scene.mouseMotion.connect(self.onMotion)
        self.scene.keyPress.connect(self.onKey)
        self.plot.canvas.setFocus()

    def deactivate(self):
        """Stop select mode."""
        self.scene.buttonPress.disconnect(self.onClick)
        self.scene.mouseMotion.disconnect(self.onMotion)
        self.scene.keyPress.disconnect(self.onKey)
        self.plot.endCapture(self.mode)
        self.scene.hovered_elements.clear()

    def onClick(self, event):
        """Display a popup window with info about the selected element."""

        if event.elem is None:
            return
        el_id = event.elem.index

        shift = bool(event.guiEvent.modifiers() & Qt.ShiftModifier)
        control = bool(event.guiEvent.modifiers() & Qt.ControlModifier)

        append = shift or control
        self.selection.add(el_id, replace=not append)

        # Set focus to parent window, so left/right cursor buttons can be
        # used immediately.
        self.plot.canvas.setFocus()

    def onMotion(self, event):
        el_idx = event.elem.index
        if self._hovered != el_idx:
            self._hovered = el_idx
            self.scene.hovered_elements[:] = [el_idx]

    def onKey(self, event):
        if 'left' in event.key:
            self.advance_selection(-1)
        elif 'right' in event.key:
            self.advance_selection(+1)

    def advance_selection(self, move_step):
        selected = self.selection
        if selected:
            old_el_id = selected.cursor_item
            new_el_id = (old_el_id + move_step) % len(self.model.elements)
            selected.add(new_el_id, replace=True)


def plot_selection_marker(ax, model, el_idx, elem_styles=ELEM_STYLES,
                          _effects=None, drift_color='#eeeeee'):
    """In-figure markers for active/selected elements."""
    elem = model.elements[el_idx]
    default = dict(ymin=0, ymax=1, color=drift_color)
    return plot_element_indicator(
        ax, elem, elem_styles, default, _effects or _selection_effects)


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

class CompareTool:

    """
    Display a precomputed reference curve for comparison.

    The reference curve is NOT visible by default.
    """

    short = 'Show reference curve'
    icon = QStyle.SP_DirLinkIcon
    text = 'Load data file for comparison.'

    def __init__(self, plot, scene):
        self.plot = plot
        self.scene = scene

    @memoize
    def action(self):
        icon = self.icon
        if isinstance(icon, QStyle.StandardPixmap):
            icon = self.plot.style().standardIcon(icon)
        action = QAction(icon, self.text, self.plot)
        action.triggered.connect(self.activate)
        return action

    def activate(self):
        self.scene._curveManager.create()


def plot_curves(ax, data, style, label, y_names):
    return LineBundle([
        plot_curve(ax, data, x_name, y_name, style, label=label)
        for x_name, y_name in zip(ax.x_name, ax.y_name)
        if y_name in y_names
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
