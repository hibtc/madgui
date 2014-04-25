# encoding: utf-8
"""
Model component for the MadGUI application.
"""

# force new style imports
from __future__ import absolute_import

# standard library
import re

# internal
from madgui.util.common import ivar, cachedproperty
from madgui.util.plugin import HookCollection
from madgui.util.unit import MadxUnits
from madgui.util.vector import Vector

# exported symbols
__all__ = ['Model']


class Model(MadxUnits):

    """
    Extended model class for cern.cpymad.model (extends by delegation).

    Improvements over cern.cpymad.model:

     - knows sequence
     - knows about variables => can perform matching

    :ivar Madx madx:
    :ivar list elements:
    :ivar dict twiss_args:
    """

    # TODO: separate into multipble components:
    #
    # - MadX
    # - metadata (cpymad.model?)
    # - Sequence (elements)
    # - Matcher
    #
    # The MadX instance should be connected to a specific frame at
    # construction time and log all output there in two separate places
    # (panels?):
    #   - logging.XXX
    #   - MAD-X library output
    #
    # Some properties (like `elements` in particular) can not be determined
    # at construction time and must be retrieved later on. Generally,
    # `elements` can come from two sources:
    # - MAD-X memory
    # - metadata
    # A reasonable mechanism is needed to resolve/update it.

    # TODO: more logging
    # TODO: automatically switch directories when CALLing files

    hook = ivar(HookCollection,
                show='madgui.component.model.show',
                update=None,
                add_constraint=None,
                remove_constraint=None,
                clear_constraints=None)

    def __init__(self,
                 madx,
                 name=None,
                 twiss_args=None,
                 elements=None,
                 model=None):
        """
        """
        super(Model, self).__init__(madx)
        self.madx = madx
        self.name = name
        self.twiss_args = twiss_args
        self._columns = ['name','s', 'l','betx','bety', 'angle', 'k1l']
        self.constraints = []
        self._update_elements(elements)
        self.model = model
        try:
            seq = madx.get_active_sequence()
            tw = seq.twiss
        except (RuntimeError, ValueError):
            # TODO: init members
            pass
        else:
            self._update_twiss(tw)

    @property
    def can_match(self):
        return bool(self.twiss_args)

    @property
    def can_select(self):
        return bool(self.elements)

    @property
    def beam(self):
        """Get the beam parameter dictionary."""
        return self.dict_from_madx(self.madx.get_sequence(self.name).beam)

    @beam.setter
    def beam(self):
        """Set beam from a parameter dictionary."""

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        for elem in self.elements:
            at, L = elem.at, elem.L
            if pos >= at and pos <= at+L:
                return elem
        return None

    def element_by_name(self, name):
        """Find the element in the sequence list by its name."""
        for elem in self.elements:
            if elem.name.lower() == name.lower():
                return elem
        return None

    def element_by_position_center(self, pos):
        """Find next element by longitudinal center position."""
        if pos is None:
            return None
        found_at = None
        found_elem = None
        for elem in self.elements:
            at, L = elem.at, elem.L
            center = at + L/2
            if found_elem is None or abs(pos - at) < abs(pos - found_at):
                found_at = at
                found_elem = elem
        return found_elem

    def twiss(self):
        """Recalculate TWISS parameters."""
        results = self.madx.twiss(sequence=self.name,
                                  columns=self._columns,
                                  twiss_init=self.twiss_args)
        self._update_twiss(results)

    def _update_twiss(self, results):
        """Update TWISS results."""
        self.tw = self.dict_from_madx(results.columns.freeze(self._columns))
        self.summary = self.dict_from_madx(results.summary)
        self.update()

    def _update_elements(self, elements=None):
        if elements is None:
            try:
                sequence = self.madx.get_active_sequence()
                elements = sequence.get_elements()
            except RuntimeError:
                self.elements = []
                return
        self.elements = list(map(self.dict_from_madx, elements))

    def element_index_by_name(self, name):
        """Find the element index in the twiss array by its name."""
        for i in range(len(self.tw.name)):
            if self.tw.name[i].lower() == name.lower():
                return i
        return None

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.element_index_by_name(elem.name)

    def get_envelope(self, elem, axis=None):
        """Return beam envelope at element."""
        i = self.get_element_index(elem)
        if i is None:
            return None
        elif axis is None:
            return Vector(self.env.x[i], self.env.y[i])
        else:
            return self.env[axis][i]

    def get_envelope_center(self, elem, axis=None):
        """Return beam envelope at center of element."""
        i = self.get_element_index(elem)
        if i is None:
            raise ValueError("Unknown element!")
        prev = i - 1 if i != 0 else i
        if axis is None:
            return ((self.env.x[i] + self.env.x[prev]) / 2,
                    (self.env.y[i] + self.env.y[prev]) / 2)
        else:
            return (self.env[axis][i] + self.env[axis][prev]) / 2

    def update(self):
        """Perform post processing."""
        # data post processing
        self.pos = self.tw.s
        self.env = Vector(
            (self.tw.betx * self.summary.ex)**0.5,
            (self.tw.bety * self.summary.ey)**0.5)
        self.hook.update()

    def match(self):

        """Perform matching according to current constraints."""

        # select variables: one for each constraint
        vary = []
        allvars = [elem for elem in self.elements
                   if elem.type.lower() == 'quadrupole']
        for axis,elem,envelope in self.constraints:
            at = elem.at
            allowed = [v for v in allvars if v.at < at]
            try:
                v = max(allowed, key=lambda v: v.at)
                try:
                    expr = v.k1._expression
                except AttributeError:
                    expr = v.name + +'->k1'
                vary.append(dict(name=expr, step=1e-6))
                allvars.remove(v)
            except ValueError:
                # No variable in range found! Ok.
                pass

        # select constraints
        constraints = []
        ex, ey = self.summary.ex, self.summary.ey
        for axis,elem,envelope in self.constraints:
            name = 'betx' if axis == 0 else 'bety'
            emittance = ex if axis == 0 else ey
            el_name = re.sub(':\d+$', '', elem.name)
            if isinstance(envelope, tuple):
                lower, upper = envelope
                constraints.append([
                    ('range', el_name),
                    (name, '>', self.value_to_madx(name, lower*lower/emittance)),
                    (name, '<', self.value_to_madx(name, upper*upper/emittance)) ])
            else:
                constraints.append({
                    'range': el_name,
                    name: self.value_to_madx(name, envelope*envelope/emittance)})

        self.madx.match(sequence=self.name,
                        vary=vary,
                        constraints=constraints,
                        twiss_init=self.twiss_args)
        self.twiss()

    def find_constraint(self, elem, axis=None):
        """Find and return the constraint for the specified element."""
        matched = [c for c in self.constraints if c[1] == elem]
        if axis is not None:
            matched = [c for c in matched if c[0] == axis]
        return matched

    def add_constraint(self, axis, elem, envelope):
        """Add constraint and perform matching."""
        # TODO: two constraints on same element represent upper/lower bounds
        #lines = self.draw_constraint(axis, elem, envelope)##EVENT
        #self.view.figure.canvas.draw()
        existing = self.find_constraint(elem, axis)
        if existing:
            self.remove_constraint(elem, axis)
        self.constraints.append( (axis, elem, envelope) )
        self.hook.add_constraint()

    def remove_constraint(self, elem, axis=None):
        """Remove the constraint for elem."""
        self.constraints = [
            c for c in self.constraints
            if c[1].name != elem.name or (axis is not None and c[0] != axis)]
        self.hook.remove_constraint()

    def clear_constraints(self):
        """Remove all constraints."""
        self.constraints = []
        self.hook.clear_constraints()

    def evaluate(self, expr):
        """Evaluate a MADX expression and return the result as float."""
        return self.madx.evaluate(expr)

