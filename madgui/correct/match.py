"""
Implementation of the matching system.
"""

import logging
from collections import namedtuple

from madgui.core.base import Object, Signal
from madgui.util.collections import List


Constraint = namedtuple('Constraint', ['elem', 'pos', 'axis', 'value'])
Variable = namedtuple('Variable', ['knob', 'info', 'value', 'design'])


def variable_from_knob(matcher, knob, info=None):
    value = matcher.model.read_param(knob)
    design = matcher.design_values.setdefault(knob, value)
    return Variable(knob, info, value, design)


def variable_update(matcher, variable):
    return variable_from_knob(matcher, variable.knob, variable.info)


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
        self.design_values = {}
        self.mirror_mode = model.config['matching'].get('mirror', True)

    def match(self):
        """Match the :ivar:`variables` to satisfy :ivar:`constraints`."""
        # transform constraints (envx => betx, etc)
        transform = MatchTransform()
        constraints = [
            Constraint(c.elem, c.pos, *getattr(transform, c.axis)(c.value, tw))
            for c in self.constraints
            for tw in [self._get_tw_row(c.elem, c.pos)]
        ]
        blacklist = [v.lower() for v in self.model.data.get('readonly', ())]
        variables = {v.knob for v in self.variables
                     if v.knob.lower() not in blacklist}
        num_vars = len(variables)
        num_cons = len(constraints)
        logging.info("Attempting to match {} constraints via {} variables."
                     .format(num_cons, num_vars))
        if num_vars == 0 or num_vars != num_cons:
            logging.warn(
                "Aborted due to invalid number of constraints or variables.")
            return
        self.model.match(variables, constraints)
        self.variables[:] = [variable_update(self, v) for v in self.variables]

    # manage 'active' state

    started = False

    def start(self):
        if not self.started:
            self.started = True

    def stop(self):
        if self.started:
            self.clear()
            self.started = False
            self.finished.emit()

    def apply(self):
        for v in self.variables:
            self.design_values[v.knob] = v.value
        self.variables[:] = [variable_update(self, v) for v in self.variables]

    def clear(self):
        self.variables.clear()
        self.constraints.clear()
        self.design_values.clear()

    def reset(self):
        with self.model.undo_stack.macro("Reset matching"):
            self.model.update_globals(self.design_values)
        self.clear()

    def _get_tw_row(self, elem, pos):
        return self.model.get_elem_twiss(elem)

    def next_best_variable(self):
        return variable_from_knob(self, self.knobs[0])

    def detect_variables(self):
        """
        Fill :ivar:`variables` to the same length as :ivar:`constraints`.
        """
        # The following uses the most naive, greedy and probably stupid
        # algorithm to select all elements that can be used for varying.
        variables = self.variables
        transform = MatchTransform()
        constraints = [
            Constraint(c.elem, c.pos, *getattr(transform, c.axis)(c.value, tw))
            for c in self.constraints
            for tw in [self._get_tw_row(c.elem, c.pos)]
        ]
        # Copy all needed variable lists (for later modification):
        axes = {c.axis for c in constraints}
        axes = {axis: self._allvars(axis)[:] for axis in axes}
        used = set()
        for c in sorted(constraints, key=lambda c: c.pos):
            # Stop as soon as we have enough variables:
            if len(variables) >= len(constraints):
                break
            try:
                # TODO: just bisect this…
                var = next(v for v in reversed(axes[c.axis])
                           if v.info.position < c.pos and v.knob not in used)
                variables.insert(0, var)
                used.add(var.knob)
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
            variable_from_knob(self, knob, elem)
            for elem in self.model.elements
            if elem.base_name.lower() in elem_types
            for knob in self.model.get_elem_knobs(elem)
        ]


class MatchTransform:

    def alfx(self, val, tw): return 'sig12', -val*tw.ex
    def alfy(self, val, tw): return 'sig34', -val*tw.ey
    def betx(self, val, tw): return 'sig11',  val*tw.ex
    def bety(self, val, tw): return 'sig33',  val*tw.ey
    def gamx(self, val, tw): return 'sig22',  val*tw.ex
    def gamy(self, val, tw): return 'sig44',  val*tw.ey
    def envx(self, val, tw): return 'sig11',  val**2
    def envy(self, val, tw): return 'sig33',  val**2

    def __getattr__(self, name):
        return lambda val, tw: (name, val)
