# encoding: utf-8
"""
Implementation of the matching system.
"""

from __future__ import absolute_import
from __future__ import unicode_literals

from collections import namedtuple

from madqt.core.base import Object, Signal
from madqt.core.unit import strip_unit
from madqt.util.collections import List


Constraint = namedtuple('Constraint', ['elem', 'pos', 'axis', 'value'])
Variable = namedtuple('Variable', ['elem', 'pos', 'attr', 'expr', 'value', 'design'])


class Matcher(Object):

    """
    Responsible for managing a MATCH operation.
    """

    matched = Signal()
    finished = Signal()

    def __init__(self, segment, rules):
        """Create empty matcher."""
        super(Matcher, self).__init__()
        self.segment = segment
        self.rules = rules
        self.constraints = List()
        self.variables = List()
        self.variables.update_after.connect(self._on_update_variables)
        self.design_values = {}

    def match(self):
        """Match the :ivar:`variables` to satisfy :ivar:`constraints`."""
        # transform constraints (envx => betx, etc)
        transform = MatchTransform(self.segment)
        constraints = [
            Constraint(c.elem, c.pos, *getattr(transform, c.axis)(c.value))
            for c in self.constraints]
        variables = [v.expr for v in self.variables]
        self.segment.match(variables, constraints)

    def accept(self):
        for v in self.variables:
            self.design_values[v.expr] = v.elem[v.attr]
        self.finished.emit()

    def reject(self):
        self.variables.clear()
        self.constraints.clear()
        self.finished.emit()

    def detect_variables(self):
        """
        Fill :ivar:`variables` to the same length as :ivar:`constraints`.
        """
        # The following uses the most naive, greedy and probably stupid
        # algorithm to select all elements that can be used for varying.
        variables = self.variables
        transform = MatchTransform(self.segment)
        constraints = [
            Constraint(c.elem, c.pos, *getattr(transform, c.axis)(c.value))
            for c in self.constraints]
        # Copy all needed variable lists (for later modification):
        axes = {c.axis for c in constraints}
        axes = {axis: self._allvars(axis)[:] for axis in axes}
        for v in variables:
            self._rmvar(axes, v)
        for c in sorted(constraints, key=lambda c: c.pos):
            # Stop as soon as we have enough variables:
            if len(variables) >= len(constraints):
                break
            try:
                # TODO: just bisect this…
                var = next(v for v in reversed(axes[c.axis]) if v.pos < c.pos)
                variables.append(var)
                self._rmvar(axes, var)
            except StopIteration:
                # No variable in range found! Ok?
                pass

    def _rmvar(self, axes, var):
        for l in axes.values():
            try:
                l.remove(var)
            except ValueError:
                pass

    def _allvars(self, axis):
        """
        Find all usable constraints for the given axis.

        :returns: list of :class:`Variable`.
        """
        param_spec = self.rules.get(axis, {})
        return [
            Variable(elem, elem['at'], attr, expr, elem[attr],
                     self.design_values.setdefault(expr, float(elem[attr])))
            for elem in self.segment.elements
            for attr in param_spec.get(elem['type'].lower(), [])
            for expr in [_get_elem_attr_expr(elem, attr)]
            if expr is not None
        ]

    # Set value back to factory defaults

    def _on_update_variables(self, indices, old_values, new_values):
        old = {(v.elem['el_id'], v.attr): v.design for v in old_values}
        new = {(v.elem['el_id'], v.attr): v.value  for v in new_values}

        # On removal, revert unapplied variables to design settings:
        # TODO: this should be handled on the level of the segment, see #17.
        # TODO: set many values in one go
        for (elem, attr), value in old.items():
            if (elem, attr) not in new:
                self.segment.set_element_attribute(elem, attr, value)

        # Set new variable values into the model:
        for (elem, attr), value in new.items():
            self.segment.set_element_attribute(elem, attr, value)


class MatchTransform(object):

    def __init__(self, segment):
        self._ex = segment.ex()
        self._ey = segment.ey()

    def envx(self, val):
        return 'betx', val*val/self._ex

    def envy(self, val):
        return 'bety', val*val/self._ey

    def __getattr__(self, name):
        return lambda val: (name, val)


def _get_elem_attr_expr(elem, attr):
    try:
        return elem[attr]._expression
    except KeyError:
        return None
    except AttributeError:
        if strip_unit(elem[attr]) != 0.0:
            return elem['name'] + '->' + attr
    return None
