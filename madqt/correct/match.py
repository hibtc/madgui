"""
Implementation of the matching system.
"""

from collections import namedtuple

from madqt.core.base import Object, Signal
from madqt.util.collections import List
from madqt.util.enum import make_enum


Constraint = namedtuple('Constraint', ['elem', 'pos', 'axis', 'value'])
Variable = namedtuple('Variable', ['elem', 'pos', 'attr', 'expr', 'value', 'design'])


def defined(value):
    """Check if attribute of an element was defined."""
    try:
        return hasattr(value, '_expression') or float(value) != 0
    except (ValueError, TypeError):
        return False



def variable_from_knob(matcher, expr):
    if '->' in expr:
        name, attr = expr.split('->')
        elem = matcher.segment.elements[name]
        expr = _get_elem_attr_expr(elem, attr)
        pos = elem['at'] + elem['l']
    else:
        # TODO: lookup element by variable, if any
        elem = None
        attr = None
        pos = None
    # TODO: generalize for tao
    value = matcher.segment.get_knob(expr)
    design = matcher.design_values.setdefault(expr, value)
    return Variable(elem, pos, attr, expr, value, design)


def variable_update(matcher, variable):
    value = matcher.segment.get_knob(variable.expr)
    design = matcher.design_values[variable.expr]
    return Variable(variable.elem, variable.pos, variable.attr, variable.expr,
                    value, design)


class Matcher(Object):

    """
    Responsible for managing a MATCH operation.
    """

    matched = Signal()
    finished = Signal()

    def __init__(self, segment, rules):
        """Create empty matcher."""
        super().__init__()
        self.segment = segment
        self.rules = rules
        self.constraints = List()
        self.variables = List()
        self.variables.update_after.connect(self._on_update_variables)
        self.design_values = {}
        local_constraints = ['envx', 'envy'] + segment.workspace.config['matching']['element']
        self.elem_enum = make_enum('Elem', segment.el_names)
        self.lcon_enum = make_enum('Local', local_constraints)
        self.mirror_mode = segment.workspace.app_config['matching'].get('mirror', False)

    def match(self):
        """Match the :ivar:`variables` to satisfy :ivar:`constraints`."""
        # transform constraints (envx => betx, etc)
        transform = MatchTransform(self.segment)
        constraints = [
            Constraint(c.elem, c.pos, *getattr(transform, c.axis)(c.value))
            for c in self.constraints]
        variables = [v.expr for v in self.variables]
        self.segment.match(variables, constraints)
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
            variable_from_knob(self, elem['name']+'->'+attr)
            for elem in self.segment.elements
            for attr in self._get_match_attrs(elem, param_spec)
        ]

    def _get_match_attrs(self, elem, spec):
        attrs = spec.get(elem['type'].lower(), [])
        defd = [attr for attr in attrs if defined(elem.get(attr))]
        return defd or attrs[:1]


    # Set value back to factory defaults

    def _on_update_variables(self, indices, old_values, new_values):
        def _knob(v):
            if v.elem and v.attr:
                return v.elem['el_id'], v.attr
            return v.expr

        old = {_knob(v): v.design for v in old_values}
        new = {_knob(v): v.value  for v in new_values}

        # On removal, revert unapplied variables to design settings:
        # TODO: this should be handled on the level of the segment, see #17.
        # TODO: set many values in one go
        for knob, value in old.items():
            if knob not in new:
                self.segment.set_knob(knob, value)

        # Set new variable values into the model:
        for knob, value in new.items():
            self.segment.set_knob(knob, value)


class MatchTransform:

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
        return elem['name'] + '->' + attr
