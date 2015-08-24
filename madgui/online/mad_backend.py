# encoding: utf-8
"""
Implementations covering the MAD-X backend for accessing element properties.
"""

from __future__ import absolute_import

from cpymad.types import Expression
from cpymad.util import is_identifier
from madgui.util.symbol import SymbolicValue

from . import api


def _get_identifier(expr):
    if isinstance(expr, SymbolicValue):
        return str(expr._expression)
    elif isinstance(expr, Expression):
        return str(expr)
    else:
        return ''


def _get_property_lval(elem, attr):
    """
    Return lvalue name for a given element attribute from MAD-X.

    >>> get_element_attribute(elements['r1qs1'], 'k1')
    'r1qs1->k1'
    """
    expr = elem[attr]
    if isinstance(expr, list):
        names = [_get_identifier(v) for v in expr]
        if not any(names):
            raise api.UnknownElement
        return names
    else:
        name = _get_identifier(expr)
        if is_identifier(name):
            return name
        return elem['name'] + '->' + attr


def _value(v):
    if isinstance(v, list):
        return [_value(x) for x in v]
    try:
        return v.value
    except AttributeError:
        return v

def _evaluate(madx, v):
    if isinstance(v, list):
        return [madx.evaluate(x) for x in v]
    return madx.evaluate(v)


class MagnetBackend(api.ElementBackend):

    """Mitigates r/w access to the properties of an element."""

    def __init__(self, madx, utool, elem, lval):
        self._madx = madx
        self._lval = lval
        self._elem = elem
        self._utool = utool

    def get(self):
        """Get dict of values from MAD-X."""
        return {key: self._utool.add_unit(key, _evaluate(self._madx, lval))
                for key, lval in self._lval.items()}

    def set(self, values):
        """Store values to MAD-X."""
        madx = self._madx
        for key, val in values.items():
            plain_value = self._utool.strip_unit(key, val)
            lval = self._lval[key]
            if isinstance(val, list):
                for k, v in zip(lval, plain_value):
                    if k:
                        madx.set_value(k, v)
            else:
                madx.set_value(lval, plain_value)


class MonitorBackend(api.ElementBackend):

    """Mitigates read access to a monitor."""

    # TODO: handle split h-/v-monitor

    def __init__(self, segment, element):
        self._segment = segment
        self._element = element

    def get(self, values):
        twiss = self._segment.tw
        index = self._segment.get_element_index(self._element)
        return {
            'betx': twiss['betx'][index],
            'bety': twiss['bety'][index],
            'x': twiss['posx'][index],
            'y': twiss['posy'][index],
        }

    def set(self, values):
        raise NotImplementedError("Can't set TWISS: monitors are read-only!")


#----------------------------------------
# Converters:
#----------------------------------------

class Monitor(api.ElementBackendConverter):

    standard_keys = ['posx', 'posy', 'widthx', 'widthy']
    backend_keys = ['x', 'y', 'betx', 'bety']

    def __init__(self, ex, ey):
        self._ex = ex
        self._ey = ey

    def to_backend(self, values):
        return {
            'betx': values['widthx'] ** 2 / self._ex,
            'bety': values['widthy'] ** 2 / self._ey,
            'x': values['posx'],
            'y': values['posy'],
        }

    def to_standard(self, values):
        return {
            'widthx': (values['betx'] * self._ex) ** 0.5,
            'widthy': (values['bety'] * self._ey) ** 0.5,
            'posx': values['x'],
            'posy': values['y'],
        }


# Dipole

class Dipole(api.NoConversion):

    standard_keys = backend_keys = ['angle']

    # TODO: DIPOLEs (+MULTIPOLEs) rotate the reference orbit, which is
    # probably not intended... use YROTATION?


class MultipoleNDP(api.ElementBackendConverter):

    standard_keys = ['angle']
    backend_keys = ['knl']

    def to_standard(self, values):
        return {'angle': values['knl'][0]}

    def to_backend(self, values):
        return {'knl': [values['angle']]}


class MultipoleSDP(api.ElementBackendConverter):

    standard_keys = ['angle']
    backend_keys = ['ksl']

    def to_standard(self, values):
        return {'angle': values['ksl'][0]}

    def to_backend(self, values):
        return {'ksl': [values['angle']]}


# Quadrupole

class Quadrupole(api.ElementBackendConverter):

    standard_keys = ['kL']
    backend_keys = ['k1']
    # TODO: handle k1s?

    def __init__(self, l):
        self._l = l

    def to_standard(self, values):
        return {'kL': values['k1'] * self._l}

    def to_backend(self, values):
        return {'k1': values['kL'] / self._l}


class MultipoleNQP(api.ElementBackendConverter):

    standard_keys = ['kL']
    backend_keys = ['knl']

    def to_standard(self, values):
        return {'kL': values['knl'][1]}

    def to_backend(self, values):
        return {'knl': [0, values['kL']]}


class MultipoleSQP(api.ElementBackendConverter):

    standard_keys = ['kL']
    backend_keys = ['ksl']

    def to_standard(self, values):
        return {'kL': values['ksl'][1]}

    def to_backend(self, values):
        return {'ksl': [0, values['kL']]}


# Solenoid

class Solenoid(api.NoConversion):
    standard_keys = backend_keys = ['ks']
