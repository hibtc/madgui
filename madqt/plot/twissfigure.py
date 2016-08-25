# encoding: utf-8
"""
Utilities to create a plot of some TWISS parameter along the accelerator
s-axis.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from functools import partial

from madqt.qt import QtGui, Qt

from madqt.util.qt import waitCursor, notifyCloseEvent, notifyEvent
from madqt.core.unit import units, strip_unit, get_unit_label, get_raw_label
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

    def __init__(self, backend, segment, basename, config):

        # create figure
        self.backend = backend
        self.segment = segment
        self.basename = basename
        self.config = config

        self.figure = figure = backend.FigurePair()

        self.title = config['title'][basename]
        self.sname = sname = 's'
        self.names = backend.Pair(basename+'x', basename+'y')

        # plot style
        self.label = config['label']
        unit_names = config['unit']
        all_axes_names = (self.sname,) + self.names
        self.unit = {col: getattr(units, unit_names[col])
                     for col in all_axes_names}

        axes = self.figure.axes

        # Store names
        axes.x.twiss_name = self.names.x
        axes.x.twiss_conj = self.names.y
        axes.y.twiss_name = self.names.y
        axes.y.twiss_conj = self.names.x

        # Tune the builtin coord status message on the toolbar:
        axes.x.format_coord = partial(self.format_coord, self.names.x)
        axes.y.format_coord = partial(self.format_coord, self.names.y)

        # create scene
        elements_style = config['element_style']
        self.scene_graph = SceneGraph([])
        self.add_twiss_curve(self.basename)
        self.indicators = SceneGraph([
            ElementIndicators(axes.x, self, elements_style),
            ElementIndicators(axes.y, self, elements_style),
        ])

        # subscribe for updates
        self.segment.updated.connect(self.update)

    def attach(self, plot, canvas, toolbar):
        plot.addTool(InfoTool(plot))
        plot.addTool(MatchTool(plot))

    @property
    def backend_figure(self):
        return self.figure.backend_figure

    def format_coord(self, name, x, y):
        unit = self.unit
        elem = self.segment.element_by_position(x * unit['s'])
        # TODO: in some cases, it might be necessary to adjust the
        # precision to the displayed xlim/ylim.
        coord_fmt = "{0}={1:.6f}{2}".format
        parts = [coord_fmt('s', x, get_raw_label(unit['s'])),
                 coord_fmt(name, y, get_raw_label(unit[name]))]
        if elem and 'name' in elem:
            parts.insert(0, 'elem={0}'.format(elem['name']))
        return ', '.join(parts)

    def get_label(self, name):
        return self.label[name] + ' ' + get_unit_label(self.unit[name])

    def plot(self):
        """Replot from clean state."""
        fig = self.figure
        fig.clear()
        fig.axes.x.set_ylabel(self.get_label(self.names.x))
        fig.axes.y.set_ylabel(self.get_label(self.names.y))
        fig.set_slabel(self.get_label(self.sname))
        self.scene_graph.plot()
        fig.draw()

    def update(self):
        """Update existing plot after TWISS recomputation."""
        self.scene_graph.update()
        self.figure.draw()

    def remove(self):
        self.scene_graph.remove()
        self.segment.updated.disconnect(self.update)

    def get_ax_by_name(self, name):
        return self.figure.axes[self.names.index(name)]

    def get_axes_name(self, axes):
        return self.names[self.figure.axes.index(axes)]

    def get_conjugate(self, name):
        return self.names[1-self.names.index(name)]

    def add_twiss_curve(self, basename, sname='s'):
        """
        Add an X/Y pair of lines of TWISS parameters into the figure.

        :param str basename: stem of the parameter name, e.g. 'bet'
        :param str sname: data name of the shared s-axis
        """
        xname = basename + 'x'
        yname = basename + 'y'
        style = self.config['curve_style']
        axes = self.figure.axes
        get_sdata = partial(self.get_float_data, sname)
        get_xdata = partial(self.get_float_data, xname)
        get_ydata = partial(self.get_float_data, yname)
        self.scene_graph.items.extend([
            self.backend.Curve(axes.x, get_sdata, get_xdata, style['x']),
            self.backend.Curve(axes.y, get_sdata, get_ydata, style['y']),
        ])

    def get_float_data(self, name):
        """Get data for the given parameter from segment."""
        return strip_unit(self.segment.tw[name], self.unit[name])

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

    def __init__(self, axes, figure, style):
        self.axes = axes
        self.figure = figure
        self.style = style
        self.lines = []

    @property
    def s_unit(self):
        return self.figure.unit[self.figure.sname]

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
            patch_x = strip_unit(elem['at'], s_unit)
            if strip_unit(elem['l']) != 0:
                patch_w = strip_unit(elem['l'], s_unit)
                line = axes.axvspan(patch_x, patch_x + patch_w, **elem_type)
            else:
                line = axes.vlines(patch_x, **elem_type)
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

    active = False

    def setActive(self, active):
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
        action = QtGui.QAction(icon, self.text, self.plot)
        action.setCheckable(True)
        action.toggled.connect(self.setActive)
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
        self.addConstraint(elem, name, event.y)

        # add another constraint to hold the orthogonal axis constant
        orth_env = self.segment.get_twiss(elem, conj)
        self.addConstraint(elem, conj, orth_env)
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
            (elem,) + getattr(transform, axis)(value)
            for elem, axis, value in self.constraints]

        # The following uses a greedy algorithm to select all elements that
        # can be used for varying. This means that for advanced matching it
        # will most probably not work.
        # Copy all needed variable lists (for later modification):
        axes = {axis for elem, axis, envelope in constraints}
        allvars = {axis: self._allvars(axis)[:] for axis in axes}
        vary = []
        for elem, axis, envelope in constraints:
            at = elem['at']
            allowed = [v for v in allvars[axis] if v[0]['at'] < at]
            if not allowed:
                # No variable in range found! Ok.
                continue
            v = max(allowed, key=lambda v: v[0]['at'])
            expr = _get_any_elem_param(v[0], v[1])
            if expr is None:
                allvars[axis].remove(v)
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
        segment.twiss()

    def findConstraint(self, elem, axis):
        """Find and return the constraint for the specified element."""
        return [c for c in self.constraints if c[0] == elem and c[1] == axis]

    def addConstraint(self, elem, axis, envelope):
        """Add constraint and perform matching."""
        self.removeConstraint(elem, axis)
        self.constraints.append((elem, axis, envelope))

    def removeConstraint(self, elem, axis):
        """Remove the constraint for elem."""
        self.constraints[:] = [
            c for c in self.constraints
            if c[0]['name'] != elem['name'] or c[1] != axis]

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
        self.figure.figure.draw()

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
        self.lines.extend(ax.plot(
            strip_unit(elem['at'] + elem['l']/2, figure.unit[figure.sname]),
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
        self._info_boxes = []

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
        if self._info_boxes and not shift and not control:
            box = self.activeBox()
            box.widget().el_name = elem_name
            box.setWindowTitle(elem_name)
            return

        dock, info = self.create_info_box(elem_name)
        notifyCloseEvent(dock, lambda: self._info_boxes.remove(dock))
        notifyEvent(info, 'focusInEvent', lambda event: self.setActiveBox(dock))

        frame = self.plot.window()
        frame.addDockWidget(Qt.RightDockWidgetArea, dock)
        if self._info_boxes and shift:
            frame.tabifyDockWidget(self.activeBox(), dock)
            dock.show()
            dock.raise_()

        self._info_boxes.append(dock)

        # Set focus to parent window, so left/right cursor buttons can be
        # used immediately.
        self.plot.canvas.setFocus()

    def activeBox(self):
        return self._info_boxes[-1]

    def setActiveBox(self, box):
        self._info_boxes.remove(box)
        self._info_boxes.append(box)

    def create_info_box(self, elem_name):
        from madqt.widget.elementinfo import ElementInfoBox
        info = ElementInfoBox(self.segment, elem_name)
        dock = QtGui.QDockWidget()
        dock.setWidget(info)
        dock.setWindowTitle(elem_name)
        return dock, info

    def onKey(self, event):
        if not self._info_boxes:
            return
        if 'left' in event.key:
            move_step = -1
        elif 'right' in event.key:
            move_step = 1
        else:
            return
        cur_box = self.activeBox().widget()
        old_index = self.segment.get_element_index(cur_box.el_name)
        new_index = old_index + move_step
        elements = self.segment.elements
        new_elem = elements[new_index % len(elements)]
        cur_box.el_name = new_elem['name']
