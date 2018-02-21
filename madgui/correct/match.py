"""
Implementation of the matching system.
"""

from collections import namedtuple

from madgui.core.base import Object, Signal
from madgui.util.collections import List


Constraint = namedtuple('Constraint', ['elem', 'pos', 'axis', 'value'])
Variable = namedtuple('Variable', ['knob', 'pos', 'expr', 'value', 'design'])


def variable_from_knob(matcher, knob):
    elem = knob.elem
    pos = elem and elem.At + elem.L
    value = knob.read()
    design = matcher.design_values.setdefault(knob.param, value)
    return Variable(knob, pos, knob.param, value, design)


def variable_update(matcher, variable):
    value = variable.knob.read()
    design = matcher.design_values[variable.expr]
    return Variable(variable.knob, variable.pos, variable.expr, value, design)


class Matcher(Object):

    """
    Responsible for managing a MATCH operation.
    """

    matched = Signal()
    finished = Signal()

    def __init__(self, model, rules):
        """Create empty matcher."""
        super().__init__()
        self.model = model
        self.rules = rules
        self.knobs = model.get_knobs()
        self.constraints = List()
        self.variables = List()
        self.variables.update_after.connect(self._on_update_variables)
        self.design_values = {}
        self.mirror_mode = model.config['matching'].get('mirror', True)

    def match(self):
        """Match the :ivar:`variables` to satisfy :ivar:`constraints`."""
        # transform constraints (envx => betx, etc)
        transform = MatchTransform(self.model)
        constraints = [
            Constraint(c.elem, c.pos, *getattr(transform, c.axis)(c.value))
            for c in self.constraints]
        variables = [v.expr for v in self.variables]
        self.model.match(variables, constraints)
        self.variables[:] = [variable_update(self, v) for v in self.variables]

    def apply(self):
        for v in self.variables:
            self.design_values[v.expr] = v.value
        self.variables[:] = [variable_update(self, v) for v in self.variables]

    def accept(self):
        self.apply()
        self.finished.emit()

    def revert(self):
        self.variables.clear()
        self.constraints.clear()

    def reject(self):
        self.revert()
        self.finished.emit()

    def next_best_variable(self):
        return variable_from_knob(self, self.knobs[0])

    def detect_variables(self):
        """
        Fill :ivar:`variables` to the same length as :ivar:`constraints`.
        """
        # The following uses the most naive, greedy and probably stupid
        # algorithm to select all elements that can be used for varying.
        variables = self.variables
        transform = MatchTransform(self.model)
        constraints = [
            Constraint(c.elem, c.pos, *getattr(transform, c.axis)(c.value))
            for c in self.constraints]
        # Copy all needed variable lists (for later modification):
        axes = {c.axis for c in constraints}
        axes = {axis: self._allvars(axis)[:] for axis in axes}
        for c in sorted(constraints, key=lambda c: c.pos):
            # Stop as soon as we have enough variables:
            if len(variables) >= len(constraints):
                break
            try:
                # TODO: just bisect this…
                var = next(v for v in reversed(axes[c.axis])
                           if v.pos < c.pos and v not in variables)
                variables.append(var)
            except StopIteration:
                # No variable in range found! Ok?
                pass

    def _allvars(self, axis):
        """
        Find all usable constraints for the given axis.

        :returns: list of :class:`Variable`.
        """
        elem_types = self.rules.get(axis, ())
        return [
            variable_from_knob(self, knob)
            for knob in self.knobs
            if knob.elem.Type.lower() in elem_types
        ]

    # Set value back to factory defaults

    def _on_update_variables(self, indices, old_values, new_values):

        old = {v.expr: (v.knob, v.design) for v in old_values}
        new = {v.expr: (v.knob, v.value)  for v in new_values}

        # On removal, revert unapplied variables to design settings:
        # TODO: this should be handled on the level of the model, see #17.
        # TODO: set many values in one go
        for expr, (knob, value) in old.items():
            if expr not in new:
                knob.write(value)

        # Set new variable values into the model:
        for knob, value in new.values():
            knob.write(value)


class MatchTransform:

    def __init__(self, model):
        self._ex = model.ex()
        self._ey = model.ey()

    def envx(self, val):
        return 'sig11', val*val

    def envy(self, val):
        return 'sig33', val*val

    def __getattr__(self, name):
        return lambda val: (name, val)
