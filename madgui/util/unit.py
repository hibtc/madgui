"""
Provides unit conversion.
"""

# force new style imports
from __future__ import absolute_import

# 3rd party
from unum import units
from pydicti import dicti
from cern.cpymad.types import Expression

# internal
from madgui.util.symbol import SymbolicValue


# exported symbols
__all__ = ['units',
           'stripunit',
           'tounit',
           'unit_label',
           'madx',
           'MadxUnits']


# compatibility
try:                    # python2
    basestring
except NameError:       # python3 (let's think about future...)
    basestring = str


def stripunit(quantity, unit=None):
    """Convert the quantity to a plain float."""
    return quantity.asNumber(unit)


def tounit(quantity, unit):
    """Cast the quantity to a specific unit."""
    return quantity.asUnit(unit)


def unit_label(quantity):
    """Get name of the unit."""
    return quantity.strUnit()


def raw_label(quantity):
    """Get the name of the unit, without enclosing brackets."""
    return quantity.strUnit().strip('[]')


class MadxUnits(object):

    """
    Quantity converter.

    Used to add and remove units from quanitities and evaluate expressions.

    :ivar Madx _madx: madx instance used to evaluate expressions
    :cvar dict _units: unit dictionary
    """

    _units = dicti({
        'L': units.m,
        'lrad': units.m,
        'at': units.m,
        's': units.m,
        'x': units.m,
        'y': units.m,
        'betx': units.m,
        'bety': units.m,
        'angle': units.rad,
        'k1': units.m**-2,
        'k1l': units.m**-2,
        'ex': units.m,
        'ey': units.m,
        'tilt': units.rad,
        'hgap': units.m,
        'h': units.rad/units.m,
        'fint': 1,            # dimenisonless
        'fintx': 1,           # dimenisonless
        'e1': units.rad,
        'e2': units.rad,
        # 'knl': None,            # varying units
        # 'ksl': None,            # varying units
        # 'vary': None,           # should be removed
    })

    def __init__(self, madx):
        """Store Madx instance for later use."""
        self._madx = madx

    def unit_label(self, name):
        """Get the name of the unit for the specified parameter name."""
        units = self._units
        return unit_label(units[name]) if name in units else ''

    def value_from_madx(self, name, value):
        """Add units to a single number."""
        units = self._units
        if name in units:
            if isinstance(value, (basestring, Expression)):
                return SymbolicValue(self._madx, str(value), units[name])
            else:
                return units[name] * value
        else:
            return value

    def value_to_madx(self, name, value):
        """Convert to madx units."""
        units = self._units
        return stripunit(value, units[name]) if name in units else value

    def dict_from_madx(self, obj):
        """Add units to all elements in a dictionary."""
        return obj.__class__({k: self.value_from_madx(k, obj[k])
                              for k in obj})

    def dict_to_madx(self, obj):
        """Remove units from all elements in a dictionary."""
        return obj.__class__({k: self.value_to_madx(k, obj[k])
                              for k in obj})
