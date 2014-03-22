"""
Model component for the MadGUI application.
"""

# standard library
import copy
import re
from collections import namedtuple

# internal
from .plugin import hookcollection
from .unit import units, madx as madunit, stripunit

try:
    basestring
except NameError:
    basestring = str

Vector = namedtuple('Vector', ['x', 'y'])

class MadModel(object):
    """
    Model class for cern.cpymad.model

    Improvements over cern.cpymad.model:

     - knows sequence
     - knows about variables => can perform matching

    """
    hook = hookcollection(
        'madgui.model', [
            'show',
            'update',
            'add_constraint',
            'remove_constraint',
            'clear_constraints'
        ])

    def __init__(self, name, model, sequence):
        """Load meta data and compute twiss variables."""
        self.constraints = []
        self.name = name
        self.model = model
        self.sequence = list(map(self.from_madx, sequence))
        self.twiss()

    def show(self, frame):
        self.hook.show(self, frame)

    @property
    def beam(self):
        mdef = self.model._mdef
        beam = mdef['sequences'][self.model._active['sequence']]['beam']
        return self.from_madx(mdef['beams'][beam])

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
        tw, self.summary = self.model.twiss(
                columns=['name','s', 'l','betx','bety', 'angle', 'k1l'])
        self.tw = self.from_madx(tw)
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
        beam = self.beam
        self.env = Vector(
            (self.tw.betx * beam['ex'])**0.5,
            (self.tw.bety * beam['ey'])**0.5)
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
        beam = self.beam
        for axis,elem,envelope in self.constraints:
            name = 'betx' if axis == 0 else 'bety'
            emittance = beam['ex'] if axis == 0 else beam['ey']
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

        tw, self.summary = self.model.match(
            vary=vary,
            constraints=constraints)
        self.tw = self.from_madx(tw)
        self.update()

    def find_constraint(self, elem, axis=None):
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


class SymbolicValue(object):
    def __init__(self, model, value, unit):
        self._model = model
        self._value = value
        self._unit = unit

    def __float__(self):
        return self.asNumber()

    def __str__(self):
        return str(self._evaluate())

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self._value)

    def _evaluate(self):
        return self._unit * self._model.evaluate(self._value)

    def asNumber(self, unit=None):
        return self._evaluate().asNumber(unit)

    def asUnit(self, unit=None):
        return self._evaluate().asUnit(unit)

    def strUnit(self):
        return self._unit.strUnit()

