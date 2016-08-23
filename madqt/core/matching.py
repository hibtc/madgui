# encoding: utf-8
"""
This module provides simple interactive matching via mouse clicks into the
plot window.
"""

# force new style imports
from __future__ import absolute_import
from __future__ import unicode_literals

from madqt.qt import QtCore, QtGui, Qt

from madqt.core.base import Object, Signal
from madqt.util.qt import waitCursor
from madgui.util.unit import strip_unit
from madqt.resource.package import PackageResource


class MatchTool(object):

    """
    Controller that performs matching when clicking on an element.
    """

    def __init__(self, plot_widget, rules):
        """Add toolbar tool to panel and subscribe to capture events."""
        self.is_active = False
        self.plot_widget = plot_widget
        self.segment = plot_widget.figure.segment
        self.add_toolbar_action()
        self.rules = rules
        self.constraints = {}
        plot_widget._match_tool = self

    @property
    def elements(self):
        return self.segment.elements

    def add_toolbar_action(self):
        with PackageResource('madqt.data', 'target.xpm').filename() as xpm:
            icon = QtGui.QPixmap(xpm, 'XPM')
        action = self.action = self.plot_widget.addAction(
            QtGui.QIcon(icon),
            'Match by specifying constraints for envelope x(s), y(s)')
        action.setCheckable(True)
        action.triggered.connect(self.onToolClicked)

    def onToolClicked(self, checked):
        """Invoked when user clicks Match-Button"""
        if checked:
            self.startMatch()
        else:
            self.stopMatch()

    def startMatch(self):
        """Start matching mode."""
        if not self.is_active:
            plot = self.plot_widget
            plot.buttonPress.connect(self.onClick)
            plot.captureMouse('MATCH', 'Match constraints', self.stopMatch)
            # TODO: insert markers
            self.is_active = True
        self.action.setChecked(True)

    def stopMatch(self):
        """Stop matching mode."""
        if self.is_active:
            plot = self.plot_widget
            plot.buttonPress.disconnect(self.onClick)
            self.clearConstraints()
            self.is_active = False
        self.action.setChecked(False)

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
            self.removeConstraint(name, elem)
            self.removeConstraint(conj, elem)
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
        self.addConstraint(name, elem, event.y)

        # add another constraint to hold the orthogonal axis constant
        orth_env = self.segment.get_twiss(elem, conj)
        self.addConstraint(conj, elem, orth_env)

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
        constraints = {}
        for axis, constr in self.constraints.items():
            for elem, value in constr:
                trans_name, trans_value = getattr(transform, axis)(value)
                this_constr = constraints.setdefault(trans_name, [])
                this_constr.append((elem, trans_value))

        # The following uses a greedy algorithm to select all elements that
        # can be used for varying. This means that for advanced matching it
        # will most probably not work.
        # Copy all needed variable lists (for later modification):
        allvars = {axis: self._allvars(axis)[:]
                   for axis in constraints}
        vary = []
        for axis, constr in constraints.items():
            for elem, envelope in constr:
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
        constraints = [
            {'range': elem['name'],
             name: universe.utool.strip_unit(name, val)}
            for name, constr in constraints.items()
            for elem, val in constr
        ]

        twiss_args = universe.utool.dict_strip_unit(segment.twiss_args)
        universe.madx.match(sequence=segment.sequence.name,
                            vary=vary,
                            constraints=constraints,
                            twiss_init=twiss_args)
        segment.twiss()

    def _gconstr(self, axis):
        return self.constraints.get(axis, [])

    def _sconstr(self, axis):
        return self.constraints.setdefault(axis, [])

    def findConstraint(self, axis, elem):
        """Find and return the constraint for the specified element."""
        return [c for c in self._gconstr(axis) if c[0] == elem]

    def addConstraint(self, axis, elem, envelope):
        """Add constraint and perform matching."""
        self.removeConstraint(axis, elem)
        self._sconstr(axis).append( (elem, envelope) )

    def removeConstraint(self, axis, elem):
        """Remove the constraint for elem."""
        try:
            orig = self.constraints[axis]
        except KeyError:
            return
        filtered = [c for c in orig if c[0]['name'] != elem['name']]
        if filtered:
            self.constraints[axis] = filtered
        else:
            del self.constraints[axis]

    def clearConstraints(self):
        """Remove all constraints."""
        self.constraints = {}


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
