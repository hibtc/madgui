__all__ = [
    'TwissWidget',
    'TwissFigure',
    'CaptureTool',
    'MatchTool',
    'InfoTool',
    'CompareTool',
    'PlotInfo',
    'CurveInfo',
    'UserData',
    'MouseEvent',
    'KeyboardEvent',
]


from functools import partial
from collections import namedtuple

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAction, QComboBox, QMenuBar, QStyle, QWidget

from madgui.util.signal import Signal

from madgui.util.qt import load_icon_resource, SingleWindow
from madgui.util.misc import memoize, strip_suffix, cachedproperty
from madgui.util.layout import VBoxLayout
from madgui.util.collections import List
from madgui.util.unit import from_ui, get_raw_label, ui_units
from madgui.plot.scene import SceneGraph, ListView, SimpleArtist
from madgui.widget.dialog import Dialog
import madgui.widget.plot as plt
import madgui.util.menu as menu

from madgui.plot.twissfigure import (
    plot_element_indicator, plot_constraint, plot_selection_marker,
    plot_twiss_curve, plot_user_curve, CONFIG, ax_label, indicator_params)


PlotInfo = namedtuple('PlotInfo', [
    'name',     # internal graph name (e.g. 'beta')
    'title',    # long display name ('Beta function')
    'curves',   # [CurveInfo]
])

CurveInfo = namedtuple('CurveInfo', [
    'table',    # table name (e.g. 'twiss')
    'xname',    # x col name (e.g. 's')
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
        self.layout_elems = List()
        self.layout_elems.emit_changed_if = lambda old, new: old != new
        self.user_tables = List()
        self.curve_info = List()
        self.hovered_elements = List()
        self.scene_graph = SceneGraph('', [
            ListView(
                'lattice_elements',
                self.layout_elems,
                plot_element_indicator,
                elem_styles=self.element_style,
                alpha=0.35),
            ListView(
                'selected_elements',
                self.session.selected_elements,
                plot_selection_marker, self.model,
                elem_styles=self.element_style),
            ListView(
                'hovered_elements',
                self.hovered_elements,
                plot_selection_marker, self.model,
                elem_styles=self.element_style, highlight=True),
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
        plot.addTool(BpmTool(plot, self))

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
        self.layout_elems[:] = self._layout_elems()
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
            ax.x_name.append(info.xname)
            ax.y_name.append(info.name)
            # assuming all curves have the same y units (as they should!!):
            ax.x_unit = ui_units.get(info.xname)
            ax.y_unit = ui_units.get(info.name)
            if not self.share_axes:
                ax.set_ylabel(ax_label(info.label, ax.y_unit))
            # replace formatter method for mouse status:
            ax.format_coord = partial(self.format_coord, ax)
        # TODO: generalize for arbitrary X data:
        self.figure.axes[-1].set_xlabel(ax_label(self.x_label, self.x_unit))
        self.scene_graph.enable(True)
        self.scene_graph.render()
        if self.share_axes:
            ax = figure.axes[0]
            legend = ax.legend(loc='lower center', fancybox=True,
                               shadow=True, ncol=4, bbox_to_anchor=(0.5, 1))
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
        self.layout_elems[:] = self._layout_elems()
        self.draw_idle()

    def on_readouts_updated(self, *_):
        node = self.scene_graph.node('monitor_readouts')
        if node.enabled():
            node.invalidate()
            self.draw_idle()

    def _layout_elems(self):
        return [
            indicator_params(elem)
            for elem in self.model.elements
            if elem.base_name in self.element_style
        ]

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
                CurveInfo(table, xname, name, label, style)
                for (table, xname, name, label, style) in conf['curves']
            ])

    def get_graphs(self):
        """Get a list of graph names."""
        return {name: info['title']
                for name, info in self.config['graphs'].items()}

    def get_graph_columns(self):
        """Get a set of all columns used in any graph."""
        cols = {
            yname
            for info in self.config['graphs'].values()
            for (table, xname, yname, label, style) in info['curves']
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
        self.draw_idle()

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
        table = getattr(self.model, info.table)
        return plot_twiss_curve(
            ax, table, info.xname, info.name, info.label, info.style)

    def plot_user_curve(self, ax, info):
        name, data, style = info
        style = self.config[style] if isinstance(style, str) else style
        return plot_user_curve(ax, data, ax.x_name, ax.y_name, name, style)


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


class BpmTool(CaptureTool):

    """Show BPM readouts."""

    short = 'BPMs'
    text = 'Show indicators for current BPM readouts in plot.'

    def __init__(self, plot, scene):
        self.plot = plot
        self.scene = scene

    @memoize
    def action(self):
        action = QAction(self.short, self.plot)
        action.setCheckable(True)
        action.toggled.connect(self.onToggle)
        return action

    def activate(self):
        self.scene.session.control.monitor_widget.create()

    def deactivate(self):
        self.scene.hide_monitor_readouts()
