"""
Implementation of the matching system.
"""

__all__ = [
    'Constraint',
    'MATCH_RULES',
    'Matcher',
    'MatchTransform',
]

import logging
from collections import namedtuple

from madgui.util.signal import Signal
from madgui.util.collections import List


Constraint = namedtuple('Constraint', ['elem', 'pos', 'axis', 'value'])


# Select which element paramters can be varied when matching a TWISS function:
# TODO: fill in more rules
MATCH_RULES = {
    'betx':     ['quadrupole'],
    'bety':     ['quadrupole'],
    'alfx':     ['quadrupole'],
    'alfy':     ['quadrupole'],
    'sig11':    ['quadrupole'],
    'sig33':    ['quadrupole'],
    'sig12':    ['quadrupole'],
    'sig22':    ['quadrupole'],
    'sig34':    ['quadrupole'],
    'sig43':    ['quadrupole'],
    'x':        ['quadrupole', 'sbend', 'kicker', 'hkicker'],
    'y':        ['quadrupole', 'sbend', 'kicker', 'vkicker'],
    'px':       ['quadrupole', 'sbend', 'kicker', 'hkicker'],
    'py':       ['quadrupole', 'sbend', 'kicker', 'vkicker'],
}


class Matcher:

    """
    Responsible for managing a MATCH operation.
    """

    matched = Signal()
    finished = Signal()

    def __init__(self, model, rules=None):
        """Create empty matcher."""
        self.model = model
        self.rules = rules = rules or MATCH_RULES
        self.knobs = model.get_knobs()
        self.constraints = List()
        self.variables = List()
        self.match_results = {}
        self.design_values = {}
        self.mirror_mode = rules.get('mirror', True)

    def match(self):
        """Match the :attr:`variables` to satisfy :attr:`constraints`."""
        # transform constraints (envx => betx, etc)
        transform = MatchTransform()
        constraints = [
            Constraint(c.elem, c.pos, *transform(c.axis, c.value, tw))
            for c in self.constraints
            for tw in [self._get_tw_row(c.elem, c.pos)]
        ]
        blacklist = [v.lower() for v in self.model.data.get('readonly', ())]
        variables = {v for v in self.variables
                     if v.lower() not in blacklist}
        num_vars = len(variables)
        num_cons = len(constraints)
        logging.info("Attempting to match {} constraints via {} variables."
                     .format(num_cons, num_vars))
        if num_vars == 0 or num_vars != num_cons:
            logging.warning(
                "Aborted due to invalid number of constraints or variables.")
            return
        match_results = self.model.match(variables, constraints, self.mirror_mode)
        self.match_results = {k.lower(): v for k, v in match_results.items()}
        self.variables.touch()

    # manage 'active' state

    started = False

    def start(self):
        if not self.started:
            self.started = True
            self.design_values = dict(self.model.globals)

    def stop(self):
        if self.started:
            self.clear()
            self.started = False
            self.finished.emit()

    def apply(self):
        self.design_values = dict(self.model.globals)
        self.variables.touch()

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
        return self.knobs[0]

    def detect_variables(self):
        """
        Fill :attr:`variables` to the same length as :attr:`constraints`.
        """
        # The following uses the most naive, greedy and probably stupid
        # algorithm to select all elements that can be used for varying.
        variables = self.variables
        transform = MatchTransform()
        constraints = [
            Constraint(c.elem, c.pos, *transform(c.axis, c.value, tw))
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
                var = next(v for elem, v in reversed(axes[c.axis])
                           if elem.position < c.pos and v not in used)
                variables.insert(0, var)
                used.add(var)
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
            (elem, knob)
            for elem in self.model.elements
            if elem.base_name.lower() in elem_types
            for knob in self.model.get_elem_knobs(elem)
        ]


class MatchTransform:

    _transform = {
        'alfx': lambda val, tw: ('sig12', -val*tw.ex),
        'alfy': lambda val, tw: ('sig34', -val*tw.ey),
        'betx': lambda val, tw: ('sig11',  val*tw.ex),
        'bety': lambda val, tw: ('sig33',  val*tw.ey),
        'gamx': lambda val, tw: ('sig22',  val*tw.ex),
        'gamy': lambda val, tw: ('sig44',  val*tw.ey),
        'envx': lambda val, tw: ('sig11',  val**2),
        'envy': lambda val, tw: ('sig33',  val**2),
    }

    def __call__(self, name, val, tw):
        try:
            return self._transform[name](val, tw)
        except KeyError:
            return (name, val)
