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
from madgui.util.unit import units, madx as madunit, stripunit
from madgui.util.symbol import SymbolicValue
from madgui.util.vector import Vector

# exported symbols
__all__ = ['Model']


# compatibility
try:                    # python2
    basestring
except NameError:       # python3 (let's think about future...)
    basestring = str


class Model(object):

    """
    Extended model class for cern.cpymad.model (extends by delegation).

    Improvements over cern.cpymad.model:

     - knows sequence
     - knows about variables => can perform matching
    """

    hook = ivar(HookCollection,
                show='madgui.component.model.show',
                update=None,
                add_constraint=None,
                remove_constraint=None,
                clear_constraints=None)

    def __init__(self, model):
        """Load meta data and compute twiss variables."""
        self._columns = ['name','s', 'l','betx','bety', 'angle', 'k1l']
        self.constraints = []
        self.model = model
        self.twiss()

    @cachedproperty
    def sequence(self):
        """Get the associated sequence data."""
        try:
            res = self.model.mdata.repository.get()
            seq = res.yaml('sequence.yml')
            return list(map(self.from_madx, seq))
        except (AttributeError, IOError):
            return None

    @property
    def can_match(self):
        """Check whether matching can be performed"""
        return self.sequence is not None

    @property
    def can_select(self):
        """Check whether information about elements is available."""
        return self.sequence is not None

    @property
    def name(self):
        """Get the name of the model."""
        return self.model.name

    @property
    def beam(self):
        """Get the beam parameter dictionary."""
        return self.from_madx(self.model.get_sequence().beam)

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        if pos is None:
            return None
        for elem in self.sequence:
            at = elem.get('at')
            L = elem.get('L')
            if at is None or L is None:
                continue
            if pos >= at-L/2 and pos <= at+L/2:
                return elem
        return None

    def element_by_name(self, name):
        """Find the element in the sequence list by its name."""
        for elem in self.sequence:
            if 'name' not in elem:
                continue
            if elem['name'].lower() == name.lower():
                return elem
        return None

    def element_by_position_center(self, pos):
        """Find next element by longitudinal center position."""
        if pos is None:
            return None
        found_at = None
        found_elem = None
        for elem in self.sequence:
            at = elem.get('at')
            if at is None:
                continue
            if found_elem is None or abs(pos - at) < abs(pos - found_at):
                found_at = at
                found_elem = elem
        return found_elem

    def twiss(self):
        """Recalculate TWISS parameters."""
        results = self.model.twiss(columns=self._columns)
        self.tw = self.from_madx(results.columns.freeze(self._columns))
        self.summary = self.from_madx(results.summary)
        self.update()

    def element_index_by_name(self, name):
        """Find the element index in the twiss array by its name."""
        pattern = re.compile(':\d+$')
        for i in range(len(self.tw.name)):
            if pattern.sub("", self.tw.name[i]).lower() == name.lower():
                return i
        return None

    def get_element_index(self, elem):
        """Get element index by it name."""
        return self.element_index_by_name(elem.get('name'))

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
            return None
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
        allvars = [elem for elem in self.sequence
                   if elem.get('vary')]
        for axis,elem,envelope in self.constraints:
            at = elem['at']
            allowed = (v for v in allvars if v['at'] < at)
            try:
                v = max(allowed, key=lambda v: v['at'])
                vary += v['vary']
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
            if isinstance(envelope, tuple):
                lower, upper = envelope
                constraints.append([
                    ('range', elem['name']),
                    (name, '>', self.value_to_madx(name, lower*lower/emittance)),
                    (name, '<', self.value_to_madx(name, upper*upper/emittance)) ])
            else:
                constraints.append({
                    'range': elem['name'],
                    name: self.value_to_madx(name, envelope*envelope/emittance)})

        results = self.model.match(vary=vary, constraints=constraints)
        self.tw = self.from_madx(results.columns.freeze(self._columns))
        self.summary = self.from_madx(results.summary)
        self.update()

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
        self.constraints = [c for c in self.constraints if c[1] != elem or (axis is not None and c[0] != axis)]
        self.hook.remove_constraint()

    def clear_constraints(self):
        """Remove all constraints."""
        self.constraints = []
        self.hook.clear_constraints()

    def evaluate(self, expr):
        """Evaluate a MADX expression and return the result as float."""
        return self.model.evaluate(expr)

    def value_from_madx(self, name, value):
        """Add units to a single number."""
        if name in madunit:
            if isinstance(value, basestring):
                return SymbolicValue(self, value, madunit[name])
            else:
                return madunit[name] * value
        else:
            return value

    def value_to_madx(self, name, value):
        """Convert to madx units."""
        return stripunit(value, madunit[name]) if name in madunit else value

    def from_madx(self, obj):
        """Add units to all elements in a dictionary."""
        return obj.__class__({k: self.value_from_madx(k, obj[k])
                              for k in obj})

    def to_madx(self, obj):
        """Remove units from all elements in a dictionary."""
        return obj.__class__({k: self.value_to_madx(k, obj[k])
                              for k in obj})
