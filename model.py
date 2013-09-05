"""
Model component for the MadGUI application.
"""

# standard library
import copy
import json
import math
import os
import re

# scipy
import numpy as np

# other
from event import event

# pymad
from cern import cpymad


def _loadJSON(filename):
    """Load json file into dictionary."""
    with open(filename) as f:
        return json.load(f)

class MadModel:
    """
    Model class for cern.cpymad.model

    Improvements over cern.cpymad.model:

     - knows sequence
     - knows about variables => can perform matching

    """

    def __init__(self, name, path='', **kwargs):
        """Load meta data and compute twiss variables."""
        self.constraints = []
        self.name = name
        self.model = cpymad.model(name, **kwargs)
        self.sequence = _loadJSON(os.path.join(path, name, 'sequence.json'))
        self.variables = _loadJSON(os.path.join(path, name, 'vary.json'))
        self.beam = _loadJSON(os.path.join(path, name, 'beam.json'))
        self.twiss()

    def element_by_position(self, pos):
        """Find optics element by longitudinal position."""
        for elem in self.sequence:
            if 'at' not in elem:
                continue
            at = float(elem['at'])
            L = float(elem.get('L', 0))
            if pos >= at-L/2 and pos <= at+L/2:
                return elem
        return None

    def element_by_position_center(self, pos):
        """Find next element by longitudinal center position."""
        found_at = None
        found_elem = None
        for elem in self.sequence:
            if 'at' not in elem:
                continue
            at = float(elem['at'])
            if found_elem is None or abs(pos - at) < abs(pos - found_at):
                found_at = at
                found_elem = elem
        return found_elem

    def twiss(self):
        """Recalculate TWISS parameters."""
        self.tw, self.summary = self.model.twiss(
                columns=['name','s', 'l','betx','bety', 'angle', 'k1l'])
        self.update()

    def get_element_index(self, elem):
        """Get element index by it name."""
        pattern = re.compile(':\d+$')
        name = elem.get('name').lower()
        for i in range(len(self.tw.name)):
            if pattern.sub("", self.tw.name[i]).lower() == name:
                return i
        return None

    def get_envelope(self, elem, axis=None):
        """Return beam envelope at element."""
        i = self.get_element_index(elem)
        if i is None:
            return None
        elif axis is None:
            return (self.env[0][i], self.env[1][i])
        else:
            return self.env[axis][i]

    def get_envelope_center(self, elem, axis=None):
        """Return beam envelope at center of element."""
        i = self.get_element_index(elem)
        if i is None:
            return None
        prev = i - 1 if i != 0 else i
        if axis is None:
            return ((self.env[0][i] + self.env[0][prev]) / 2,
                    (self.env[1][i] + self.env[1][prev]) / 2)
        else:
            return (self.env[axis][i] + self.env[axis][prev]) / 2

    @event
    def update(self):
        """Perform post processing."""
        # data post processing
        self.pos = self.tw.s
        self.env = (
            np.array([math.sqrt(betx*self.beam['ex']) for betx in self.tw.betx]),
            np.array([math.sqrt(bety*self.beam['ey']) for bety in self.tw.bety]) )

    def match(self):
        """Perform matching according to current constraints."""
        # select variables: one for each constraint
        vary = []
        allvars = copy.copy(self.variables)
        for axis,elem,envelope in self.constraints:
            at = float(elem['at'])
            allowed = (v for v in allvars if float(v['at']) < at)
            try:
                v = max(allowed, key=lambda v: float(v['at']))
                vary.append(v['vary'])
                allvars.remove(v)
            except ValueError:
                # No variable in range found! Ok.
                pass

        # select constraints
        constraints = []
        for axis,elem,envelope in self.constraints:
            name = 'betx' if axis == 0 else 'bety'
            emittance = self.beam['ex'] if axis == 0 else self.beam['ey']
            if isinstance(envelope, tuple):
                lower, upper = envelope
                constraints.append([
                    ('range', elem['name']),
                    (name, '>', lower*lower/emittance),
                    (name, '<', upper*upper/emittance) ])
            else:
                constraints.append({
                    'range': elem['name'],
                    name: envelope*envelope/emittance})

        self.tw, self.summary = self.model.match(vary=vary, constraints=constraints)
        self.update()

    @event
    def find_constraint(self, elem, axis=None):
        matched = [c for c in self.constraints if c[1] == elem]
        if axis is not None:
            matched = [c for c in matched if c[0] == axis]
        return matched

    @event
    def add_constraint(self, axis, elem, envelope):
        """Add constraint and perform matching."""
        # TODO: two constraints on same element represent upper/lower bounds
        #lines = self.draw_constraint(axis, elem, envelope)##EVENT
        #self.view.figure.canvas.draw()

        existing = self.find_constraint(elem, axis)
        if existing:
            self.remove_constraint(elem, axis)

        self.constraints.append( (axis, elem, envelope) )

    @event
    def remove_constraint(self, elem, axis=None):
        """Remove the constraint for elem."""
        self.constraints = [c for c in self.constraints if c[1] != elem or (axis is not None and c[0] != axis)]

    @event
    def clear_constraints(self):
        """Remove all constraints."""
        self.constraints = []


